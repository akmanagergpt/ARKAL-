"""The executable Phase 14 root-cause pipeline (ARK-REQ-0086, ARK-REQ-0238,
D-024). RepairPipelinePath enforces BP §Failure protocol's 11-stage sequence
as the sole executable authority; resolve_attempt derives Accept/Reject from
measured evidence and records it through the unchanged C-26 ledger.
"""

from __future__ import annotations

import pathlib
from decimal import Decimal
from typing import Final

import pytest

from arkali.engineering.repair.contracts import (
    RepairBudget,
    RepairBudgetLedger,
    RepairFingerprint,
)
from arkali.engineering.repair.errors import (
    IllegalPipelineTransition,
    RepairBudgetExceededError,
    RepeatedFailedStrategyError,
)
from arkali.engineering.repair.failure_protocol import FailureProtocolVocabulary
from arkali.engineering.repair.pipeline import (
    REJECTED,
    RESOLVED,
    AttemptEvidence,
    AttemptMeasurement,
    RepairPipelinePath,
    RepairStageReceipt,
    resolve_attempt,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def path() -> RepairPipelinePath:
    return RepairPipelinePath.load(REPO)


def ledger(**overrides: object) -> RepairBudgetLedger:
    values: dict[str, object] = {
        "candidate_id": "candidate-14",
        "budget": RepairBudget(
            attempts=2, ai_calls=5, elapsed_seconds=600,
            cost=Decimal("5.00"), touched_files=5, regression_delta=1,
        ),
    }
    values.update(overrides)
    return RepairBudgetLedger.model_validate(values)


def fingerprint(**overrides: object) -> RepairFingerprint:
    values: dict[str, object] = {
        "failure_signature": "pytest: test_pipeline_journey",
        "root_cause_class": "contract-mismatch",
        "files": ("backend/z.py",),
        "strategy": "minimal-contract-repair",
        "provider_model": "local/qwen2.5-coder:14b",
        "outcome": "unresolved",
    }
    values.update(overrides)
    return RepairFingerprint.model_validate(values)


def evidence(**overrides: object) -> AttemptEvidence:
    values: dict[str, object] = {"targeted_tests_passed": True, "regression_passed": True}
    values.update(overrides)
    return AttemptEvidence.model_validate(values)


def measurement(**overrides: object) -> AttemptMeasurement:
    values: dict[str, object] = {
        "ai_calls": 1, "elapsed_seconds": 10, "cost": Decimal("0.10"),
        "touched_files": 1, "regression_delta": 0,
    }
    values.update(overrides)
    return AttemptMeasurement.model_validate(values)


def run_to_terminal(path: RepairPipelinePath, attempt_id: str) -> RepairStageReceipt:
    receipt = path.begin(attempt_id=attempt_id)
    for stage in path.stages()[1:]:
        receipt = path.advance(receipt, to_stage=stage)
    return receipt


class TestTheGovernedStageListComesFromTheDocuments:
    def test_stages_equal_the_live_bp_failure_protocol_lowercased(
        self, path: RepairPipelinePath
    ) -> None:
        """No shadow model: the 11 stages are read, not written here."""
        vocabulary = FailureProtocolVocabulary.load(REPO)
        assert path.stages() == tuple(s.strip().lower() for s in vocabulary.bp_stages())
        assert len(path.stages()) == 11

    def test_ms_stages_are_never_used_as_the_executable_sequence(
        self, path: RepairPipelinePath
    ) -> None:
        """D-024: MS's 9-stage sequence is conceptual, not executable here."""
        vocabulary = FailureProtocolVocabulary.load(REPO)
        assert path.stages() != tuple(s.strip().lower() for s in vocabulary.ms_stages())
        assert len(path.stages()) != len(vocabulary.ms_stages())


class TestThePathAdvancesOnlyOneGovernedStageAtATime:
    def test_beginning_starts_at_reproduce(self, path: RepairPipelinePath) -> None:
        receipt = path.begin(attempt_id="a1")
        assert receipt.stage == "reproduce"
        assert receipt.traversed == ("reproduce",)

    def test_the_full_eleven_stage_sequence_can_be_traversed_in_order(
        self, path: RepairPipelinePath
    ) -> None:
        receipt = run_to_terminal(path, "a1")
        assert receipt.stage == "accept/reject"
        assert receipt.traversed == path.stages()
        assert path.is_terminal(receipt)

    def test_a_skipped_stage_is_refused(self, path: RepairPipelinePath) -> None:
        receipt = path.begin(attempt_id="a1")
        with pytest.raises(IllegalPipelineTransition, match="every governed stage is required"):
            path.advance(receipt, to_stage="Classify")  # skips Evidence

    def test_a_reversed_stage_is_refused(self, path: RepairPipelinePath) -> None:
        receipt = path.begin(attempt_id="a1")
        receipt = path.advance(receipt, to_stage="Evidence")
        with pytest.raises(IllegalPipelineTransition):
            path.advance(receipt, to_stage="Reproduce")

    def test_a_repeated_stage_is_refused(self, path: RepairPipelinePath) -> None:
        receipt = path.begin(attempt_id="a1")
        with pytest.raises(IllegalPipelineTransition):
            path.advance(receipt, to_stage="Reproduce")

    def test_an_unknown_stage_is_refused(self, path: RepairPipelinePath) -> None:
        receipt = path.begin(attempt_id="a1")
        with pytest.raises(IllegalPipelineTransition, match="not a stage"):
            path.advance(receipt, to_stage="Deploy To Production")

    def test_a_forged_receipt_with_an_incomplete_prefix_is_refused(
        self, path: RepairPipelinePath
    ) -> None:
        """A receipt claiming to be at 'candidate' without having actually
        traversed the stages before it must not be honoured."""
        forged = RepairStageReceipt(
            attempt_id="a1", stage="candidate", traversed=("reproduce", "candidate"),
        )
        with pytest.raises(IllegalPipelineTransition, match="complete governed prefix"):
            path.advance(forged, to_stage="targeted tests")


class TestAcceptRejectIsDerivedFromEvidenceNotDeclared:
    def test_resolving_before_the_terminal_stage_is_refused(
        self, path: RepairPipelinePath
    ) -> None:
        receipt = path.begin(attempt_id="a1")
        with pytest.raises(IllegalPipelineTransition, match="governed terminal stage"):
            resolve_attempt(
                path, ledger(), receipt, fingerprint(), evidence(), measurement(),
            )

    @pytest.mark.parametrize(
        ("targeted_tests_passed", "regression_passed", "expected"),
        [
            (True, True, RESOLVED),
            (True, False, REJECTED),
            (False, True, REJECTED),
            (False, False, REJECTED),
        ],
    )
    def test_the_outcome_is_derived_exhaustively_from_both_facts(
        self, path: RepairPipelinePath,
        targeted_tests_passed: bool, regression_passed: bool, expected: str,
    ) -> None:
        """A caller cannot declare 'resolved'; only the two measured facts
        decide it, over the complete closed truth table."""
        receipt = run_to_terminal(path, "a1")
        recorded = resolve_attempt(
            path, ledger(), receipt, fingerprint(),
            evidence(
                targeted_tests_passed=targeted_tests_passed,
                regression_passed=regression_passed,
            ),
            measurement(),
        )
        assert recorded.fingerprints[-1].outcome == expected

    def test_a_failed_attempt_is_still_recorded_against_the_budget(
        self, path: RepairPipelinePath
    ) -> None:
        """J: a failed attempt does not vanish -- it consumes budget and
        remains in evidence, so it cannot silently become an accepted
        candidate by being forgotten either."""
        receipt = run_to_terminal(path, "a1")
        recorded = resolve_attempt(
            path, ledger(), receipt, fingerprint(),
            evidence(targeted_tests_passed=False, regression_passed=False),
            measurement(),
        )
        assert recorded.consumption.attempts == 1
        assert recorded.fingerprints[-1].outcome == REJECTED

    def test_evidence_and_measurement_are_immutable(self) -> None:
        with pytest.raises(Exception):
            evidence().targeted_tests_passed = False  # type: ignore[misc]
        with pytest.raises(Exception):
            measurement().ai_calls = 99  # type: ignore[misc]


class TestResolutionStillEnforcesTheUnchangedC26Mechanisms:
    def test_exceeding_a_budget_dimension_fails_closed(
        self, path: RepairPipelinePath
    ) -> None:
        receipt = run_to_terminal(path, "a1")
        with pytest.raises(RepairBudgetExceededError):
            resolve_attempt(
                path, ledger(), receipt, fingerprint(), evidence(),
                measurement(ai_calls=999),
            )

    def test_a_repeated_failed_strategy_is_refused_not_looped(
        self, path: RepairPipelinePath
    ) -> None:
        receipt = run_to_terminal(path, "a1")
        first = resolve_attempt(
            path, ledger(), receipt, fingerprint(),
            evidence(targeted_tests_passed=False, regression_passed=False),
            measurement(),
        )
        receipt2 = run_to_terminal(path, "a2")
        with pytest.raises(RepeatedFailedStrategyError):
            resolve_attempt(
                path, first, receipt2, fingerprint(),  # same strategy/signature
                evidence(), measurement(),
            )

    def test_a_different_strategy_after_a_rejection_is_permitted(
        self, path: RepairPipelinePath
    ) -> None:
        receipt = run_to_terminal(path, "a1")
        first = resolve_attempt(
            path, ledger(), receipt, fingerprint(),
            evidence(targeted_tests_passed=False, regression_passed=False),
            measurement(),
        )
        receipt2 = run_to_terminal(path, "a2")
        second = resolve_attempt(
            path, first, receipt2, fingerprint(strategy="broader-contract-repair"),
            evidence(), measurement(),
        )
        assert second.consumption.attempts == 2
        assert second.fingerprints[-1].outcome == RESOLVED
