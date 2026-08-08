"""Plugin Lifecycle state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: engineering.plugin — AUTHORITY_MAP.yaml
`state_machine_authorities.PluginLifecycle`.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §6 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§6's invariant — permissions are declared using the canonical operation classes,
and an unmappable permission blocks at `PERMISSIONS_DECLARED` — is enforced by
`permission_mapping_guard`. The canonical vocabulary is **not** copied here: the
guard receives the permitted classes from its context, so `AUTHORITY_MAP.yaml`
remains the sole store of the fourteen operation classes. Hard-coding them would
be the shadow-model defect F-0013 recorded against the phase-graph validator.

`REMOVED` is TERMINAL by human ruling **ERR-002**, which closed finding F-0018.
§6 previously read `any→QUARANTINED`; taken literally that made
`REMOVED → QUARANTINED` legal and left the machine with no terminal state. The
ruling narrowed `any` to the non-removed states and §6 now reads
`any pre-REMOVED→QUARANTINED` with an explicit `Forbidden: REMOVED→any`.

A removed plugin revision cannot be quarantined again, reactivated, or
reinstalled by mutating the same lifecycle instance. Reintroducing the same
plugin or package starts a **new** instance with its own provenance and audit
identity — `StateMachine.start` on a fresh instance, never a transition out of
`REMOVED`.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import (
    GuardContext,
    StateMachine,
    StateMachineDefinition,
)

MACHINE = "PluginLifecycle"
AUTHORITY = "engineering.plugin"
SOURCE = "docs/canonical/STATE_MACHINES.md §6 Plugin Lifecycle"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "DISCOVERED",
        "MANIFEST_VALIDATED",
        "PERMISSIONS_DECLARED",
        "APPROVED",
        "ENABLED",
        "DISABLED",
        "QUARANTINED",
        "REMOVED",
    ),
    transitions=(
        ("DISCOVERED", "MANIFEST_VALIDATED"),
        ("MANIFEST_VALIDATED", "PERMISSIONS_DECLARED"),
        ("PERMISSIONS_DECLARED", "APPROVED"),
        ("APPROVED", "ENABLED"),
        ("ENABLED", "DISABLED"),
        ("DISABLED", "ENABLED"),
        ("DISCOVERED", "QUARANTINED"),
        ("MANIFEST_VALIDATED", "QUARANTINED"),
        ("PERMISSIONS_DECLARED", "QUARANTINED"),
        ("APPROVED", "QUARANTINED"),
        ("ENABLED", "QUARANTINED"),
        ("DISABLED", "QUARANTINED"),
        ("QUARANTINED", "DISABLED"),
        ("QUARANTINED", "REMOVED"),
    ),
    forbidden=(
        ("REMOVED", "DISCOVERED"),
        ("REMOVED", "MANIFEST_VALIDATED"),
        ("REMOVED", "PERMISSIONS_DECLARED"),
        ("REMOVED", "APPROVED"),
        ("REMOVED", "ENABLED"),
        ("REMOVED", "DISABLED"),
        ("REMOVED", "QUARANTINED"),
    ),
    terminal=("REMOVED",),
)


def permission_mapping_guard(context: GuardContext) -> bool:
    """Every declared permission must map to a canonical operation class.

    `canonical_operation_classes` is supplied by the caller from
    AUTHORITY_MAP.yaml. An absent vocabulary fails closed rather than passing
    for want of anything to check.
    """
    vocabulary = context.get("canonical_operation_classes")
    if not vocabulary:
        return False
    declared = context.get("declared_permissions") or ()
    return set(declared).issubset(set(vocabulary))


def build() -> StateMachine:
    return StateMachine(
        DEFINITION, {("PERMISSIONS_DECLARED", "APPROVED"): permission_mapping_guard}
    )
