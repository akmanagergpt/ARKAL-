"""C-18 phase gate verdict contract.

Owner: acceptance.engine (Protected Core).

A verdict is the deterministic output of the Phase Gate Checker. It is written
to the evidence store and is never re-scored by an implementing actor
(ARK-REQ-0205).
"""

from __future__ import annotations

import enum
import json

from pydantic import BaseModel, ConfigDict, Field

from arkali.kernel.contracts.results import CheckResult, Finding, HonestState


class Verdict(str, enum.Enum):
    """The only legal checker outcomes."""

    PHASE_ACCEPTED_BY_MACHINE = "PHASE_ACCEPTED_BY_MACHINE"
    PHASE_BLOCKED = "PHASE_BLOCKED"
    AWAITING_HUMAN_GATE = "AWAITING_HUMAN_GATE"
    #: The phase already carries an acceptance record and no valid re-scoring
    #: authorization covers this evidence package (GOV-001, closes F-0026).
    #: Distinct from AWAITING_HUMAN_GATE: that is a gate the phase always
    #: carried, this is permission to supersede a verdict already issued.
    AWAITING_RESCORING_AUTHORITY = "AWAITING_RESCORING_AUTHORITY"


class GateVerdict(BaseModel):
    """Machine-readable verdict plus the evidence that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase_id: str
    requested_next_phase: str | None
    verdict: Verdict
    checks: tuple[CheckResult, ...]
    findings: tuple[Finding, ...] = Field(default_factory=tuple)
    human_gate_required: str | None = None
    progression_permitted: bool = False
    failing_condition: str = ""

    def to_json(self) -> str:
        """Stable serialisation: sorted keys, fixed separators.

        Two runs over identical repository state must produce byte-identical
        output, which is what the determinism test asserts.
        """
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )

    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.state is HonestState.FAIL)

    def render(self) -> str:
        """Human-readable evidence rendering, stable ordering."""
        lines = [
            f"phase           : {self.phase_id}",
            f"requested next  : {self.requested_next_phase or '-'}",
            f"verdict         : {self.verdict.value}",
            f"progression     : {'PERMITTED' if self.progression_permitted else 'STOPPED'}",
        ]
        if self.human_gate_required:
            lines.append(f"human gate      : {self.human_gate_required} REQUIRED")
        if self.failing_condition:
            lines.append(f"failing condition: {self.failing_condition}")
        lines.append("checks:")
        for check in self.checks:
            lines.append(f"  {check.state.value:20s} {check.check_id}: {check.summary}")
        if self.findings:
            lines.append("findings:")
            for finding in sorted(self.findings, key=lambda f: f.sort_key()):
                lines.append(f"  {finding.severity.value:13s} {finding.code}: {finding.summary}")
        return "\n".join(lines)
