"""TRUST-3 execution gate: isolation + human approval (ARK-REQ-0116, condition 7).

Owner (this composition point): engineering.import. Owner of the two
authorities composed: control.isolation and control.policy (both Protected
Core, both reused unmodified).

NO PARALLEL APPROVAL AUTHORITY. ARK-REQ-0116 ("TRUST-3 human approval before
first execution") is owned by `control.policy`. `control.policy.
workflow_approval.WorkflowApprovalGate` (Phase 17) already IS the generic
mechanism the canonical set needs here: refuse an automated actor recording
its own approval, and refuse an approval bound to a revision hash that is no
longer current. Nothing about either rule is specific to a workflow graph —
`is_enforced_approval` compares two caller-supplied hash strings and consults
the one governed automated-actor list
(`AUTHORITY_MAP.yaml` `stable_mutation.prohibited_actors`, which already
names `implementing_actor`-shaped automated callers). Building a second,
import-specific approval-record contract here would be exactly the
duplicated-authority defect this build's governance repeatedly refuses; this
module instead binds the "revision" WorkflowApprovalGate compares to the
imported project's `TierAssignment.assignment_ref` rather than to a workflow
graph revision — the general shape survives the rename, and no new
`control.policy` module or file is required.

NEITHER CONDITION SUBSTITUTES FOR THE OTHER (ARK-REQ-0348 condition 7:
"execution is DENY where the tier's required security properties cannot be
established"). A genuine human approval never overrides an unsatisfiable
isolation posture, and a satisfiable isolation posture never substitutes for
a missing human approval — both are checked, and the isolation check is
evaluated first so it cannot be skipped by an approval-only code path.
"""

from __future__ import annotations

from arkali.control.isolation.isolation_contract import IsolationResolution
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.engineering.project_import.errors import RescueBoundaryViolationError


def assert_execution_approved(
    *,
    isolation_resolution: IsolationResolution,
    approval_gate: WorkflowApprovalGate,
    decision: str,
    actor: str,
    approval_binding_hash: str,
    tier_assignment_ref: str,
) -> None:
    """Raise unless TRUST-3 execution is genuinely permitted.

    Never returns a boolean a caller could ignore — the same "raise, don't
    ask" shape `AgentAuthority.assert_confined_to_candidate_lifecycle`
    established for a comparable Protected-Core-owned prohibition (Phase 14).
    """
    if isolation_resolution.execution_decision != "ALLOW":
        raise RescueBoundaryViolationError(
            "TRUST-3 execution is DENY: required isolation properties "
            f"{isolation_resolution.missing} are unsatisfiable on this host "
            "(control.isolation.IsolationAuthority.resolve)"
        )
    if not approval_gate.is_enforced_approval(
        decision=decision,
        actor=actor,
        approval_revision_hash=approval_binding_hash,
        current_revision_hash=tier_assignment_ref,
    ):
        raise RescueBoundaryViolationError(
            "TRUST-3 human approval is not enforced for this tier "
            "assignment; ARK-REQ-0116 requires a recorded, non-automated, "
            "non-stale APPROVED decision before first execution"
        )


__all__ = ["assert_execution_approved"]
