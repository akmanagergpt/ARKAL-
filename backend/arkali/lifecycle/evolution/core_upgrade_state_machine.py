"""Core Upgrade state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: lifecycle.evolution — AUTHORITY_MAP.yaml
`state_machine_authorities.CoreUpgrade`. Promotion is `lifecycle.release` and
rollback is `lifecycle.recovery` (ADR-0009); this module owns neither decision.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §8 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§8 invariants enforced as guards: entry requires a verified Recovery Supervisor
(Phase 22B) or the PDP returns DENY, and `PROMOTED` is reachable only through
`AWAITING_GATE_2` with HUMAN GATE 2 recorded. `ROLLED_BACK` is reachable only via
`lifecycle.recovery`, which the guard checks by requiring the recovery invoker.
"""

from __future__ import annotations

# `StateMachineInstance as StateMachineInstance` marks the intentional
# re-export mypy strict mode requires (three lifecycle.evolution modules
# import it from here rather than from kernel.contracts.state_machine
# directly, keeping that module's own fan-in at its 15-of-15 ceiling). Kept
# in this one statement deliberately, against ruff's own import-sort
# preference (which would split it into a second `from` line): a second
# statement from this file measures as a second import edge and reproduces
# the exact fan-in-16-of-15 violation this re-export exists to avoid -
# confirmed by running the real architecture gate before settling on this
# form, not assumed.
from arkali.kernel.contracts.state_machine import (  # noqa: I001
    GuardContext,
    StateMachine,
    StateMachineDefinition,
    StateMachineInstance as StateMachineInstance,
)

MACHINE = "CoreUpgrade"
AUTHORITY = "lifecycle.evolution"
SOURCE = "docs/canonical/STATE_MACHINES.md §8 Core Upgrade"
RECOVERY_AUTHORITY = "lifecycle.recovery"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "SNAPSHOT_TAKEN",
        "CANDIDATE_BUILT",
        "VERIFYING",
        "AWAITING_GATE_2",
        "PROMOTED",
        "REJECTED",
        "ROLLED_BACK",
    ),
    transitions=(
        ("SNAPSHOT_TAKEN", "CANDIDATE_BUILT"),
        ("CANDIDATE_BUILT", "VERIFYING"),
        ("VERIFYING", "AWAITING_GATE_2"),
        ("VERIFYING", "REJECTED"),
        ("AWAITING_GATE_2", "PROMOTED"),
        ("AWAITING_GATE_2", "REJECTED"),
        ("PROMOTED", "ROLLED_BACK"),
    ),
    forbidden=(),
    terminal=("REJECTED", "ROLLED_BACK"),
)


def recovery_supervisor_guard(context: GuardContext) -> bool:
    """§8: entry requires a verified Recovery Supervisor, else the PDP denies."""
    return bool(context.get("recovery_supervisor_verified", False))


def gate_2_guard(context: GuardContext) -> bool:
    """§8: promotion of a core upgrade requires a recorded HUMAN GATE 2."""
    return bool(context.get("human_gate_2_recorded", False))


def rollback_invoker_guard(context: GuardContext) -> bool:
    """ADR-0009: only lifecycle.recovery may drive a promoted core to ROLLED_BACK."""
    return context.get("invoker") == RECOVERY_AUTHORITY


def build() -> StateMachine:
    return StateMachine(
        DEFINITION,
        {
            ("SNAPSHOT_TAKEN", "CANDIDATE_BUILT"): recovery_supervisor_guard,
            ("AWAITING_GATE_2", "PROMOTED"): gate_2_guard,
            ("PROMOTED", "ROLLED_BACK"): rollback_invoker_guard,
        },
    )
