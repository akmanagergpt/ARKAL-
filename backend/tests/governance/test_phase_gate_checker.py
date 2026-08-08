"""Phase 2 — Phase Gate Checker behaviour, determinism and negative controls."""

from __future__ import annotations

import pathlib

import pytest

from arkali.acceptance.checker import PhaseGateChecker
from arkali.acceptance.gate_verdict import Verdict
from arkali.acceptance.phase_report import PhaseReport, TestExecutionRecord
from arkali.kernel.contracts.errors import GovernanceStateError
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]


def build_report(**overrides: object) -> PhaseReport:
    """A complete, honest Phase 2 report; individual fields overridable."""
    checker = PhaseGateChecker(REPO)
    mandatory = [r.req_id for r in checker.register.for_phase("2") if r.is_mandatory]
    base: dict[str, object] = {
        "phase_id": "2",
        "objective": "Foundation, contracts and executable phase gates",
        "ark_req_ids_closed": tuple(mandatory),
        "files_created": ("backend/arkali/acceptance/checker.py",),
        "files_modified": (),
        "public_contracts": ("C-01", "C-17", "C-18"),
        "migrations": (),
        "state_machine_capability_changes": "none",
        "tests_executed": (
            TestExecutionRecord(command="pytest -q", exit_code=0, passed=1),
        ),
        "architecture_checks": "8 gates executed",
        "duplicate_shadow_check": "0 duplicate authorities",
        "security_findings": "none",
        "fake_success_scan": "clean",
        "evidence_created": ("EV-0015",),
        "limitations": "Python 3.13 NOT_CONFIGURED",
        "blockers": "none",
        "next_exact_action": "begin Phase 3",
        "status": HonestState.PASS,
    }
    base.update(overrides)
    return PhaseReport(**base)  # type: ignore[arg-type]


@pytest.fixture()
def checker() -> PhaseGateChecker:
    return PhaseGateChecker(REPO)


class TestChecksPass:
    def test_complete_report_is_accepted(self, checker: PhaseGateChecker) -> None:
        verdict = checker.evaluate(build_report(), requested_next_phase="3")
        assert verdict.verdict is Verdict.PHASE_ACCEPTED_BY_MACHINE
        assert verdict.progression_permitted is True
        assert verdict.failed_checks() == ()


class TestC1ReportCompleteness:
    def test_missing_field_is_rejected(self, checker: PhaseGateChecker) -> None:
        """NEGATIVE CONTROL: an empty required field must FAIL, not warn."""
        report = build_report(next_exact_action="")
        result = checker.check_report_completeness(report)
        assert result.state is HonestState.FAIL
        assert "next_exact_action" in result.detail


class TestC2RegisterLinkage:
    def test_unknown_requirement_id_is_rejected(
        self, checker: PhaseGateChecker
    ) -> None:
        """NEGATIVE CONTROL: a cited id that is not in the register."""
        report = build_report(ark_req_ids_closed=("ARK-REQ-9999",))
        result = checker.check_register_linkage(report)
        assert result.state is HonestState.FAIL
        assert "unknown" in result.detail

    def test_unaddressed_mandatory_requirement_is_rejected(
        self, checker: PhaseGateChecker
    ) -> None:
        """NEGATIVE CONTROL: silently dropping a phase requirement."""
        report = build_report(ark_req_ids_closed=())
        result = checker.check_register_linkage(report)
        assert result.state is HonestState.FAIL
        assert "unaddressed" in result.detail


class TestC3RecordedExecution:
    def test_no_recorded_run_is_rejected(self, checker: PhaseGateChecker) -> None:
        assert checker.check_recorded_execution(
            build_report(tests_executed=())
        ).state is HonestState.FAIL

    def test_failing_run_under_pass_status_is_rejected(
        self, checker: PhaseGateChecker
    ) -> None:
        """NEGATIVE CONTROL: exit code 1 reported as PASS (ARK-REQ-0216)."""
        report = build_report(
            tests_executed=(
                TestExecutionRecord(command="pytest -q", exit_code=1, failed=1),
            )
        )
        assert checker.check_recorded_execution(report).state is HonestState.FAIL


class TestC5HonestStateIntegrity:
    def test_pass_contradicting_a_failing_run_is_rejected(
        self, checker: PhaseGateChecker
    ) -> None:
        report = build_report(
            tests_executed=(
                TestExecutionRecord(command="pytest", exit_code=2, failed=3),
            )
        )
        assert checker.check_honest_state_integrity(report).state is HonestState.FAIL


