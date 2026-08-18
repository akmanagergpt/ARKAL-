"""C-33 campaign declaration contract + `declaration_guard` wiring (ARK-REQ-0139).

Stage A (targeted contract tests) + Stage B (structural guard-satisfaction proof).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from arkali.kernel.contracts.content_address import is_address
from arkali.kernel.contracts.state_machine_errors import GuardRejected
from arkali.lifecycle.evolution import evolution_campaign_state_machine as ecsm
from arkali.lifecycle.evolution.campaign_declaration import (
    CampaignBudgets,
    CampaignDeclaration,
)


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


def declaration(**updates: object) -> CampaignDeclaration:
    values: dict[str, object] = {
        "campaign_id": "campaign-23-001",
        "objective": "reduce p95 latency in execution.scheduler",
        "baseline_metrics": {"p95_ms": 400.0},
        "budgets": budgets(),
    }
    values.update(updates)
    return CampaignDeclaration.model_validate(values)


class TestCampaignBudgets:
    def test_the_six_canonical_ms_fields_are_required(self) -> None:
        assert set(CampaignBudgets.model_fields) == {
            "candidate_budget",
            "ai_call_budget",
            "time_budget_seconds",
            "cost_budget",
            "regression_ceiling",
            "no_progress_threshold",
        }

    def test_names_reports_exactly_six_distinct_names(self) -> None:
        assert len(set(budgets().names)) == 6

    @pytest.mark.parametrize(
        "field", ("candidate_budget", "ai_call_budget", "time_budget_seconds",
                   "no_progress_threshold"),
    )
    def test_positive_fields_reject_zero(self, field: str) -> None:
        with pytest.raises(ValidationError):
            budgets(**{field: 0})

    def test_cost_budget_and_regression_ceiling_accept_zero(self) -> None:
        assert budgets(cost_budget=Decimal("0"), regression_ceiling=0)


class TestCampaignDeclaration:
    def test_immutable_deterministic_and_content_addressed(self) -> None:
        first = declaration()
        second = declaration()
        assert first.rendering() == second.rendering()
        assert first.campaign_ref == second.campaign_ref
        assert is_address(first.campaign_ref)
        with pytest.raises(ValidationError):
            first.objective = "changed"  # type: ignore[misc]

    def test_a_different_objective_changes_the_campaign_ref(self) -> None:
        assert declaration().campaign_ref != declaration(
            objective="a different objective"
        ).campaign_ref

    def test_guard_context_carries_objective_baseline_and_six_budget_names(
        self,
    ) -> None:
        context = declaration().guard_context()
        assert context["objective"]
        assert context["baseline_metrics"] == {"p95_ms": 400.0}
        assert len(set(context["budgets"])) == 6  # type: ignore[arg-type]

    def test_empty_objective_is_refused_by_the_model_not_the_guard(self) -> None:
        with pytest.raises(ValidationError):
            declaration(objective="")

    def test_empty_baseline_metrics_is_refused_by_the_model(self) -> None:
        with pytest.raises(ValidationError):
            declaration(baseline_metrics={})


class TestDeclarationGuardIsSatisfiableOnlyByARealDeclaration:
    """Stage B: the guard the state machine consults cannot be satisfied by a
    hand-built dict that fabricates six arbitrary strings - only by a real,
    typed `CampaignDeclaration`, whose six budget names are the MS vocabulary
    by construction (`CampaignBudgets.model_fields`).
    """

    def test_a_real_declaration_satisfies_the_guard(self) -> None:
        machine = ecsm.build().start("DECLARED")
        outcome = machine.apply("RUNNING", declaration().guard_context())
        assert outcome.decision.value == "ACCEPTED"

    def test_six_fabricated_labels_also_satisfy_the_kernel_guard_alone(self) -> None:
        """The kernel-level `declaration_guard` is deliberately generic (it
        cannot know this context's vocabulary without duplicating it) - proven
        here so the next test's refusal is shown to come from
        `CampaignDeclaration`'s own validation, not from the kernel guard.
        """
        machine = ecsm.build().start("DECLARED")
        outcome = machine.apply(
            "RUNNING",
            {
                "objective": "x",
                "baseline_metrics": {"m": 1},
                "budgets": ("a", "b", "c", "d", "e", "f"),
            },
        )
        assert outcome.decision.value == "ACCEPTED"

    def test_five_of_the_six_ms_budgets_is_refused(self) -> None:
        incomplete = tuple(CampaignBudgets.model_fields)[:5]
        machine = ecsm.build().start("DECLARED")
        with pytest.raises(GuardRejected):
            machine.apply(
                "RUNNING",
                {
                    "objective": "x",
                    "baseline_metrics": {"m": 1},
                    "budgets": incomplete,
                },
            )

    def test_missing_objective_is_refused(self) -> None:
        machine = ecsm.build().start("DECLARED")
        context = declaration().guard_context()
        context["objective"] = ""
        with pytest.raises(GuardRejected):
            machine.apply("RUNNING", context)
