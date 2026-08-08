"""Import Project state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: engineering.import — AUTHORITY_MAP.yaml
`state_machine_authorities.ImportProject`.

ERR-001: the logical context identity is `engineering.import`; the physical
package is `engineering/project_import` because `import` is a Python reserved
keyword. Authority, lifecycle, TRUST tier, Protected Core membership and
requirement meaning are unchanged by that erratum.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §12 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§12 invariants: no execution before `STATICALLY_INSPECTED`; the tier cannot be
reassigned by an implementing actor; the original source is preserved unmodified
and independently restorable. The first is structural — `APPROVED_FOR_EXECUTION`
is unreachable except through `STATICALLY_INSPECTED` — and is additionally
guarded so the inspection must have actually completed, not merely been passed
through.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import (
    GuardContext,
    StateMachine,
    StateMachineDefinition,
)

MACHINE = "ImportProject"
AUTHORITY = "engineering.import"
SOURCE = "docs/canonical/STATE_MACHINES.md §12 Import Project"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "REGISTERED",
        "STATICALLY_INSPECTED",
        "TIER_ASSIGNED",
        "APPROVED_FOR_EXECUTION",
        "WORKING_COPY_CREATED",
        "REJECTED",
    ),
    transitions=(
        ("REGISTERED", "STATICALLY_INSPECTED"),
        ("STATICALLY_INSPECTED", "TIER_ASSIGNED"),
        ("TIER_ASSIGNED", "APPROVED_FOR_EXECUTION"),
        ("APPROVED_FOR_EXECUTION", "WORKING_COPY_CREATED"),
        ("REGISTERED", "REJECTED"),
        ("STATICALLY_INSPECTED", "REJECTED"),
        ("TIER_ASSIGNED", "REJECTED"),
        ("APPROVED_FOR_EXECUTION", "REJECTED"),
        ("WORKING_COPY_CREATED", "REJECTED"),
    ),
    forbidden=(),
    terminal=("REJECTED",),
)


def static_inspection_guard(context: GuardContext) -> bool:
    """§12: no execution approval before static inspection actually completed."""
    return bool(context.get("static_inspection_complete", False))


def tier_assignment_guard(context: GuardContext) -> bool:
    """§12: the tier is not assignable by an implementing actor."""
    assigner = context.get("tier_assigned_by")
    return bool(assigner) and assigner != "implementing_actor"


def build() -> StateMachine:
    return StateMachine(
        DEFINITION,
        {
            ("STATICALLY_INSPECTED", "TIER_ASSIGNED"): tier_assignment_guard,
            ("TIER_ASSIGNED", "APPROVED_FOR_EXECUTION"): static_inspection_guard,
        },
    )
