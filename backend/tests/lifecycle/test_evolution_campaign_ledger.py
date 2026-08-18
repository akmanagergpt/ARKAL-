"""C-33 campaign ledger: successor eligibility + terminal state
(ARK-REQ-0140, ARK-REQ-0141, ARK-REQ-0142). Stage A/B.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from arkali.kernel.contracts.content_address import is_address
from arkali.kernel.contracts.state_machine_errors import TerminalStateEscape
from arkali.lifecycle.evolution import evolution_campaign_state_machine as ecsm
from arkali.lifecycle.evolution.campaign_declaration import CampaignBudgets
from arkali.lifecycle.evolution.campaign_ledger import (
    COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN,
    ESCALATED,
    PROMOTED,
    CampaignAttempt,
    CampaignLedger,
)
from arkali.lifecycle.evolution.errors import (
    CampaignBudgetExceededError,
    CampaignStillRunningError,
)


def tight_budgets(**updates: object) -> CampaignBudgets:
    values: dict[str, object] = {
        "candidate_budget": 2,
        "ai_call_budget": 10,
        "time_budget_seconds": 600,
        "cost_budget": Decimal("5.00"),
        "regression_ceiling": 3,
        "no_progress_threshold": 2,
    }
    values.update(updates)
    return CampaignBudgets.model_validate(values)


def ledger(**updates: object) -> CampaignLedger:
    values: dict[str, object] = {
        "campaign_id": "campaign-23-001",
        "budgets": tight_budgets(),
    }
    values.update(updates)
    return CampaignLedger.model_validate(values)


def attempt(candidate_id: str = "candidate-1", outcome: str = "REJECTED",
            measured_gain: bool = False, regression_delta: int = 0) -> CampaignAttempt:
    return CampaignAttempt(
        candidate_id=candidate_id, outcome=outcome,
        measured_gain=measured_gain, regression_delta=regression_delta,
    )


class TestCampaignLedgerAccounting:
    def test_record_returns_new_evidence_and_preserves_the_prior_ledger(self) -> None:
        original = ledger()
        recorded = original.record(
            attempt(), ai_calls=1, elapsed_seconds=30, cost=Decimal("0.25"),
        )
        assert original.consumption.candidates == 0
        assert recorded.consumption.candidates == 1
        assert recorded.attempts == (attempt(),)
        assert is_address(recorded.ledger_ref)

    def test_immutable_and_deterministic(self) -> None:
        first = ledger()
        second = ledger()
        assert first.rendering() == second.rendering()
        assert first.ledger_ref == second.ledger_ref
        with pytest.raises(ValidationError):
            first.campaign_id = "changed"  # type: ignore[misc]


class TestMayGenerateSuccessor:
    """ARK-REQ-0141: a rejected candidate does not auto-generate a successor
    once budget or the no-progress threshold is exhausted."""

    def test_a_fresh_campaign_may_generate_a_successor(self) -> None:
        assert ledger().may_generate_successor() is True

    def test_candidate_budget_exhaustion_refuses_a_successor(self) -> None:
        one = ledger().record(
            attempt("candidate-1"), ai_calls=0, elapsed_seconds=1, cost=Decimal("0"),
        )
        two = one.record(
            attempt("candidate-2"), ai_calls=0, elapsed_seconds=1, cost=Decimal("0"),
        )
        assert two.consumption.candidates == 2  # == candidate_budget
        assert two.may_generate_successor() is False
        with pytest.raises(CampaignBudgetExceededError):
            two.record(
                attempt("candidate-3"), ai_calls=0, elapsed_seconds=1, cost=Decimal("0"),
            )

    def test_no_progress_threshold_refuses_a_successor_before_budget_exhausts(
        self,
    ) -> None:
        generous = ledger(budgets=tight_budgets(candidate_budget=10))
        one = generous.record(
            attempt("candidate-1", measured_gain=False), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"),
        )
        two = one.record(
            attempt("candidate-2", measured_gain=False), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"),
        )
        assert two.consumption.consecutive_no_progress == 2  # == no_progress_threshold
        assert two.consumption.candidates == 2  # well under candidate_budget=10
        assert two.may_generate_successor() is False

    def test_a_measured_gain_resets_the_no_progress_counter(self) -> None:
        generous = ledger(budgets=tight_budgets(candidate_budget=10))
        one = generous.record(
            attempt("candidate-1", measured_gain=False), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"),
        )
        two = one.record(
            attempt("candidate-2", measured_gain=True), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"),
        )
        assert two.consumption.consecutive_no_progress == 0
        assert two.may_generate_successor() is True

    def test_a_promoted_attempt_ends_the_campaign_even_with_budget_remaining(
        self,
    ) -> None:
        generous = ledger(budgets=tight_budgets(candidate_budget=10))
        promoted = generous.record(
            attempt("candidate-1", outcome=PROMOTED, measured_gain=True),
            ai_calls=0, elapsed_seconds=1, cost=Decimal("0"),
        )
        assert promoted.may_generate_successor() is False
        with pytest.raises(CampaignBudgetExceededError):
            promoted.record(
                attempt("candidate-2"), ai_calls=0, elapsed_seconds=1, cost=Decimal("0"),
            )

    @pytest.mark.parametrize(
        ("field", "kwargs"),
        (
            ("ai_calls", {"ai_calls": 11, "elapsed_seconds": 1, "cost": Decimal("0")}),
            ("elapsed_seconds", {"ai_calls": 0, "elapsed_seconds": 601, "cost": Decimal("0")}),
            ("cost", {"ai_calls": 0, "elapsed_seconds": 1, "cost": Decimal("5.01")}),
        ),
    )
    def test_each_measured_dimension_fails_closed(
        self, field: str, kwargs: dict[str, object],
    ) -> None:
        with pytest.raises(CampaignBudgetExceededError, match=field):
            ledger().record(attempt(), **kwargs)  # type: ignore[arg-type]


class TestTerminalState:
    """ARK-REQ-0140: exactly one of the four terminal states, honestly derived."""

    def test_still_running_refuses_a_terminal_verdict(self) -> None:
        with pytest.raises(CampaignStillRunningError):
            ledger().terminal_state()

    def test_a_promoted_attempt_yields_promoted(self) -> None:
        generous = ledger(budgets=tight_budgets(candidate_budget=10))
        promoted = generous.record(
            attempt("candidate-1", outcome=PROMOTED, measured_gain=True),
            ai_calls=0, elapsed_seconds=1, cost=Decimal("0"),
        )
        assert promoted.terminal_state() == PROMOTED

    def test_exhaustion_with_an_intact_baseline_yields_no_further_gain(self) -> None:
        one = ledger().record(
            attempt("candidate-1", regression_delta=0), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"),
        )
        two = one.record(
            attempt("candidate-2", regression_delta=0), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"),
        )
        assert two.may_generate_successor() is False
        assert two.terminal_state() == COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN

    def test_exhaustion_with_a_regression_present_yields_escalated(self) -> None:
        one = ledger().record(
            attempt("candidate-1", regression_delta=0), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"),
        )
        two = one.record(
            attempt("candidate-2", regression_delta=1), ai_calls=0,
            elapsed_seconds=1, cost=Decimal("0"),
        )
        assert two.may_generate_successor() is False
        assert two.terminal_state() == ESCALATED

    def test_terminal_state_is_never_a_fifth_value(self) -> None:
        canonical = {PROMOTED, COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN, ESCALATED}
        machine_terminals = set(ecsm.DEFINITION.terminal)
        assert canonical <= machine_terminals


class TestNoRestart:
    """ARK-REQ-0142: structural in the kernel primitive - proven here against
    the real `EvolutionCampaign` machine so the property is tied to this
    context's own machine, not just the generic kernel test."""

    def test_a_terminal_evolution_campaign_cannot_transition_again(self) -> None:
        machine = ecsm.build().start("DECLARED")
        machine.apply("RUNNING", {
            "objective": "x", "baseline_metrics": {"m": 1.0},
            "budgets": tight_budgets().names,
        })
        machine.apply(PROMOTED)
        assert machine.is_terminal is True
        with pytest.raises(TerminalStateEscape):
            machine.apply("RUNNING")
