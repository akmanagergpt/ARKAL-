"""Evolution Campaign state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: lifecycle.evolution — AUTHORITY_MAP.yaml
`state_machine_authorities.EvolutionCampaign`.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §10 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§10 invariants: `DECLARED` requires an objective, baseline metrics and all six
budgets recorded **before** execution; a rejected candidate does not auto-generate
a successor; and all four exits are terminal, with no restart permitted to obtain
a different terminal state. The last is structural here — the four exit states
carry no outgoing transition, so "run it again until it passes" cannot be
expressed at all.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import (
    GuardContext,
    StateMachine,
    StateMachineDefinition,
)

MACHINE = "EvolutionCampaign"
AUTHORITY = "lifecycle.evolution"
SOURCE = "docs/canonical/STATE_MACHINES.md §10 Evolution Campaign"

#: §10 requires all six budgets before a campaign may run.
REQUIRED_BUDGET_COUNT = 6

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "DECLARED",
        "RUNNING",
        "PROMOTED",
        "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN",
        "ESCALATED",
        "BLOCKED",
    ),
    transitions=(
        ("DECLARED", "RUNNING"),
        ("RUNNING", "PROMOTED"),
        ("RUNNING", "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN"),
        ("RUNNING", "ESCALATED"),
        ("RUNNING", "BLOCKED"),
    ),
    forbidden=(),
    terminal=(
        "PROMOTED",
        "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN",
        "ESCALATED",
        "BLOCKED",
    ),
)


def declaration_guard(context: GuardContext) -> bool:
    """§10: objective, baseline metrics and all six budgets recorded first."""
    if not context.get("objective"):
        return False
    if not context.get("baseline_metrics"):
        return False
    budgets = context.get("budgets") or ()
    return len(set(budgets)) == REQUIRED_BUDGET_COUNT


def build() -> StateMachine:
    return StateMachine(DEFINITION, {("DECLARED", "RUNNING"): declaration_guard})
