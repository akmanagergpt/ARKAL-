"""Project state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: control.registry.project — AUTHORITY_MAP.yaml `state_machine_authorities.Project`.

IMPLEMENTATION AUTHORITY. This module is the executable authority for the
Project machine. `docs/canonical/STATE_MACHINES.md` §1 remains the canonical
specification. The two are reconciled mechanically by
`backend/tests/state_machines/test_canonical_reconciliation.py`, which fails if
they diverge in states, transitions, forbidden pairs or terminal states.
Neither is a silent private copy of the other: divergence cannot land.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import StateMachine, StateMachineDefinition

MACHINE = "Project"
AUTHORITY = "control.registry.project"
SOURCE = "docs/canonical/STATE_MACHINES.md §1 Project"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=("DRAFT", "SPECIFIED", "ACTIVE", "SUSPENDED", "ARCHIVED"),
    transitions=(
        ("DRAFT", "SPECIFIED"),
        ("SPECIFIED", "ACTIVE"),
        ("ACTIVE", "SUSPENDED"),
        ("SUSPENDED", "ACTIVE"),
        ("ACTIVE", "ARCHIVED"),
        ("SUSPENDED", "ARCHIVED"),
    ),
    forbidden=(
        ("DRAFT", "ACTIVE"),
        ("ARCHIVED", "DRAFT"),
        ("ARCHIVED", "SPECIFIED"),
        ("ARCHIVED", "ACTIVE"),
        ("ARCHIVED", "SUSPENDED"),
    ),
    terminal=("ARCHIVED",),
)


def build() -> StateMachine:
    """The Project machine. No guards: §1 declares no conditional transition."""
    return StateMachine(DEFINITION)
