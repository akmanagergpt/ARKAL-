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

from typing import Final

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


#: Named states, for modules that must select WHICH declared transition to ask
#: for. They resolve through the definition above, so a state this machine stops
#: declaring becomes a KeyError at import rather than a string that quietly
#: reaches `evaluate` and is rejected at run time.
#:
#: These belong here and nowhere else. Phase 7 Package 2 needs to name a target
#: to request a move; writing the literal in the requesting module would put a
#: second copy of the vocabulary in this context, which
#: `test_durable_authority.py` forbids and which is exactly how a shadow
#: authority starts. The requester imports the name; the relation stays here.
_DECLARED: Final[dict[str, str]] = {state: state for state in DEFINITION.states}

QUEUED: Final[str] = _DECLARED["QUEUED"]
RUNNING: Final[str] = _DECLARED["RUNNING"]
CHECKPOINTED: Final[str] = _DECLARED["CHECKPOINTED"]
PAUSED: Final[str] = _DECLARED["PAUSED"]
RESUMING: Final[str] = _DECLARED["RESUMING"]
SUCCEEDED: Final[str] = _DECLARED["SUCCEEDED"]
FAILED: Final[str] = _DECLARED["FAILED"]
CANCELLED: Final[str] = _DECLARED["CANCELLED"]
DEAD_LETTER: Final[str] = _DECLARED["DEAD_LETTER"]
RECOVERABLE: Final[str] = _DECLARED["RECOVERABLE"]


def build() -> StateMachine:
    return StateMachine(DEFINITION)
