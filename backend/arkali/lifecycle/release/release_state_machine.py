"""Release state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: lifecycle.release — AUTHORITY_MAP.yaml `state_machine_authorities.Release`.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §7 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§7's invariant: `RELEASED` requires HUMAN GATE 7 and a complete evidence set.
The guard refuses the transition without both, so a release cannot be self-
declared by any implementing actor.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import (
    GuardContext,
    StateMachine,
    StateMachineDefinition,
)

MACHINE = "Release"
AUTHORITY = "lifecycle.release"
SOURCE = "docs/canonical/STATE_MACHINES.md §7 Release"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=("DRAFT", "BUILT", "VERIFIED", "SIGNED_READY", "RELEASED", "WITHDRAWN"),
    transitions=(
        ("DRAFT", "BUILT"),
        ("BUILT", "VERIFIED"),
        ("VERIFIED", "SIGNED_READY"),
        ("SIGNED_READY", "RELEASED"),
        ("DRAFT", "WITHDRAWN"),
        ("BUILT", "WITHDRAWN"),
        ("VERIFIED", "WITHDRAWN"),
        ("SIGNED_READY", "WITHDRAWN"),
    ),
    forbidden=(),
    terminal=("RELEASED", "WITHDRAWN"),
)


def release_guard(context: GuardContext) -> bool:
    """§7: RELEASED requires HUMAN GATE 7 plus a complete evidence set."""
    return bool(context.get("human_gate_7_recorded", False)) and bool(
        context.get("evidence_complete", False)
    )


def build() -> StateMachine:
    return StateMachine(DEFINITION, {("SIGNED_READY", "RELEASED"): release_guard})
