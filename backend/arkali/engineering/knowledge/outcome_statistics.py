"""C-28 per-model, per-task-class empirical outcome statistics (ARK-REQ-0394,
D-026).

D-026: "only VERIFIED outcomes — never a model's self-reported claim — may
update routing knowledge." `VerifiedOutcome.evidence` is typed
`contracts.EvidenceReference` — the identical structural exclusion of
`SelfReportedClaim` that `KnowledgeRecord` uses, not a second copy of the
rule. `aggregate` is a pure function over whatever `VerifiedOutcome`
sequence its caller supplies: nothing is cached, nothing is stored, and
calling it twice with different input produces different output — the same
"nothing is cached at any layer" shape `control.capability` (C-13)
established. This module records no execution-routing decision and does
not modify `engineering.factory.execution_routing`'s `VERIFIED_KNOWLEDGE`
tier; wiring a live statistics source into that tier is a future caller's
composition, per that module's own documented deferral.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.engineering.knowledge.contracts import EvidenceReference

Declared = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(ge=0)]


class VerifiedOutcome(BaseModel):
    """One verified execution outcome for one model on one task class."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    model_id: Declared
    task_class: Declared
    succeeded: bool
    evidence: EvidenceReference


class EmpiricalOutcomeStats(BaseModel):
    """Aggregated (model_id, task_class) statistics, derived only from
    `VerifiedOutcome` records."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: Declared
    task_class: Declared
    attempts: Count
    successes: Count

    @property
    def success_rate(self) -> Decimal:
        if self.attempts == 0:
            return Decimal("0")
        return Decimal(self.successes) / Decimal(self.attempts)


def aggregate(outcomes: Sequence[VerifiedOutcome]) -> tuple[EmpiricalOutcomeStats, ...]:
    """Deterministic (model_id, task_class) aggregation over `outcomes`.
    Returned in sorted key order so two callers passing the same set in a
    different order observe an identical result."""
    grouped: dict[tuple[str, str], list[VerifiedOutcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[(outcome.model_id, outcome.task_class)].append(outcome)

    stats: Final[list[EmpiricalOutcomeStats]] = [
        EmpiricalOutcomeStats(
            model_id=model_id,
            task_class=task_class,
            attempts=len(entries),
            successes=sum(1 for entry in entries if entry.succeeded),
        )
        for (model_id, task_class), entries in grouped.items()
    ]
    return tuple(sorted(stats, key=lambda item: (item.model_id, item.task_class)))
