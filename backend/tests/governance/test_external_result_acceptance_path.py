"""The ARK-REQ-0219 rule must be reached by the acceptance path itself.

THE F-0017 / F-0040 LESSON. Exercising a rule directly never proves its caller
consults it: a mutation making the checker ignore the result passed every
control that called the helper by hand. These controls drive the REAL
`PhaseGateChecker` over a copied canonical document tree, so a bypass in the
acceptance path fails them.

Every subject is derived. No phase number or check id ordering is assumed
beyond what the checker itself reports.

ADR-0008 decomposition: kept beside the rule's own controls rather than inside
them, because the subject is the acceptance path rather than the rule. No GATE 8
exception was requested.
"""

from __future__ import annotations

import pathlib
import shutil
from typing import Final

import pytest

from arkali.acceptance.checker import PhaseGateChecker
from arkali.acceptance.external_result import ExternalProviderResultRule as Rule
from arkali.acceptance.phase_report import PhaseReport, TestExecutionRecord
from arkali.control.specification.register_parser import RequirementRegister
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
#: Everything the checker reads. Copied, never written in place.
DOCUMENT_TREE: Final[tuple[str, ...]] = ("docs", "backend/arkali")


@pytest.fixture(scope="module")
def owing_phase() -> str:
    entry = RequirementRegister.load(REPO).get(Rule.REQUIREMENT)
    assert entry is not None
    return entry.owning_phase


@pytest.fixture()
def tree(tmp_path: pathlib.Path) -> pathlib.Path:
    for relative in DOCUMENT_TREE:
        source = REPO / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)
    return tmp_path


def build(phase_id: str, declared: Rule.Declared | None) -> PhaseReport:
    fields: dict[str, object] = {
        "command": "pytest", "exit_code": 0, "passed": 1, "failed": 0,
        "summary": "run",
    }
    if declared is not None:
        fields["external_result"] = declared
    return PhaseReport(
        phase_id=phase_id,
        objective="acceptance-path fixture",
        ark_req_ids_closed=(),
        files_created=("x.py",),
        files_modified=(),
        public_contracts=(),
        migrations=(),
        state_machine_capability_changes="none",
        tests_executed=(TestExecutionRecord(**fields),),  # type: ignore[arg-type]
        architecture_checks="gates PASS",
        duplicate_shadow_check="none",
        security_findings="none",
        fake_success_scan="clean",
        evidence_created=("EV-0001",),
        limitations="none",
        blockers="none",
        next_exact_action="continue",
        status=HonestState.PASS,
    )


def results(tree: pathlib.Path, report: PhaseReport) -> dict[str, HonestState]:
    checker = PhaseGateChecker(tree)
    return {r.check_id: r.state for r in checker._run_checks(report)}


class TestTheAcceptancePathInvokesTheRule:
    def test_the_check_is_part_of_the_one_acceptance_path(
        self, tree: pathlib.Path, owing_phase: str
    ) -> None:
        """No route to a verdict may omit it."""
        states = results(tree, build(owing_phase, Rule.Declared.NO_EXTERNAL_RESULT))
        assert "EXTERNAL_RESULT" in states, sorted(states)

    def test_an_external_claim_fails_through_the_checker(
        self, tree: pathlib.Path, owing_phase: str
    ) -> None:
        states = results(
            tree, build(owing_phase, Rule.Declared.EXTERNAL_PROVIDER_RESULT)
        )
        assert states["EXTERNAL_RESULT"] is HonestState.FAIL

    def test_an_undeclared_run_fails_through_the_checker(
        self, tree: pathlib.Path, owing_phase: str
    ) -> None:
        states = results(tree, build(owing_phase, None))
        assert states["EXTERNAL_RESULT"] is HonestState.FAIL

    def test_an_honest_declaration_passes_through_the_checker(
        self, tree: pathlib.Path, owing_phase: str
    ) -> None:
        states = results(tree, build(owing_phase, Rule.Declared.NO_EXTERNAL_RESULT))
        assert states["EXTERNAL_RESULT"] is HonestState.PASS

    def test_a_test_only_double_passes_through_the_checker(
        self, tree: pathlib.Path, owing_phase: str
    ) -> None:
        states = results(tree, build(owing_phase, Rule.Declared.SIMULATED_TEST_ONLY))
        assert states["EXTERNAL_RESULT"] is HonestState.PASS

    def test_a_failing_external_claim_stops_the_public_verdict(
        self, tree: pathlib.Path, owing_phase: str
    ) -> None:
        """A FAIL must reach the VERDICT, not sit in an ignored result list.

        Driven through the public entry point rather than `_run_checks`, so a
        checker that collected the result and then discarded it would fail here.
        """
        from arkali.acceptance.gate_verdict import Verdict

        checker = PhaseGateChecker(tree)
        claimed = checker.evaluate(
            build(owing_phase, Rule.Declared.EXTERNAL_PROVIDER_RESULT)
        )
        assert claimed.verdict is not Verdict.PHASE_ACCEPTED_BY_MACHINE
        assert any(
            r.check_id == "EXTERNAL_RESULT" and r.state is HonestState.FAIL
            for r in claimed.checks
        )
