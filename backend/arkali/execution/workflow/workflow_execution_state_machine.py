"""Workflow Execution state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: execution.workflow — AUTHORITY_MAP.yaml
`state_machine_authorities.WorkflowExecution`.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §4 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§4's invariant is the load-bearing one: `WAITING_APPROVAL` advances only on a
recorded human approval, and no agent, API or workflow path may advance it. The
guard makes that structural — without a recorded approval the transition raises
`GuardRejected`, and there is no other route out of `WAITING_APPROVAL`.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import (
    GuardContext,
    StateMachine,
    StateMachineDefinition,
)

MACHINE = "WorkflowExecution"
AUTHORITY = "execution.workflow"
SOURCE = "docs/canonical/STATE_MACHINES.md §4 Workflow Execution"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "PENDING",
        "RUNNING",
        "WAITING_SIGNAL",
        "WAITING_APPROVAL",
        "COMPENSATING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
    ),
    transitions=(
        ("PENDING", "RUNNING"),
        ("RUNNING", "WAITING_SIGNAL"),
        ("RUNNING", "WAITING_APPROVAL"),
        ("RUNNING", "COMPENSATING"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "FAILED"),
        ("RUNNING", "CANCELLED"),
        ("WAITING_SIGNAL", "RUNNING"),
        ("WAITING_APPROVAL", "RUNNING"),
        ("COMPENSATING", "FAILED"),
        ("COMPENSATING", "CANCELLED"),
    ),
    forbidden=(),
    terminal=("SUCCEEDED", "FAILED", "CANCELLED"),
)


def human_approval_guard(context: GuardContext) -> bool:
    """§4: only a recorded human approval releases WAITING_APPROVAL.

    An agent-supplied or workflow-supplied approval is not a recorded human
    approval; the caller must present the recorded decision itself.
    """
    return bool(context.get("human_approval_recorded", False))


def build() -> StateMachine:
    return StateMachine(
        DEFINITION, {("WAITING_APPROVAL", "RUNNING"): human_approval_guard}
    )
