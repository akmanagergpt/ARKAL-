"""ARK-REQ-0219 — never fabricate or simulate an external-provider result.

`BP §Mandatory`. The invariant is NEGATIVE: Phase 9 satisfies it without
producing a real external-provider result, by proving the acceptance mechanism
cannot turn an absent, local or simulated result into an external claim.

Every subject is DERIVED - the obligation phase from the register, the current
work phase from `GovernanceState`, the binding from the canonical contract
inventory. No phase number, provider name or contract revision is written here,
so a canonical change moves these controls instead of expiring them (F-0021).

NOTHING HERE CONTACTS A PROVIDER, and no stand-in provider is presented as
evidence that the requirement is met. What is proven is refusal.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Final

import pytest

from arkali.acceptance.external_result import ExternalProviderResultRule as Rule
from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.phase_report import PhaseReport, TestExecutionRecord
from arkali.control.specification.register_parser import RequirementRegister
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
ACCEPTED: Final[pathlib.Path] = REPO / "docs" / "acceptance"


@pytest.fixture(scope="module")
def register() -> RequirementRegister:
    return RequirementRegister.load(REPO)


@pytest.fixture(scope="module")
def owing_phase(register: RequirementRegister) -> str:
    entry = register.get(Rule.REQUIREMENT)
    assert entry is not None, f"{Rule.REQUIREMENT} is absent from the register"
    return entry.owning_phase


def run(**changes: object) -> TestExecutionRecord:
    """A recorded run. `external_result` is supplied only when asked for, so a
    control can tell a declaration from a default."""
    fields: dict[str, object] = {
        "command": ".\\.venv\\Scripts\\python.exe -m pytest backend -q",
        "exit_code": 0,
        "passed": 1,
        "failed": 0,
        "summary": "a run",
    }
    fields.update(changes)
    return TestExecutionRecord(**fields)  # type: ignore[arg-type]


def report(phase_id: str, *runs: TestExecutionRecord) -> PhaseReport:
    return PhaseReport(
        phase_id=phase_id,
        objective="control fixture",
        ark_req_ids_closed=(),
        files_created=("x.py",),
        files_modified=(),
        public_contracts=(),
        migrations=(),
        state_machine_capability_changes="none",
        tests_executed=runs or (run(external_result=Rule.Declared.NO_EXTERNAL_RESULT),),
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


def verdict(record: PhaseReport, register: RequirementRegister) -> tuple[bool, str, str]:
    return Rule.evaluate(REPO, record, register)


class TestTheDeclaredVocabulary:
    def test_exactly_one_class_claims_an_external_result(self) -> None:
        claiming = [c for c in Rule.Declared if c.claims_external]
        assert len(claiming) == 1
        assert claiming[0] is Rule.Declared.EXTERNAL_PROVIDER_RESULT

    def test_the_three_required_meanings_exist(self) -> None:
        """Honest absence, a test-only double, and a claimed external result."""
        assert len(list(Rule.Declared)) == 3
        assert not Rule.Declared.NO_EXTERNAL_RESULT.claims_external
        assert not Rule.Declared.SIMULATED_TEST_ONLY.claims_external

    def test_the_contract_default_is_non_claiming(self) -> None:
        """Silence may never read as a claim of external provenance."""
        assert not run().external_result.claims_external
        assert run().external_result is Rule.Declared.NO_EXTERNAL_RESULT

    def test_no_stored_verification_flag_exists_to_trust(self) -> None:
        """The binding is recomputed; there is no boolean to believe."""
        fields = set(TestExecutionRecord.model_fields)
        assert not {"is_real", "verified", "external_verified", "real"} & fields


class TestTheExternalPathIsClosed:
    def test_no_canonical_binding_exists_today(self) -> None:
        available, reason, source = Rule.binding(REPO)
        assert available is False
        assert reason and source

    def test_an_external_declaration_is_refused(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        passed, summary, _ = verdict(
            report(owing_phase,
                   run(external_result=Rule.Declared.EXTERNAL_PROVIDER_RESULT)),
            register,
        )
        assert passed is False
        assert "no canonical binding can substantiate" in summary

    def test_a_simulated_run_relabelled_external_is_refused(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        """Relabelling is the only way a double could become an external claim."""
        honest = report(owing_phase,
                        run(external_result=Rule.Declared.SIMULATED_TEST_ONLY))
        assert verdict(honest, register)[0] is True
        relabelled = report(owing_phase,
                            run(external_result=Rule.Declared.EXTERNAL_PROVIDER_RESULT))
        assert verdict(relabelled, register)[0] is False

    def test_a_local_run_relabelled_external_is_refused(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        local = report(owing_phase,
                       run(external_result=Rule.Declared.NO_EXTERNAL_RESULT))
        assert verdict(local, register)[0] is True
        relabelled = report(owing_phase,
                            run(external_result=Rule.Declared.EXTERNAL_PROVIDER_RESULT))
        assert verdict(relabelled, register)[0] is False

    def test_a_fabricated_provider_identity_in_prose_changes_nothing(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        """Prose is never consulted, in either direction: naming a real provider
        cannot earn a claim, and cannot manufacture one either."""
        prose = run(
            command="benchmark --provider anthropic --model claude-opus-4",
            summary="live endpoint, 12 responses, mean latency 812ms",
            external_result=Rule.Declared.NO_EXTERNAL_RESULT,
        )
        assert verdict(report(owing_phase, prose), register)[0] is True
        claimed = run(
            command="benchmark --provider anthropic --model claude-opus-4",
            summary="live endpoint",
            external_result=Rule.Declared.EXTERNAL_PROVIDER_RESULT,
        )
        assert verdict(report(owing_phase, claimed), register)[0] is False

    @pytest.mark.parametrize("honest", [HonestState.NOT_CONFIGURED,
                                        HonestState.EXTERNAL_UNAVAILABLE])
    def test_an_honest_non_result_cannot_become_an_external_success(
        self, register: RequirementRegister, owing_phase: str, honest: HonestState
    ) -> None:
        """The canonical honest outcomes stay honest, and declaring one of them
        external is refused exactly like any other unsubstantiated claim."""
        record = report(
            owing_phase,
            run(summary=f"provider {honest.value}",
                external_result=Rule.Declared.NO_EXTERNAL_RESULT),
        )
        assert verdict(record, register)[0] is True
        converted = report(
            owing_phase,
            run(summary=f"provider {honest.value}", exit_code=0,
                external_result=Rule.Declared.EXTERNAL_PROVIDER_RESULT),
        )
        assert verdict(converted, register)[0] is False


class TestTheDeclarationIsOwedAndCannotBeEscaped:
    def test_an_omitted_classification_on_a_current_candidate_is_refused(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        passed, summary, _ = verdict(report(owing_phase, run()), register)
        assert passed is False
        assert "does not declare" in summary

    def test_a_default_is_not_a_declaration(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        """The two are distinguished, or silence would satisfy the rule."""
        defaulted = report(owing_phase, run())
        declared = report(owing_phase,
                          run(external_result=Rule.Declared.NO_EXTERNAL_RESULT))
        assert defaulted.tests_executed[0].external_result == \
            declared.tests_executed[0].external_result
        assert verdict(defaulted, register)[0] is False
        assert verdict(declared, register)[0] is True

    def test_the_obligation_comes_from_the_register_not_the_report(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        """A candidate cannot declare an older revision to escape the rule: the
        boundary is the register's Phase column, which the report cannot edit."""
        assert Rule.phase_owes(owing_phase, owing_phase)
        earlier = str(max(int("".join(c for c in owing_phase if c.isdigit())) - 1, 0))
        assert not Rule.phase_owes(earlier, owing_phase)
        assert verdict(report(earlier, run()), register)[0] is True

    def test_the_current_work_phase_owes_a_declaration(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        """Derived, so this stays true as the build advances."""
        current = GovernanceState.load(REPO).current_work_phase()
        assert current is not None
        assert Rule.phase_owes(current, owing_phase)

    def test_a_missing_requirement_row_fails_closed(
        self, owing_phase: str
    ) -> None:
        class Empty:
            @staticmethod
            def get(_req_id: str) -> None:
                return None

        passed, summary, _ = Rule.evaluate(REPO, report(owing_phase, run()), Empty())
        assert passed is False
        assert "absent from the requirement register" in summary


class TestPermittedOutcomesRemainPermitted:
    def test_an_honest_no_result_run_passes(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        record = report(owing_phase,
                        run(external_result=Rule.Declared.NO_EXTERNAL_RESULT))
        assert verdict(record, register)[0] is True

    def test_a_test_only_double_passes_and_claims_nothing(
        self, register: RequirementRegister, owing_phase: str
    ) -> None:
        record = report(owing_phase,
                        run(external_result=Rule.Declared.SIMULATED_TEST_ONLY))
        passed, _, detail = verdict(record, register)
        assert passed is True
        assert Rule.Declared.SIMULATED_TEST_ONLY.value in detail
        assert not Rule.external_runs(record)

    def test_every_accepted_report_stays_valid_and_byte_identical(
        self, register: RequirementRegister
    ) -> None:
        """Historical reports keep their bytes AND their meaning: none of them
        is read as claiming an external result."""
        reports = sorted(ACCEPTED.glob("phase_*_report*.json"))
        assert len(reports) > 5, "too few accepted reports to prove compatibility"
        for path in reports:
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            record = PhaseReport.model_validate(json.loads(path.read_text("utf-8")))
            assert verdict(record, register)[0] is True, path.name
            assert not Rule.external_runs(record), path.name
            assert hashlib.sha256(path.read_bytes()).hexdigest() == before