class TestPrerequisitesAndHumanGates:
    def test_prerequisites_of_phase_two_are_met(
        self, checker: PhaseGateChecker
    ) -> None:
        assert checker.check_prerequisites("2").state is HonestState.PASS

    def test_unknown_phase_is_rejected(self, checker: PhaseGateChecker) -> None:
        with pytest.raises(GovernanceStateError):
            checker.evaluate(build_report(phase_id="41"))

    def test_recorded_human_gate_is_recognised(
        self, checker: PhaseGateChecker
    ) -> None:
        assert checker.check_human_gate("0B").state is HonestState.PASS

    def test_phase_without_a_gate_is_not_applicable(
        self, checker: PhaseGateChecker
    ) -> None:
        assert checker.check_human_gate("2").state is HonestState.NOT_APPLICABLE

    def test_unrecorded_human_gate_blocks(self, checker: PhaseGateChecker) -> None:
        """NEGATIVE CONTROL: the checker must never self-accept a human gate."""
        checker.state.accepted_human_gates = frozenset()
        result = checker.check_human_gate("23")
        assert result.state is HonestState.BLOCKED
        assert "HUMAN_GATE_2" in result.summary


class TestOpenFindings:
    def test_open_high_finding_blocks_acceptance(
        self, checker: PhaseGateChecker
    ) -> None:
        """NEGATIVE CONTROL: an unresolved HIGH must stop progression."""
        checker.state.open_stopping_findings = ("EXT-999",)
        result = checker.check_open_findings()
        assert result.state is HonestState.FAIL
        verdict = checker.evaluate(build_report())
        assert verdict.verdict is Verdict.PHASE_BLOCKED
        assert verdict.progression_permitted is False


class TestDeterminism:
    def test_repeated_evaluation_is_byte_identical(
        self, checker: PhaseGateChecker
    ) -> None:
        first = PhaseGateChecker(REPO).evaluate(build_report(), "3").to_json()
        second = PhaseGateChecker(REPO).evaluate(build_report(), "3").to_json()
        assert first == second

    def test_render_is_stable(self, checker: PhaseGateChecker) -> None:
        assert checker.evaluate(build_report()).render() == \
            checker.evaluate(build_report()).render()


class TestNoCanonicalMutation:
    def test_evaluation_does_not_write_to_canonical_state(self) -> None:
        watched = [
            REPO / "docs" / "canonical" / "AUTHORITY_MAP.yaml",
            REPO / "docs" / "canonical" / "REQUIREMENT_REGISTER.md",
            REPO / "docs" / "build" / "BUILD_STATE.md",
        ]
        before = {p: p.read_bytes() for p in watched}
        PhaseGateChecker(REPO).evaluate(build_report(), "3")
        assert {p: p.read_bytes() for p in watched} == before


class TestNoShadowModel:
    """The checker must hold no private copy of governed data."""

    def test_phase_to_gate_mapping_comes_from_the_matrix(
        self, checker: PhaseGateChecker
    ) -> None:
        assert checker.state.phase_gates, "phase->gate mapping was not parsed"
        assert checker.state.phase_gates["23"] == "HUMAN_GATE_2"
        assert checker.state.phase_gates["37"] == "HUMAN_GATE_7"

    def test_mapping_drift_changes_the_verdict(
        self, checker: PhaseGateChecker
    ) -> None:
        """DRIFT CONTROL: altering the parsed mapping must change behaviour.

        Proves the checker reads the mapping rather than a hard-coded copy: if a
        gate were hard-coded, re-pointing phase 2 at an unaccepted gate would
        have no effect.
        """
        assert checker.check_human_gate("2").state is HonestState.NOT_APPLICABLE
        checker.state.phase_gates = {**checker.state.phase_gates, "2": "HUMAN_GATE_5"}
        blocked = checker.check_human_gate("2")
        assert blocked.state is HonestState.BLOCKED
        assert "HUMAN_GATE_5" in blocked.summary

    def test_register_denominator_is_not_hard_coded(
        self, checker: PhaseGateChecker
    ) -> None:
        """DRIFT CONTROL: the mandatory count must follow the register file."""
        from arkali.control.specification.register_parser import RequirementRegister

        live = RequirementRegister.load(REPO)
        assert len(checker.register) == len(live)
        assert checker.register.classification_counts() == live.classification_counts()


class TestExitCodeIsStructurallyRequired:
    """A claimed run without an exit code cannot be constructed at all."""

    def test_missing_exit_code_is_rejected_at_construction(self) -> None:
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            TestExecutionRecord(command="pytest -q")  # type: ignore[call-arg]

    def test_unnamed_run_is_rejected_by_c3(self, checker: PhaseGateChecker) -> None:
        report = build_report(
            tests_executed=(TestExecutionRecord(command="   ", exit_code=0),)
        )
        assert checker.check_recorded_execution(report).state is HonestState.FAIL
