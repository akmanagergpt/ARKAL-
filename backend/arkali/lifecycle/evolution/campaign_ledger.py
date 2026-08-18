"""C-33 campaign ledger: successor eligibility and terminal-state derivation.

Owner: `lifecycle.evolution` (ARK-REQ-0140, ARK-REQ-0141, ARK-REQ-0142).

Mirrors `engineering.repair.contracts.RepairBudgetLedger`'s structural
shape - immutable, evidence-driven accounting that refuses before it can
overrun - at the campaign's own six budgets (`CampaignBudgets`) rather than a
single repair loop's six. A campaign-level ledger is a distinct C-33 record
(owner `lifecycle.evolution`) from a repair-loop ledger (owner
`engineering.repair`, C-26): if a campaign delegates an actual repair
sub-loop to that pipeline, the sub-loop keeps its own `RepairBudgetLedger`
unmodified; this ledger never re-derives that accounting.

ARK-REQ-0141 ("a rejected candidate does not auto-generate a successor") is
`may_generate_successor()`: true only while every budget dimension has
headroom and the no-progress threshold has not been reached. ARK-REQ-0140
("exactly one of four terminal states") is `terminal_state()`, honestly
derived from the ledger's own recorded facts - `PROMOTED` once any attempt
records that outcome, `COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN` when budget or
no-progress exhausts with the most recent attempt's baseline intact (no
regression), `ESCALATED` when it exhausts with a regression present. Mirrors
`HardeningRound`'s own canonical rule (`STATE_MACHINES.md` §11): "budget
exhaustion with an intact baseline yields COMPLETE_WITH_NO_FURTHER_MEASURED_
GAIN, otherwise ESCALATED." A campaign denied entry (unverified Recovery
Supervisor, PDP DENY) never reaches `RUNNING` and so never has a ledger at
all - `BLOCKED` is `CoreUpgrade`'s entry-guard concern, not this ledger's;
mirrors `CoreUpgrade`'s own "entry requires a verified Recovery Supervisor
... or the PDP returns DENY" (no ledger-side BLOCKED path exists to fabricate
one). ARK-REQ-0142 ("never restarted") is already structural in
`evolution_campaign_state_machine`'s kernel primitive - every terminal state
carries no outgoing transition, so `TerminalStateEscape` refuses any further
transition unconditionally; this module adds no restart path to refuse.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arkali.lifecycle.evolution.campaign_declaration import CampaignBudgets
from arkali.lifecycle.evolution.content_identity import address_of
from arkali.lifecycle.evolution.errors import (
    CampaignBudgetExceededError,
    CampaignStillRunningError,
)

CONTRACT_VERSION: Final[str] = "1.0.0"
Declared = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(ge=0)]

PROMOTED = "PROMOTED"
COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN = "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN"
ESCALATED = "ESCALATED"
CandidateOutcome = Declared


class CampaignConsumption(BaseModel):
    """Cumulative evidence measured against a declared `CampaignBudgets`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: Count = 0
    ai_calls: Count = 0
    elapsed_seconds: Count = 0
    cost: Annotated[Decimal, Field(ge=0)] = Decimal("0")
    regression_delta: Count = 0
    consecutive_no_progress: Count = 0


_CONSUMPTION_TO_BUDGET: Final[dict[str, str]] = {
    "candidates": "candidate_budget",
    "ai_calls": "ai_call_budget",
    "elapsed_seconds": "time_budget_seconds",
    "cost": "cost_budget",
    "regression_delta": "regression_ceiling",
    "consecutive_no_progress": "no_progress_threshold",
}


class CampaignAttempt(BaseModel):
    """Immutable record of one core-candidate attempt within the campaign."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: Declared
    outcome: CandidateOutcome
    measured_gain: bool
    regression_delta: Count


class CampaignLedger(BaseModel):
    """Immutable, evidence-driven accounting for one evolution campaign."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str = CONTRACT_VERSION
    campaign_id: Declared
    budgets: CampaignBudgets
    consumption: CampaignConsumption = CampaignConsumption()
    attempts: tuple[CampaignAttempt, ...] = ()

    @model_validator(mode="after")
    def _within_declared_budget(self) -> CampaignLedger:
        if self.contract_version.split(".")[0] != CONTRACT_VERSION.split(".")[0]:
            raise CampaignBudgetExceededError(
                f"contract major version {self.contract_version!r} is not readable"
            )
        exceeded = self.exceeded_dimensions()
        if exceeded:
            raise CampaignBudgetExceededError(
                "campaign budget exceeded: " + ", ".join(exceeded)
            )
        if len(self.attempts) != self.consumption.candidates:
            raise CampaignBudgetExceededError(
                "candidate consumption must equal the recorded attempt count"
            )
        return self

    def exceeded_dimensions(self) -> tuple[str, ...]:
        return tuple(
            consumed
            for consumed, budget in _CONSUMPTION_TO_BUDGET.items()
            if getattr(self.consumption, consumed) > getattr(self.budgets, budget)
        )

    def may_generate_successor(self) -> bool:
        """ARK-REQ-0141: only while every budget has headroom and the
        no-progress threshold has not been reached. A `PROMOTED` attempt ends
        the campaign outright - no successor follows a promotion either."""
        if any(attempt.outcome == PROMOTED for attempt in self.attempts):
            return False
        c, b = self.consumption, self.budgets
        return (
            c.candidates < b.candidate_budget
            and c.ai_calls <= b.ai_call_budget
            and c.elapsed_seconds <= b.time_budget_seconds
            and c.cost <= b.cost_budget
            and c.regression_delta <= b.regression_ceiling
            and c.consecutive_no_progress < b.no_progress_threshold
        )

    def terminal_state(self) -> str:
        """ARK-REQ-0140: exactly one of the honestly-derivable terminal
        states. Refuses while the campaign may still generate a successor -
        a terminal verdict is not guessed at while the campaign is live."""
        if any(attempt.outcome == PROMOTED for attempt in self.attempts):
            return PROMOTED
        if self.may_generate_successor():
            raise CampaignStillRunningError(
                f"campaign {self.campaign_id!r} may still generate a successor; "
                "no terminal state applies yet"
            )
        baseline_intact = not self.attempts or self.attempts[-1].regression_delta == 0
        return COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN if baseline_intact else ESCALATED

    def record(self, attempt: CampaignAttempt, *, ai_calls: int,
               elapsed_seconds: int, cost: Decimal) -> CampaignLedger:
        """Return a new ledger, or refuse the attempt before it can overrun a
        campaign already exhausted or already promoted (ARK-REQ-0141)."""
        if not self.may_generate_successor():
            raise CampaignBudgetExceededError(
                f"campaign {self.campaign_id!r} may not generate a successor: "
                "budget or no-progress threshold already reached, or already promoted"
            )
        current = self.consumption
        updated = CampaignConsumption(
            candidates=current.candidates + 1,
            ai_calls=current.ai_calls + ai_calls,
            elapsed_seconds=current.elapsed_seconds + elapsed_seconds,
            cost=current.cost + cost,
            regression_delta=current.regression_delta + attempt.regression_delta,
            consecutive_no_progress=(
                0 if attempt.measured_gain else current.consecutive_no_progress + 1
            ),
        )
        return type(self).model_validate(
            {
                **self.model_dump(),
                "consumption": updated,
                "attempts": (*self.attempts, attempt),
            }
        )

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def ledger_ref(self) -> str:
        return address_of(self.rendering())
