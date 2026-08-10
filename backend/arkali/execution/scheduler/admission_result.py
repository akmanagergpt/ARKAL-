"""The C-21 admission answer.

Owner: `execution.scheduler`.

WHY NOT A BOOLEAN. `EXECUTION_AND_CAPABILITY.md` §4 gives admission three
independent conditions, and each fails for a different governed reason. A bare
`False` would erase which authority refused, so a caller could not tell "the
capability graph is not activated yet" from "this host cannot satisfy TRUST-2"
from "the concurrency limit is reached". Those need different responses, and one
of them is expected to be permanent until Phase 9B.

THIS IS NOT A STATE MACHINE. An `AdmissionDecision` is a value returned by one
evaluation. It has no lifecycle, no transitions and no persistence: two
evaluations of the same request produce two independent values, and nothing
records that either happened. `execution.scheduler` declares no state machine and
the canonical count stays at 12.

THE REASON IS THE AUTHORITY'S, NOT OURS. Each refusal carries the text produced
by the context that refused - the capability graph, `control.isolation`, or the
resource assessment. Nothing here rewrites a canonical reason into a friendlier
one, because the reason is evidence.
"""

from __future__ import annotations

import enum
from typing import Final

from pydantic import BaseModel, ConfigDict

CANONICAL_SOURCE: Final[str] = (
    "docs/canonical/EXECUTION_AND_CAPABILITY.md §4 (admission control)"
)


class AdmissionOutcome(str, enum.Enum):
    """The canonical §4 conditions, plus the one way all three can hold.

    Exactly one member per condition. There is no fourth condition and no
    partial or provisional outcome: §4 admits a job only when all three hold.
    """

    ADMITTED = "ADMITTED"
    CAPABILITY_NOT_CONFIGURED = "CAPABILITY_NOT_CONFIGURED"
    ISOLATION_UNSATISFIED = "ISOLATION_UNSATISFIED"
    RESOURCE_UNAVAILABLE = "RESOURCE_UNAVAILABLE"

    @property
    def admits(self) -> bool:
        return self is AdmissionOutcome.ADMITTED


class AdmissionDecision(BaseModel):
    """One deterministic admission answer, with the reason that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_class: str
    capability_id: str
    outcome: AdmissionOutcome
    reason: str
    authoritative_source: str = CANONICAL_SOURCE

    @property
    def admitted(self) -> bool:
        """Only ADMITTED admits. Every other outcome is a refusal."""
        return self.outcome.admits

    def render(self) -> str:
        return (
            f"{self.outcome.value} worker_class={self.worker_class} "
            f"capability={self.capability_id}: {self.reason}"
        )
