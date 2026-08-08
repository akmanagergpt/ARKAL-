"""Hardening Round state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: acceptance.engine (Protected Core) — AUTHORITY_MAP.yaml
`state_machine_authorities.HardeningRound`.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §11 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§11 invariants: budgets are declared before the first candidate; budget
exhaustion with an intact baseline yields
`COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN`, otherwise `ESCALATED`; and a
post-Round-4 regression failure yields `ESCALATED`, never a new round. The last
is structural: all four exits are terminal, so a fresh round cannot be reached
from an exit to obtain a better verdict.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import (
    GuardContext,
    StateMachine,
    StateMachineDefinition,
)

MACHINE = "HardeningRound"
AUTHORITY = "acceptance.engine"
SOURCE = "docs/canonical/STATE_MACHINES.md §11 Hardening Round"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "DECLARED",
        "RUNNING",
        "PASS",
        "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN",
        "ESCALATED",
        "BLOCKED",
    ),
    transitions=(
        ("DECLARED", "RUNNING"),
        ("RUNNING", "PASS"),
        ("RUNNING", "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN"),
        ("RUNNING", "ESCALATED"),
        ("RUNNING", "BLOCKED"),
    ),
    forbidden=(),
    terminal=(
        "PASS",
        "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN",
        "ESCALATED",
        "BLOCKED",
    ),
)


def budget_declaration_guard(context: GuardContext) -> bool:
    """§11: budgets must be declared before the first candidate is produced."""
    return bool(context.get("budgets_declared", False))


def build() -> StateMachine:
    return StateMachine(DEFINITION, {("DECLARED", "RUNNING"): budget_declaration_guard})
