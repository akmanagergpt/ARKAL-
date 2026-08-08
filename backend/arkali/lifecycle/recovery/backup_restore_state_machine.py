"""Backup/Restore state machine (ARK-REQ-0043, ARK-REQ-0044).

Owner: lifecycle.recovery — AUTHORITY_MAP.yaml
`state_machine_authorities.BackupRestore`.

IMPLEMENTATION AUTHORITY. Executable authority for this machine;
`docs/canonical/STATE_MACHINES.md` §9 is the canonical specification, reconciled
by `backend/tests/state_machines/test_canonical_reconciliation.py`.

§9's invariant is the no-false-success rule of this machine: a backup is not
`BACKUP_VERIFIED` until proven by an actual restore, and file copy alone is FAIL.
The guard refuses `BACKUP_RUNNING → BACKUP_VERIFIED` unless a restore actually
proved it, so "the file exists" can never be recorded as verification.
"""

from __future__ import annotations

from arkali.kernel.contracts.state_machine import (
    GuardContext,
    StateMachine,
    StateMachineDefinition,
)

MACHINE = "BackupRestore"
AUTHORITY = "lifecycle.recovery"
SOURCE = "docs/canonical/STATE_MACHINES.md §9 Backup/Restore"

DEFINITION = StateMachineDefinition(
    machine=MACHINE,
    authority=AUTHORITY,
    authoritative_source=SOURCE,
    states=(
        "PLANNED",
        "BACKUP_RUNNING",
        "BACKUP_VERIFIED",
        "RESTORE_RUNNING",
        "RESTORE_VERIFIED",
        "FAILED",
    ),
    transitions=(
        ("PLANNED", "BACKUP_RUNNING"),
        ("BACKUP_RUNNING", "BACKUP_VERIFIED"),
        ("BACKUP_RUNNING", "FAILED"),
        ("BACKUP_VERIFIED", "RESTORE_RUNNING"),
        ("RESTORE_RUNNING", "RESTORE_VERIFIED"),
        ("RESTORE_RUNNING", "FAILED"),
    ),
    forbidden=(),
    terminal=("RESTORE_VERIFIED", "FAILED"),
)


def restore_proof_guard(context: GuardContext) -> bool:
    """§9: verification requires a proven restore, never a file copy."""
    return bool(context.get("restore_proven", False))


def build() -> StateMachine:
    return StateMachine(
        DEFINITION, {("BACKUP_RUNNING", "BACKUP_VERIFIED"): restore_proof_guard}
    )
