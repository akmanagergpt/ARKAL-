"""D-026 adaptive execution-tier routing tests (ARK-REQ-0392, ARK-REQ-0393)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from arkali.control.capability.capability_graph import CapabilityQueryResult
from arkali.engineering.factory.execution_routing import (
    TIER_ORDER,
    ExecutionTier,
    TierEligibilityRequest,
    TierState,
    select_execution_tier,
)
from arkali.engineering.repair.contracts import (
    RepairBudget,
    RepairBudgetLedger,
    RepairConsumption,
    RepairFingerprint,
)
from arkali.kernel.contracts.results import HonestState

DECISION_LOG_TIER_ORDER = (
    ExecutionTier.DETERMINISTIC_TOOL,
    ExecutionTier.VERIFIED_KNOWLEDGE,
    ExecutionTier.LOCAL_MODEL,
    ExecutionTier.STRONGER_LOCAL_REVIEWER,
    ExecutionTier.CLOUD_PROVIDER,
    ExecutionTier.STRONGER_CLOUD_SPECIALIST,
    ExecutionTier.MULTI_REVIEWER,
    ExecutionTier.HUMAN_GOVERNANCE,
)


class TestTierOrderMatchesD026:
    def test_the_eight_tiers_match_the_decision_log_exactly(self) -> None:
        assert TIER_ORDER == DECISION_LOG_TIER_ORDER

    def test_the_order_has_exactly_eight_members(self) -> None:
        assert len(TIER_ORDER) == 8


class TestDeterministicToolIsPreferredWhenEligible:
    def test_a_deterministically_capable_task_selects_tier_one(self) -> None:
        request = TierEligibilityRequest(task_id="t1", deterministic_capable=True)
        selection = select_execution_tier(request)
        assert selection.selected is ExecutionTier.DETERMINISTIC_TOOL
        assert selection.is_automated

    def test_every_tier_is_still_recorded_even_after_selection(self) -> None:
        request = TierEligibilityRequest(task_id="t1", deterministic_capable=True)
        selection = select_execution_tier(request)
        assert len(selection.evaluations) == 8
        assert selection.evaluations[0].state is TierState.SELECTED


class TestNoAutomatedTierFallsThroughToHumanGovernance:
    def test_an_ineligible_task_with_no_capability_resolves_human_governance(self) -> None:
        request = TierEligibilityRequest(task_id="t2", deterministic_capable=False)
        selection = select_execution_tier(request)
        assert selection.selected is ExecutionTier.HUMAN_GOVERNANCE
        assert not selection.is_automated

    def test_this_is_never_none_and_never_a_bare_boolean(self) -> None:
        """ARK-REQ-0393: no false-PASS shape exists on the result model."""
        request = TierEligibilityRequest(task_id="t2")
        selection = select_execution_tier(request)
        assert isinstance(selection.selected, ExecutionTier)
        assert set(TierState) == {TierState.SELECTED, TierState.NOT_CONFIGURED, TierState.EXHAUSTED}
        assert "PASS" not in TierState.__members__ and "FAIL" not in TierState.__members__


class TestStructurallyUnavailableTiersAreHonest:
    """Phase 18/22 do not exist; no live provider registry exists. These
    resolve NOT_CONFIGURED by construction, never a fabricated availability."""

    @pytest.mark.parametrize(
        "tier",
        [
            ExecutionTier.VERIFIED_KNOWLEDGE,
            ExecutionTier.CLOUD_PROVIDER,
            ExecutionTier.STRONGER_CLOUD_SPECIALIST,
            ExecutionTier.MULTI_REVIEWER,
        ],
    )
    def test_tier_is_not_configured_for_every_request(self, tier: ExecutionTier) -> None:
        request = TierEligibilityRequest(task_id="t3")
        selection = select_execution_tier(request)
        evaluation = next(e for e in selection.evaluations if e.tier is tier)
        assert evaluation.state is TierState.NOT_CONFIGURED


class TestLocalModelTierComposesTheRealCapabilityGraphAnswer:
    """No shadow capability store: the caller's own callable is consulted;
    this module holds no capability data of its own (ARK-REQ-0392)."""

    def test_a_pass_capability_answer_selects_the_local_model_tier(self) -> None:
        request = TierEligibilityRequest(task_id="t4", capability_id="cap.local_gen")

        def query(capability_id: str) -> CapabilityQueryResult:
            assert capability_id == "cap.local_gen"
            return CapabilityQueryResult(
                capability_id=capability_id, state=HonestState.PASS, reason="configured"
            )

        selection = select_execution_tier(request, capability_query=query)
        assert selection.selected is ExecutionTier.LOCAL_MODEL

    def test_a_not_configured_capability_answer_does_not_select_the_tier(self) -> None:
        request = TierEligibilityRequest(task_id="t5", capability_id="cap.local_gen")

        def query(capability_id: str) -> CapabilityQueryResult:
            return CapabilityQueryResult(
                capability_id=capability_id, state=HonestState.NOT_CONFIGURED, reason="absent",
            )

        selection = select_execution_tier(request, capability_query=query)
        assert selection.selected is ExecutionTier.HUMAN_GOVERNANCE

    def test_no_capability_query_supplied_is_honestly_not_configured(self) -> None:
        request = TierEligibilityRequest(task_id="t6", capability_id="cap.local_gen")
        selection = select_execution_tier(request, capability_query=None)
        evaluation = next(
            e for e in selection.evaluations if e.tier is ExecutionTier.LOCAL_MODEL
        )
        assert evaluation.state is TierState.NOT_CONFIGURED


class TestFailoverBoundedByTheExistingRepairLedger:
    """ARK-REQ-0393: repeated use of one failing strategy is bounded by the
    existing C-26 mechanism, not a second budget/retry authority."""

    @staticmethod
    def _fingerprint(strategy: str) -> RepairFingerprint:
        return RepairFingerprint(
            failure_signature="sig", root_cause_class="cls", files=("a.py",),
            strategy=strategy, provider_model="local/deterministic", outcome="pending",
        )

    def test_a_fresh_strategy_still_selects_the_deterministic_tier(self) -> None:
        ledger = RepairBudgetLedger(
            candidate_id="c1",
            budget=RepairBudget(
                attempts=3, ai_calls=0, elapsed_seconds=60, cost=Decimal("0"),
                touched_files=3, regression_delta=0,
            ),
        )
        fingerprint = self._fingerprint("scaffold-v1")
        request = TierEligibilityRequest(task_id="t7", deterministic_capable=True)
        selection = select_execution_tier(request, ledger=ledger, fingerprint=fingerprint)
        assert selection.selected is ExecutionTier.DETERMINISTIC_TOOL

    def test_a_repeated_strategy_already_in_the_ledger_is_exhausted_not_reselected(
        self,
    ) -> None:
        fingerprint = self._fingerprint("scaffold-v1")
        ledger = RepairBudgetLedger(
            candidate_id="c2",
            budget=RepairBudget(
                attempts=3, ai_calls=0, elapsed_seconds=60, cost=Decimal("0"),
                touched_files=3, regression_delta=0,
            ),
            consumption=RepairConsumption(attempts=1),
            fingerprints=(fingerprint,),
        )
        repeat = self._fingerprint("scaffold-v1")
        request = TierEligibilityRequest(task_id="t7", deterministic_capable=True)
        selection = select_execution_tier(request, ledger=ledger, fingerprint=repeat)
        evaluation = next(
            e for e in selection.evaluations if e.tier is ExecutionTier.DETERMINISTIC_TOOL
        )
        assert evaluation.state is TierState.EXHAUSTED
        assert selection.selected is ExecutionTier.HUMAN_GOVERNANCE

    def test_exhaustion_never_produces_a_false_pass(self) -> None:
        """The EXHAUSTED tier can never be `selected`."""
        fingerprint = self._fingerprint("scaffold-v1")
        ledger = RepairBudgetLedger(
            candidate_id="c3",
            budget=RepairBudget(
                attempts=3, ai_calls=0, elapsed_seconds=60, cost=Decimal("0"),
                touched_files=3, regression_delta=0,
            ),
            consumption=RepairConsumption(attempts=1),
            fingerprints=(fingerprint,),
        )
        repeat = self._fingerprint("scaffold-v1")
        request = TierEligibilityRequest(task_id="t8", deterministic_capable=True)
        selection = select_execution_tier(request, ledger=ledger, fingerprint=repeat)
        for evaluation in selection.evaluations:
            if evaluation.state is TierState.EXHAUSTED:
                assert selection.selected is not evaluation.tier


class TestTaskIdentityPassesThroughUnchanged:
    """No durable state is touched; `task_id` is the caller's own identity,
    never regenerated (structural precondition for ARK-REQ-0393)."""

    def test_the_returned_selection_carries_the_same_task_id(self) -> None:
        request = TierEligibilityRequest(task_id="durable-job-42")
        selection = select_execution_tier(request)
        assert selection.task_id == "durable-job-42"
