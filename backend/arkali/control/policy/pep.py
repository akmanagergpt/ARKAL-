"""Policy Enforcement Point (ARK-REQ-0096, 0097).

Owner: control.policy (Protected Core).

A PEP sits at every governed call site and is the only way a governed operation
may proceed. There is no bypass path: `enforce` either returns an audited
decision record or raises. It never returns a bare boolean, because a boolean
invites `if not allowed: pass`.

WHAT THIS PHASE CAN AND CANNOT CLAIM. Phase 4 implements the enforcement
*contract* and proves it deterministic. It cannot claim end-to-end bypass
resistance across API, UI, agent, workflow, plugin and computer-use surfaces,
because none of those surfaces exists yet. The contract is verified; the runtime
surfaces are NOT_YET_IMPLEMENTED, and the Phase 4 evidence says exactly that
rather than implying coverage it does not have.

`require_auto` exists for call sites that may only proceed unattended. ASK_USER
is not permission - it is a request for a human, and a caller that cannot ask one
must treat it as refusal.
"""

from __future__ import annotations

from arkali.control.policy.operation_class import Decision
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.policy_contract import PolicyDecisionRecord, PolicyRequest
from arkali.control.policy.policy_errors import PolicyDenied, PolicyBypassAttempt


class PolicyEnforcementPoint:
    """Guards one call site. Every governed operation passes through here."""

    def __init__(self, pdp: PolicyDecisionPoint, surface: str) -> None:
        if not surface.strip():
            raise PolicyBypassAttempt(
                "a PEP must name the surface it guards; an unnamed enforcement "
                "point cannot be audited"
            )
        self._pdp = pdp
        self.surface = surface
        self._audit: list[PolicyDecisionRecord] = []

    @property
    def audit_trail(self) -> tuple[PolicyDecisionRecord, ...]:
        """Every decision, including AUTO (SECURITY_ARCHITECTURE.md §1)."""
        return tuple(self._audit)

    def evaluate(self, request: PolicyRequest) -> PolicyDecisionRecord:
        """Decide and audit, without raising. Use when a DENY is a valid answer."""
        record = self._pdp.decide(request)
        self._audit.append(record)
        return record

    def enforce(self, request: PolicyRequest) -> PolicyDecisionRecord:
        """Decide, audit, and refuse anything that is not permitted.

        ASK_USER is returned rather than raised: it is a legitimate outcome that
        the caller must resolve with a human. Only DENY raises.
        """
        record = self.evaluate(request)
        if record.decision is Decision.DENY:
            raise PolicyDenied(
                f"{self.surface}: {record.render()} - {record.reason}",
                source=record.authoritative_source,
            )
        return record

    def require_auto(self, request: PolicyRequest) -> PolicyDecisionRecord:
        """For unattended call sites: anything short of AUTO is refused."""
        record = self.enforce(request)
        if not record.permits_execution:
            raise PolicyDenied(
                f"{self.surface}: {record.render()} requires a human decision; "
                "this call site cannot obtain one",
                source=record.authoritative_source,
            )
        return record
