"""Architecture gate base contract.

Owner: control.architecture (Protected Core).

Each gate derives its definition from an authoritative source and reports a
deterministic result. A gate with nothing meaningful to evaluate must return
NOT_APPLICABLE with a justification - never a vacuous PASS.
"""

from __future__ import annotations

import abc
import pathlib
from typing import Final

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.kernel.contracts.results import CheckResult, Finding, HonestState, Severity

#: Every gate threshold in the canonical map is zero-tolerance.
ZERO: Final[int] = 0


class GateContext:
    """Immutable inputs shared by all gates."""

    def __init__(self, repo_root: pathlib.Path, authority_map: AuthorityMap) -> None:
        self.repo_root = repo_root
        self.authority_map = authority_map


class ArchitectureGate(abc.ABC):
    """One canonical architecture gate."""

    #: Stable identifier, must match an id in AUTHORITY_MAP.architecture_gates.
    gate_id: str = ""
    #: Where the gate's definition comes from.
    authoritative_source: str = ""

    @abc.abstractmethod
    def evaluate(self, ctx: GateContext) -> CheckResult:
        """Deterministic evaluation. Must not mutate any input."""

    # -- helpers shared by concrete gates -------------------------------------

    def _violation(self, summary: str, detail: str = "") -> Finding:
        return Finding(
            code=f"GATE-{self.gate_id}",
            severity=Severity.HIGH,
            summary=summary,
            detail=detail,
            source=self.authoritative_source,
        )

    def _result(
        self,
        state: HonestState,
        summary: str,
        detail: str = "",
        findings: tuple[Finding, ...] = (),
    ) -> CheckResult:
        return CheckResult(
            check_id=self.gate_id,
            state=state,
            summary=summary,
            detail=detail,
            authoritative_source=self.authoritative_source,
            findings=findings,
        )

    def _from_violations(
        self, violations: list[str], pass_summary: str, fail_summary: str
    ) -> CheckResult:
        """PASS iff the violation list is empty. Ordering is stabilised."""
        ordered = sorted(violations)
        if not ordered:
            return self._result(HonestState.PASS, pass_summary, f"violations={ZERO}")
        return self._result(
            HonestState.FAIL,
            fail_summary,
            f"violations={len(ordered)}",
            tuple(self._violation(v) for v in ordered),
        )
