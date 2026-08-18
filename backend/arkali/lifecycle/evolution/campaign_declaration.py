"""C-33 campaign declaration: objective, baseline and the six MS budgets.

Owner: `lifecycle.evolution` (ARK-REQ-0139).

MS "ARKALI Self-Evolution" names the six budgets a campaign must declare
before execution: candidate budget, AI-call budget, time budget, cost budget,
a regression ceiling and a no-progress threshold. `evolution_campaign_state_
machine.declaration_guard` only checks that `context["budgets"]` carries six
*distinct* entries - a generic, machine-primitive-level property, since the
kernel guard cannot know the canonical six names without becoming a second
copy of this context's own vocabulary. `CampaignBudgets` is that vocabulary:
a frozen model with exactly the six MS fields, so its field names are the
"six budgets" by construction and cannot silently become six different
strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from arkali.kernel.contracts.content_address import address_of

CONTRACT_VERSION: Final[str] = "1.0.0"
Declared = Annotated[str, Field(min_length=1)]
PositiveCount = Annotated[int, Field(gt=0)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=0)]


class CampaignBudgets(BaseModel):
    """The six budgets MS "ARKALI Self-Evolution" requires before execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_budget: PositiveCount
    ai_call_budget: PositiveCount
    time_budget_seconds: PositiveCount
    cost_budget: NonNegativeDecimal
    regression_ceiling: Annotated[int, Field(ge=0)]
    no_progress_threshold: PositiveCount

    @property
    def names(self) -> tuple[str, ...]:
        """The six field names - always distinct, always these six."""
        return tuple(type(self).model_fields)


class CampaignDeclaration(BaseModel):
    """One evolution campaign's pre-execution declaration (C-33).

    Constructing this is the whole of "declares objective, baseline and six
    budgets before execution" (ARK-REQ-0139); `guard_context()` is the only
    path a caller has to satisfy `declaration_guard`, so the guard can never
    be satisfied by a hand-built dict that skips real typed budgets.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str = CONTRACT_VERSION
    campaign_id: Declared
    objective: Declared
    baseline_metrics: Mapping[str, float]
    budgets: CampaignBudgets

    @field_validator("baseline_metrics")
    @classmethod
    def _non_empty_baseline(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        if not value:
            raise ValueError("a campaign must declare at least one baseline metric")
        return value

    def guard_context(self) -> dict[str, object]:
        """The exact fact set `evolution_campaign_state_machine.declaration_guard`
        reads - objective, baseline metrics and the six distinct budget names."""
        return {
            "objective": self.objective,
            "baseline_metrics": dict(self.baseline_metrics),
            "budgets": self.budgets.names,
        }

    def rendering(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode("utf-8")

    @property
    def campaign_ref(self) -> str:
        """Content-addressed identity of this declaration (C-33 evidence key)."""
        return address_of(self.rendering())
