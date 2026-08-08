"""Candidate state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: engineering.candidate — AUTHORITY_MAP.yaml
`state_machine_authorities.Candidate`. Promotion is a separate authority
(`lifecycle.release`, ADR-0009); this module owns the machine, not the decision
to promote.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §2 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

`CREATED → PROMOTED` and `VERIFYING → PROMOTED` are the sharpest prohibitions in
the canonical set: they are the shape of "ship without verification". They are
enumerated explicitly so a rejection names them, and the guard on
`ACCEPTED → PROMOTED` enforces §2's invariant that promotion requires an
evidence set, plus HUMAN GATE 2 for core candidates.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import (
    GuardContext,
    StateMachine,
    StateMachineDefinition,
)

MACHINE = "Candidate"
AUTHORITY = "engineering.candidate"
SOURCE = "docs/canonical/STATE_MACHINES.md §2 Candidate"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "CREATED",
        "ASSEMBLING",
        "ASSEMBLED",
        "VERIFYING",
        "ACCEPTED",
        "REJECTED",
        "PROMOTED",
        "EXPIRED",
    ),
    transitions=(
        ("CREATED", "ASSEMBLING"),
        ("ASSEMBLING", "ASSEMBLED"),
        ("ASSEMBLED", "VERIFYING"),
        ("VERIFYING", "ACCEPTED"),
        ("VERIFYING", "REJECTED"),
        ("ACCEPTED", "PROMOTED"),
        ("ASSEMBLED", "EXPIRED"),
        ("ACCEPTED", "EXPIRED"),
    ),
    forbidden=(
        ("CREATED", "PROMOTED"),
        ("VERIFYING", "PROMOTED"),
        ("REJECTED", "CREATED"),
        ("REJECTED", "ASSEMBLING"),
        ("REJECTED", "ASSEMBLED"),
        ("REJECTED", "VERIFYING"),
        ("REJECTED", "ACCEPTED"),
        ("REJECTED", "PROMOTED"),
        ("REJECTED", "EXPIRED"),
        ("PROMOTED", "CREATED"),
        ("PROMOTED", "ASSEMBLING"),
        ("PROMOTED", "ASSEMBLED"),
        ("PROMOTED", "VERIFYING"),
        ("PROMOTED", "ACCEPTED"),
        ("PROMOTED", "REJECTED"),
        ("PROMOTED", "EXPIRED"),
    ),
    terminal=("REJECTED", "PROMOTED", "EXPIRED"),
)


def promotion_guard(context: GuardContext) -> bool:
    """§2 invariant: PROMOTED needs an evidence set; core candidates need GATE 2.

    Facts are read from the supplied context rather than resolved here: this
    module is not the evidence authority and must not become one.
    """
    evidence = context.get("evidence_set") or ()
    if not evidence:
        return False
    if context.get("is_core_candidate", False):
        return bool(context.get("human_gate_2_recorded", False))
    return True


def build() -> StateMachine:
    return StateMachine(DEFINITION, {("ACCEPTED", "PROMOTED"): promotion_guard})
