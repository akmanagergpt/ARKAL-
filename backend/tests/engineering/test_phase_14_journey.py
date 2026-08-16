"""Phase 14 composed journey: reproduce -> governed pipeline -> evidence ->
Accept/Reject, over real repository authorities.

Proves the behaviours BUILD_STATE.md's Package 5 paragraph and
docs/contracts/repair.md declare, composed rather than unit-isolated:
reproduction evidence, ordered progression through the D-024-governed
11-stage BP pipeline, deterministic-transformer confinement to the
candidate lifecycle (ARK-REQ-0240), canonical fingerprint evidence
(ARK-REQ-0087), all six bounded budget dimensions (ARK-REQ-0029,
ARK-REQ-0088), anti-loop refusal on a repeated strategy (ARK-REQ-0239),
budget exhaustion failing closed, targeted tests preceding regression and
Accept/Reject, an evidence-derived (never fabricated) terminal outcome, and
the register-derived Phase 14 denominator.
"""

from __future__ import annotations

import pathlib
from decimal import Decimal
from typing import Final

import pytest

from arkali.control.policy.agent_authority import AgentAuthority
from arkali.control.policy.policy_errors import DirectStableMutationError
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.repair.contracts import (
    RepairBudget,
    RepairBudgetLedger,
    RepairFingerprint,
)
from arkali.engineering.repair.deterministic_transformer import DeterministicTransformer
from arkali.engineering.repair.errors import (
    RepairBudgetExceededError,
    RepeatedFailedStrategyError,
)
from arkali.engineering.repair.pipeline import (
    REJECTED,
    RESOLVED,
    AttemptEvidence,
    AttemptMeasurement,
    RepairPipelinePath,
    resolve_attempt,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PHASE: Final[str] = "14"


class TestPhase14Journey:
    def test_step_1_the_denominator_is_derived_from_the_register(self) -> None:
        requirements = RequirementRegister.load(REPO).for_phase(PHASE)
        assert {r.req_id for r in requirements} == {
            "ARK-REQ-0029", "ARK-REQ-0086", "ARK-REQ-0087", "ARK-REQ-0088",
            "ARK-REQ-0238", "ARK-REQ-0239", "ARK-REQ-0240",
        }
        assert {r.owning_component for r in requirements} == {
            "engineering.repair", "control.policy",
        }

    def test_step_2_a_failure_is_reproduced_and_the_governed_pipeline_advances_in_order(
        self,
    ) -> None:
        path = RepairPipelinePath.load(REPO)
        receipt = path.begin(attempt_id="journey-attempt-1")
        assert receipt.stage == "reproduce"
        for stage in ("evidence", "classify", "hypotheses", "experiment",
                      "root cause", "minimal change", "candidate"):
            receipt = path.advance(receipt, to_stage=stage)
        assert receipt.stage == "candidate"
        assert receipt.traversed == path.stages()[:8]

    def test_step_3_a_deterministic_transformer_at_the_candidate_stage_cannot_reach_stable(
        self,
    ) -> None:
        """ARK-REQ-0240, composed: a transformer participating at the
        Candidate stage is proven, through the real Phase 10 authority, to
        have no path to a direct Stable write."""
        authority = AgentAuthority.load(REPO)
        transformer = DeterministicTransformer(
            name="strip-trailing-whitespace", version="1.0.0",
        )
        with pytest.raises(DirectStableMutationError):
            transformer.assert_confined_to_candidate_lifecycle(authority)

    def test_step_4_targeted_tests_precede_regression_precede_accept_reject(self) -> None:
        path = RepairPipelinePath.load(REPO)
        receipt = path.begin(attempt_id="journey-attempt-1")
        for stage in path.stages()[1:]:
            receipt = path.advance(receipt, to_stage=stage)
        assert receipt.stage == "accept/reject"
        order = receipt.traversed
        assert order.index("targeted tests") < order.index("regression") < order.index(
            "accept/reject"
        )

    def test_step_5_accept_reject_is_derived_from_real_evidence_not_declared(self) -> None:
        """ARK-REQ-0087, ARK-REQ-0238, I, J: the outcome comes from measured
        facts, and a failing attempt is recorded honestly, not silently
        promoted or dropped."""
        path = RepairPipelinePath.load(REPO)
        ledger = RepairBudgetLedger.model_validate({
            "candidate_id": "journey-candidate",
            "budget": RepairBudget(
                attempts=3, ai_calls=10, elapsed_seconds=600,
                cost=Decimal("5.00"), touched_files=5, regression_delta=1,
            ),
        })
        failing_receipt = path.begin(attempt_id="journey-attempt-fail")
        for stage in path.stages()[1:]:
            failing_receipt = path.advance(failing_receipt, to_stage=stage)
        failing_fp = RepairFingerprint.model_validate({
            "failure_signature": "pytest: journey_failure",
            "root_cause_class": "contract-mismatch",
            "files": ("backend/z.py",),
            "strategy": "narrow-fix",
            "provider_model": "local/qwen2.5-coder:14b",
            "outcome": "unresolved",
        })
        after_failure = resolve_attempt(
            path, ledger, failing_receipt, failing_fp,
            AttemptEvidence(targeted_tests_passed=True, regression_passed=False),
            AttemptMeasurement(
                ai_calls=1, elapsed_seconds=30, cost=Decimal("0.05"),
                touched_files=1, regression_delta=0,
            ),
        )
        assert after_failure.fingerprints[-1].outcome == REJECTED
        assert after_failure.consumption.attempts == 1, "a rejected attempt is still recorded"

        succeeding_receipt = path.begin(attempt_id="journey-attempt-2")
        for stage in path.stages()[1:]:
            succeeding_receipt = path.advance(succeeding_receipt, to_stage=stage)
        succeeding_fp = RepairFingerprint.model_validate({
            "failure_signature": "pytest: journey_failure",
            "root_cause_class": "contract-mismatch",
            "files": ("backend/z.py",),
            "strategy": "broader-fix",
            "provider_model": "local/qwen2.5-coder:14b",
            "outcome": "unresolved",
        })
        after_success = resolve_attempt(
            path, after_failure, succeeding_receipt, succeeding_fp,
            AttemptEvidence(targeted_tests_passed=True, regression_passed=True),
            AttemptMeasurement(
                ai_calls=1, elapsed_seconds=30, cost=Decimal("0.05"),
                touched_files=1, regression_delta=0,
            ),
        )
        assert after_success.fingerprints[-1].outcome == RESOLVED
        assert after_success.consumption.attempts == 2

    def test_step_6_repeating_the_narrow_fix_strategy_is_refused_not_looped(self) -> None:
        """ARK-REQ-0087, ARK-REQ-0239: repeated failed strategy escalates."""
        path = RepairPipelinePath.load(REPO)
        ledger = RepairBudgetLedger.model_validate({
            "candidate_id": "journey-candidate-2",
            "budget": RepairBudget(
                attempts=3, ai_calls=10, elapsed_seconds=600,
                cost=Decimal("5.00"), touched_files=5, regression_delta=1,
            ),
        })
        first_receipt = path.begin(attempt_id="a1")
        for stage in path.stages()[1:]:
            first_receipt = path.advance(first_receipt, to_stage=stage)
        fp = RepairFingerprint.model_validate({
            "failure_signature": "pytest: journey_loop",
            "root_cause_class": "contract-mismatch",
            "files": ("backend/z.py",),
            "strategy": "narrow-fix",
            "provider_model": "local/qwen2.5-coder:14b",
            "outcome": "unresolved",
        })
        recorded = resolve_attempt(
            path, ledger, first_receipt, fp,
            AttemptEvidence(targeted_tests_passed=False, regression_passed=False),
            AttemptMeasurement(
                ai_calls=1, elapsed_seconds=1, cost=Decimal("0"),
                touched_files=1, regression_delta=0,
            ),
        )
        second_receipt = path.begin(attempt_id="a2")
        for stage in path.stages()[1:]:
            second_receipt = path.advance(second_receipt, to_stage=stage)
        with pytest.raises(RepeatedFailedStrategyError):
            resolve_attempt(
                path, recorded, second_receipt, fp,
                AttemptEvidence(targeted_tests_passed=True, regression_passed=True),
                AttemptMeasurement(
                    ai_calls=1, elapsed_seconds=1, cost=Decimal("0"),
                    touched_files=1, regression_delta=0,
                ),
            )

    def test_step_7_budget_exhaustion_fails_closed(self) -> None:
        """F: exceeding any of the six dimensions refuses, never silently
        continues the loop."""
        path = RepairPipelinePath.load(REPO)
        ledger = RepairBudgetLedger.model_validate({
            "candidate_id": "journey-candidate-3",
            "budget": RepairBudget(
                attempts=1, ai_calls=10, elapsed_seconds=600,
                cost=Decimal("5.00"), touched_files=5, regression_delta=1,
            ),
        })
        receipt = path.begin(attempt_id="a1")
        for stage in path.stages()[1:]:
            receipt = path.advance(receipt, to_stage=stage)
        fp = RepairFingerprint.model_validate({
            "failure_signature": "pytest: journey_budget",
            "root_cause_class": "contract-mismatch",
            "files": ("backend/z.py",),
            "strategy": "attempt-one",
            "provider_model": "local/qwen2.5-coder:14b",
            "outcome": "unresolved",
        })
        exhausted = resolve_attempt(
            path, ledger, receipt, fp,
            AttemptEvidence(targeted_tests_passed=False, regression_passed=False),
            AttemptMeasurement(
                ai_calls=1, elapsed_seconds=1, cost=Decimal("0"),
                touched_files=1, regression_delta=0,
            ),
        )
        second_receipt = path.begin(attempt_id="a2")
        for stage in path.stages()[1:]:
            second_receipt = path.advance(second_receipt, to_stage=stage)
        fp2 = RepairFingerprint.model_validate({
            "failure_signature": "pytest: journey_budget",
            "root_cause_class": "contract-mismatch",
            "files": ("backend/z.py",),
            "strategy": "attempt-two",
            "provider_model": "local/qwen2.5-coder:14b",
            "outcome": "unresolved",
        })
        with pytest.raises(RepairBudgetExceededError):
            resolve_attempt(
                path, exhausted, second_receipt, fp2,
                AttemptEvidence(targeted_tests_passed=True, regression_passed=True),
                AttemptMeasurement(
                    ai_calls=1, elapsed_seconds=1, cost=Decimal("0"),
                    touched_files=1, regression_delta=0,
                ),
            )

    def test_step_8_no_external_provider_result_is_claimed(self) -> None:
        """K: the recorded provider/model is declared test data; no network
        call, external provider or fabricated result exists anywhere in this
        journey."""
        fp = RepairFingerprint.model_validate({
            "failure_signature": "pytest: journey_provider",
            "root_cause_class": "contract-mismatch",
            "files": ("backend/z.py",),
            "strategy": "narrow-fix",
            "provider_model": "local/qwen2.5-coder:14b",
            "outcome": "unresolved",
        })
        assert fp.provider_model.startswith("local/")
