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

Phase 19 (C-29) adds the third guard below: `execution_approval_guard` on
`APPROVED_FOR_EXECUTION -> WORKING_COPY_CREATED`, enforcing ARK-REQ-0116
("TRUST-3 human approval before first execution") and ARK-REQ-0348 condition
7 ("execution is DENY where the tier's required security properties cannot
be established"). The guard itself only reads a boolean context fact, the
identical shape `static_inspection_guard`/`tier_assignment_guard` already
use; the fact is made trustworthy by `execution_gate.assert_execution_approved`,
which the pipeline composing this machine must call and which raises before
the fact can ever be set true on an unapproved or isolation-unsatisfiable
attempt. Nothing here duplicates that authority — the guard cannot itself
consult `control.policy` or `control.isolation` without creating a second,
ungoverned path to the same decision.
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


def execution_approval_guard(context: GuardContext) -> bool:
    """ARK-REQ-0116 / condition 7: no working copy before TRUST-3 execution is
    genuinely approved (human, non-stale) AND the tier's required isolation
    properties are satisfiable. `execution_gate.assert_execution_approved`
    raises before this fact may be set true on any other path."""
    return bool(context.get("execution_approved", False))


def build() -> StateMachine:
    return StateMachine(
        DEFINITION,
        {
            ("STATICALLY_INSPECTED", "TIER_ASSIGNED"): tier_assignment_guard,
            ("TIER_ASSIGNED", "APPROVED_FOR_EXECUTION"): static_inspection_guard,
            ("APPROVED_FOR_EXECUTION", "WORKING_COPY_CREATED"): execution_approval_guard,
        },
    )
