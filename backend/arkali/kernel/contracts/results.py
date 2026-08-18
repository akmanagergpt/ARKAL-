"""Canonical honest states and the deterministic Result model.

Authoritative source: CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md (Honest states)
and ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md (Direct-AI benchmark
states). The member list is fixed by the canonical set; it is not extended here.

`HonestState` itself now lives in `honest_state.py` (ADR-0008 decomposition,
the `error_base.py` -> `contract_violation_base.py` shape) and is re-exported
here unchanged, so every existing importer of this module is untouched.
"""

from __future__ import annotations

import enum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.kernel.contracts.honest_state import HonestState

__all__ = [
    "HonestState", "PROGRESSING_STATES", "NON_PASS_STATES", "Severity",
    "ACCEPTANCE_STOPPING", "Finding", "CheckResult",
]

#: States that permit progression. Everything else stops it.
PROGRESSING_STATES: Final[frozenset[HonestState]] = frozenset(
    {HonestState.PASS, HonestState.NOT_APPLICABLE}
)

#: States that must never be produced by converting a non-PASS state (ARK-REQ-0216).
NON_PASS_STATES: Final[frozenset[HonestState]] = frozenset(
    set(HonestState) - {HonestState.PASS}
)


class Severity(str, enum.Enum):
    """Finding severity. BLOCKER and HIGH stop phase acceptance."""

    BLOCKER = "BLOCKER"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFORMATIONAL = "INFORMATIONAL"


ACCEPTANCE_STOPPING: Final[frozenset[Severity]] = frozenset(
    {Severity.BLOCKER, Severity.HIGH}
)


class Finding(BaseModel):
    """A single defect. Immutable once constructed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: Severity
    summary: str
    detail: str = ""
    source: str = ""

    def sort_key(self) -> tuple[str, str]:
        return (self.severity.value, self.code)


class CheckResult(BaseModel):
    """Deterministic result of one governance check.

    `state` is an honest state, never a boolean, so a check that could not run is
    distinguishable from one that ran and passed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    check_id: str
    state: HonestState
    summary: str
    detail: str = ""
    authoritative_source: str = ""
    findings: tuple[Finding, ...] = Field(default_factory=tuple)

    @property
    def is_progressing(self) -> bool:
        return self.state in PROGRESSING_STATES

    @property
    def stopping_findings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity in ACCEPTANCE_STOPPING)
