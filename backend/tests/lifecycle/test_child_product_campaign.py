"""C-36 child-product campaign composition over the real, unmodified C-33
`EvolutionCampaign` machine (ARK-REQ-0132/0133) - no second state machine,
no second campaign authority.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from arkali.kernel.contracts.state_machine_errors import GuardRejected
from arkali.lifecycle.evolution import evolution_campaign_state_machine as ecsm
from arkali.lifecycle.evolution.campaign_declaration import CampaignBudgets
from arkali.lifecycle.evolution.child_product_campaign import (
    _child_campaign_id,
    begin_child_product_campaign,
    declare_child_product_campaign,
)
from arkali.lifecycle.evolution.child_product_identity import (
    ChildProductIdentity,
    ChildProductMode,
)
from arkali.lifecycle.evolution.errors import ChildProductNotSdkEligibleError


def identity(**updates: object) -> ChildProductIdentity:
    values: dict[str, object] = {
        "product_id": "acme-task-tracker",
        "name": "Acme Task Tracker",
        "mode": ChildProductMode.AI_NATIVE_SELF_EVOLVING,
    }
    values.update(updates)
    return ChildProductIdentity.model_validate(values)


def budgets(**updates: object) -> CampaignBudgets:
    values: dict[str, object] = {
        "candidate_budget": 5,
        "ai_call_budget": 20,
        "time_budget_seconds": 3600,
        "cost_budget": Decimal("10.00"),
        "regression_ceiling": 0,
        "no_progress_threshold": 3,
    }
    values.update(updates)
    return CampaignBudgets.model_validate(values)


class TestModeEligibilityRefusesBeforeConstruction:
    @pytest.mark.parametrize(
        "mode", [ChildProductMode.STANDARD, ChildProductMode.AI_ASSISTED]
    )
    def test_ineligible_modes_are_refused(self, mode: ChildProductMode) -> None:
        with pytest.raises(ChildProductNotSdkEligibleError):
            declare_child_product_campaign(
                identity(mode=mode),
                objective="add recurring tasks",
                baseline_metrics={"feature_count": 4.0},
                budgets=budgets(),
            )

    def test_ai_native_self_evolving_is_accepted(self) -> None:
        declaration = declare_child_product_campaign(
            identity(),
            objective="add recurring tasks",
            baseline_metrics={"feature_count": 4.0},
            budgets=budgets(),
        )
        assert declaration.objective == "add recurring tasks"


class TestCampaignIdBindsToTheExactProductAndRequest:
    def test_two_different_products_get_different_campaign_ids(self) -> None:
        first = _child_campaign_id(identity(product_id="product-a"), "x")
        second = _child_campaign_id(identity(product_id="product-b"), "x")
        assert first != second

    def test_the_same_product_and_objective_is_deterministic(self) -> None:
        assert _child_campaign_id(identity(), "x") == _child_campaign_id(identity(), "x")

    def test_two_different_evolution_requests_for_the_same_product_get_different_ids(
        self,
    ) -> None:
        """The real defect `test_child_product_journey.py` found: a second
        evolution request for the *same* product must not collide with the
        first's campaign_id (which would then collide the workspace it
        allocates, refused as "already allocated")."""
        subject = identity()
        first = _child_campaign_id(subject, "add recurring tasks")
        second = _child_campaign_id(subject, "add task search")
        assert first != second

    def test_declared_campaign_carries_the_bound_id(self) -> None:
        subject = identity()
        declaration = declare_child_product_campaign(
            subject, objective="x", baseline_metrics={"m": 1.0}, budgets=budgets(),
        )
        assert declaration.campaign_id == _child_campaign_id(subject, "x")


class TestBeginsTheRealUnmodifiedEvolutionCampaignMachine:
    def test_a_valid_declaration_reaches_running(self) -> None:
        declaration = declare_child_product_campaign(
            identity(), objective="x", baseline_metrics={"m": 1.0}, budgets=budgets(),
        )
        instance = begin_child_product_campaign(declaration)
        assert instance.state == "RUNNING"
        assert instance.machine.definition.machine == "EvolutionCampaign"

    def test_the_instance_is_a_real_evolution_campaign_machine_instance(self) -> None:
        """No second machine was minted: the instance's own definition is
        byte-identical to the canonical `evolution_campaign_state_machine`
        module's, not a look-alike built here."""
        declaration = declare_child_product_campaign(
            identity(), objective="x", baseline_metrics={"m": 1.0}, budgets=budgets(),
        )
        instance = begin_child_product_campaign(declaration)
        assert instance.machine.definition is ecsm.DEFINITION

    def test_the_guard_still_rejects_an_incomplete_declaration_context(self) -> None:
        """The real, unmodified `declaration_guard` still enforces its own
        rule (six distinct budget names) - not weakened for this caller."""
        instance = ecsm.build().start("DECLARED")
        with pytest.raises(GuardRejected):
            instance.apply("RUNNING", {"objective": "x", "baseline_metrics": {}})
