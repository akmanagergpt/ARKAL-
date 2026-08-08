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

`REMOVED → QUARANTINED` is present because §6 states `any→QUARANTINED` literally,
which leaves this machine with no terminal state. That reading is recorded as
finding F-0018 for human ruling and is implemented exactly as written rather
than silently narrowed.
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
        ("REMOVED", "QUARANTINED"),
        ("QUARANTINED", "DISABLED"),
        ("QUARANTINED", "REMOVED"),
    ),
    forbidden=(),
    terminal=(),
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
