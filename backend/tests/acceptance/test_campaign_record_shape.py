"""ARK-REQ-0360: an evolution run's outcome is FAIL without a bounded
campaign record. Proves `campaign_record_shape._check_campaign_record_shape`
both against fabricated primitive shapes and against a real, composed
`lifecycle.evolution` campaign - `acceptance.engine` cannot import that
context (layer direction), but this test file sits outside the graph and
can, so it is the one place the two are proven compatible.
"""

from __future__ import annotations

import json
from decimal import Decimal

from arkali.acceptance.campaign_record_shape import (
    REQUIRED_BUDGET_NAMES,
    TERMINAL_STATES,
    _check_campaign_record_shape,
)
from arkali.lifecycle.evolution import evolution_campaign_state_machine as ecsm
from arkali.lifecycle.evolution.campaign_declaration import (
    CampaignBudgets,
    CampaignDeclaration,
)
from arkali.lifecycle.evolution.campaign_ledger import (
    PROMOTED,
    CampaignAttempt,
    CampaignLedger,
)


def real_declaration() -> CampaignDeclaration:
    return CampaignDeclaration(
        campaign_id="campaign-23-shape",
        objective="reduce p95 latency",
        baseline_metrics={"p95_ms": 400.0},
        budgets=CampaignBudgets(
            candidate_budget=3, ai_call_budget=10, time_budget_seconds=600,
            cost_budget=Decimal("5.00"), regression_ceiling=0, no_progress_threshold=2,
        ),
    )


class TestBoundedShapeIsAccepted:
    def test_a_complete_record_is_accepted(self) -> None:
        declaration = {
            "objective": "reduce p95 latency",
            "baseline_metrics": {"p95_ms": 400.0},
            "budgets": {name: 1 for name in REQUIRED_BUDGET_NAMES},
        }
        outcome = {"terminal_state": "PROMOTED"}
        assert _check_campaign_record_shape(declaration, outcome) is None


class TestUnboundedShapeIsRefused:
    def test_no_objective_is_refused(self) -> None:
        declaration = {
            "objective": "", "baseline_metrics": {"m": 1},
            "budgets": {name: 1 for name in REQUIRED_BUDGET_NAMES},
        }
        refusal = _check_campaign_record_shape(declaration, {"terminal_state": "PROMOTED"})
        assert refusal is not None
        assert "no objective" in refusal[0]

    def test_no_baseline_metrics_is_refused(self) -> None:
        declaration = {
            "objective": "x", "baseline_metrics": {},
            "budgets": {name: 1 for name in REQUIRED_BUDGET_NAMES},
        }
        refusal = _check_campaign_record_shape(declaration, {"terminal_state": "PROMOTED"})
        assert refusal is not None
        assert "no baseline metrics" in refusal[0]

    def test_missing_a_budget_is_refused(self) -> None:
        incomplete = {name: 1 for name in sorted(REQUIRED_BUDGET_NAMES)[:5]}
        declaration = {
            "objective": "x", "baseline_metrics": {"m": 1}, "budgets": incomplete,
        }
        refusal = _check_campaign_record_shape(declaration, {"terminal_state": "PROMOTED"})
        assert refusal is not None
        assert "six canonical budgets" in refusal[0]

    def test_an_extra_unrecognised_budget_is_refused(self) -> None:
        extra = {name: 1 for name in REQUIRED_BUDGET_NAMES}
        extra["a_seventh_budget"] = 1
        declaration = {
            "objective": "x", "baseline_metrics": {"m": 1}, "budgets": extra,
        }
        refusal = _check_campaign_record_shape(declaration, {"terminal_state": "PROMOTED"})
        assert refusal is not None
        assert "six canonical budgets" in refusal[0]

    def test_no_terminal_state_is_refused(self) -> None:
        declaration = {
            "objective": "x", "baseline_metrics": {"m": 1},
            "budgets": {name: 1 for name in REQUIRED_BUDGET_NAMES},
        }
        refusal = _check_campaign_record_shape(declaration, {})
        assert refusal is not None
        assert "no genuine terminal state" in refusal[0]

    def test_a_fabricated_terminal_state_is_refused(self) -> None:
        declaration = {
            "objective": "x", "baseline_metrics": {"m": 1},
            "budgets": {name: 1 for name in REQUIRED_BUDGET_NAMES},
        }
        refusal = _check_campaign_record_shape(
            declaration, {"terminal_state": "SUCCESSFULLY_DONE"}
        )
        assert refusal is not None


class TestCompatibilityWithTheRealCampaignObjects:
    """The primitive shape this module checks is exactly what
    `CampaignDeclaration`/`CampaignLedger` really render - proven by driving
    a real campaign to a real terminal state and checking its own output."""

    def test_a_real_declaration_and_a_real_promoted_ledger_are_accepted(self) -> None:
        declaration = real_declaration()
        ledger = CampaignLedger(campaign_id=declaration.campaign_id, budgets=declaration.budgets)
        ledger = ledger.record(
            CampaignAttempt(
                candidate_id="cand-1", outcome=PROMOTED, measured_gain=True,
                regression_delta=0,
            ),
            ai_calls=1, elapsed_seconds=10, cost=Decimal("0.10"),
        )

        declaration_shape = json.loads(declaration.rendering())
        outcome_shape = {"terminal_state": ledger.terminal_state()}
        assert _check_campaign_record_shape(declaration_shape, outcome_shape) is None

    def test_a_real_declaration_missing_from_the_shape_is_still_refused(self) -> None:
        """A caller presenting only the ledger's outcome, with no real
        declaration behind it, is refused - the shape check does not trust
        an outcome that arrived without its own bounded declaration."""
        assert _check_campaign_record_shape({}, {"terminal_state": PROMOTED}) is not None


class TestConstantsStayReconciledWithTheirRealAuthorities:
    """`acceptance.engine` cannot import `lifecycle.evolution` (layer
    direction), so its restated budget/terminal-state vocabularies could
    silently drift from the real ones. This is the one place - outside the
    context graph - that proves they have not."""

    def test_required_budget_names_matches_campaign_budgets_fields(self) -> None:
        assert REQUIRED_BUDGET_NAMES == frozenset(CampaignBudgets.model_fields)

    def test_terminal_states_matches_the_real_evolution_campaign_machine(self) -> None:
        assert TERMINAL_STATES == frozenset(ecsm.DEFINITION.terminal)
