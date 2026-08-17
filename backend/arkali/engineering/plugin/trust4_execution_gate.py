"""TRUST-4 execution gate: isolation + human approval per execution
(ARK-REQ-0117).

Owner (this composition point): engineering.plugin. Owner of the two
authorities composed: control.isolation and control.policy (both Protected
Core, both reused unmodified) - the identical composition
`engineering.import.execution_gate` established for TRUST-3 (ARK-REQ-0116,
Phase 19), rebound to TRUST-4 and to a stricter binding.

WHY "PER EXECUTION" IS A DIFFERENT BINDING, NOT A DIFFERENT MECHANISM.
MS §Trust-Tiered Isolation: TRUST-3 requires human approval "before first
execution" (once, bound to the tier assignment); TRUST-4 requires it "per
execution" (every time, bound to the exact execution attempt).
`WorkflowApprovalGate.is_enforced_approval` already refuses an approval
whose bound revision hash is not the CURRENT one - reusing that same
staleness check against a fresh, content-addressed per-execution identity
(`execution_binding_ref`, rather than a static tier-assignment identity) is
what turns "once" into "every time": a previous execution's approval can
never satisfy the next one, because each execution computes its own binding
ref from facts that change between executions.

NEITHER CONDITION SUBSTITUTES FOR THE OTHER, matching
`engineering.import.execution_gate`'s own rule: isolation is checked first
so it cannot be skipped by an approval-only code path, and a genuine
approval never overrides an unsatisfiable isolation posture.
"""

from __future__ import annotations

import json

from arkali.control.isolation.isolation_contract import IsolationResolution
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.engineering.plugin.content_ref import address_of
from arkali.engineering.plugin.errors import PluginExecutionRefusedError

#: MS §Trust-Tiered Isolation: "internet-sourced executable content" -> TRUST-4.
TRUST_TIER = "TRUST-4"


def execution_binding_ref(
    *, plugin_id: str, manifest_ref: str, action: str, execution_nonce: str,
) -> str:
    """The content-addressed identity of ONE execution attempt.

    `execution_nonce` must be supplied by the caller from a real,
    non-repeatable fact about this attempt (a resolved request id, a
    monotonic counter, a wall-clock timestamp from the invoking surface) -
    never a constant, or every "execution" would bind to the identical ref
    and the per-execution freshness this function exists to provide would
    collapse back into TRUST-3's once-per-assignment shape.
    """
    payload = json.dumps(
        {
            "plugin_id": plugin_id,
            "manifest_ref": manifest_ref,
            "action": action,
            "execution_nonce": execution_nonce,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return address_of(payload)


def assert_execution_approved(
    *,
    isolation_resolution: IsolationResolution,
    approval_gate: WorkflowApprovalGate,
    decision: str,
    actor: str,
    approval_binding_hash: str,
    execution_ref: str,
) -> None:
    """Raise unless TRUST-4 execution is genuinely permitted, for THIS
    execution attempt only.

    Never returns a boolean a caller could ignore - the same "raise, don't
    ask" shape `engineering.import.execution_gate.assert_execution_approved`
    established for the TRUST-3 analogue.
    """
    if isolation_resolution.tier != TRUST_TIER:
        raise PluginExecutionRefusedError(
            f"TRUST-4 execution gate invoked with a "
            f"{isolation_resolution.tier!r} resolution; ARK-REQ-0117 governs "
            "TRUST-4 only"
        )
    if isolation_resolution.execution_decision != "ALLOW":
        raise PluginExecutionRefusedError(
            "TRUST-4 execution is DENY: required isolation properties "
            f"{isolation_resolution.missing} are unsatisfiable on this host "
            "(control.isolation.IsolationAuthority.resolve)"
        )
    if not approval_gate.is_enforced_approval(
        decision=decision,
        actor=actor,
        approval_revision_hash=approval_binding_hash,
        current_revision_hash=execution_ref,
    ):
        raise PluginExecutionRefusedError(
            "TRUST-4 human approval is not enforced for this exact execution "
            "attempt; ARK-REQ-0117 requires a recorded, non-automated, "
            "non-stale APPROVED decision bound to THIS execution, not a "
            "previous one"
        )


__all__ = ["assert_execution_approved", "execution_binding_ref", "TRUST_TIER"]
