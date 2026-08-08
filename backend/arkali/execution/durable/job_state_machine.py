"""Job state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: execution.durable — AUTHORITY_MAP.yaml `state_machine_authorities.Job`.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §3 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§3's invariant — an interrupted job resolves to RESUMING or RECOVERABLE, and
silent disappearance is a verification FAIL — is a *runtime recovery* obligation
owned by Phase 7, not by this schema. What Phase 3 delivers is the structure that
makes it expressible: RECOVERABLE and RESUMING exist as reachable states, and
FAILED is deliberately not terminal so a failed job can still reach either.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import StateMachine, StateMachineDefinition

MACHINE = "Job"
AUTHORITY = "execution.durable"
SOURCE = "docs/canonical/STATE_MACHINES.md §3 Job"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "QUEUED",
        "RUNNING",
        "CHECKPOINTED",
        "PAUSED",
        "RESUMING",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "DEAD_LETTER",
        "RECOVERABLE",
    ),
    transitions=(
        ("QUEUED", "RUNNING"),
        ("RUNNING", "CHECKPOINTED"),
        ("CHECKPOINTED", "RUNNING"),
        ("RUNNING", "PAUSED"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "FAILED"),
        ("RUNNING", "CANCELLED"),
        ("PAUSED", "RESUMING"),
        ("RESUMING", "RUNNING"),
        ("FAILED", "DEAD_LETTER"),
        ("FAILED", "RECOVERABLE"),
        ("RECOVERABLE", "RESUMING"),
    ),
    forbidden=(),
    terminal=("SUCCEEDED", "CANCELLED", "DEAD_LETTER"),
)


def build() -> StateMachine:
    return StateMachine(DEFINITION)
