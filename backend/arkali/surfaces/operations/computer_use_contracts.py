"""C-34 Computer-Use decision value object (ARK-REQ-0170).

Owner: `surfaces.operations`.

ONE DECISION SHAPE, PRIMITIVE FIELDS ONLY. `decision` carries the literal
`Decision.value` string (`"AUTO"`/`"ASK_USER"`/`"DENY"`) the real PDP already
returns - never a second enum invented here, and never the concrete
`control.policy` types themselves (see `computer_use.py`'s own docstring for
why: `control.policy.pep`/`.policy_contract` are both already at their
15-of-15 fan-in ceiling).
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict

AUTO: Final[str] = "AUTO"
ASK_USER: Final[str] = "ASK_USER"
DENY: Final[str] = "DENY"


class ComputerUseDecision(BaseModel):
    """The real PDP's answer for one Computer-Use action, as primitives."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation_class: str
    decision: str
    reason: str
    required_human_gate: str | None = None

    @property
    def permits_execution(self) -> bool:
        """`ASK_USER` is not permission. Only `AUTO` permits without a
        human - the identical rule `policy_contract.PolicyDecisionRecord.
        permits_execution` already states for the concrete type."""
        return self.decision == AUTO

    def render(self) -> str:
        gate = f" gate={self.required_human_gate}" if self.required_human_gate else ""
        return f"{self.decision} {self.operation_class} reason={self.reason!r}{gate}"


__all__ = ["ComputerUseDecision", "AUTO", "ASK_USER", "DENY"]
