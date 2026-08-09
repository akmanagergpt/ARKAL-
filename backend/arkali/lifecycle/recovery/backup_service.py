"""Minimal backup/restore lifecycle (ARK-REQ-0153, ARK-REQ-0335).

Owner: `lifecycle.recovery` (Protected Core).

THE STATE MACHINE IS DRIVEN, NOT COPIED. Every transition goes through the
executable `BackupRestore` machine built by `backup_restore_state_machine.build`.
This module declares no states, no transitions and no guard: the
`restore_proof_guard` that refuses `BACKUP_RUNNING -> BACKUP_VERIFIED` without a
proven restore already lives with the machine, and a control asserts no
canonical state name appears as a literal here.

WHY THE ORDER LOOKS UNUSUAL. `STATE_MACHINES.md` section 9 puts `BACKUP_VERIFIED`
*before* `RESTORE_RUNNING` while its invariant says a backup is not verified
until proven by an actual restore. Read together, the canonical flow is: take
the image, prove it by restoring into a **scratch** target and checking the
result, promote to `BACKUP_VERIFIED`, and only then restore to the real target.
That is what this module does. The file existing is never the proof.

MECHANICS STAY IN THE KERNEL. Byte-level backup, restore, digest and
`PRAGMA integrity_check` belong to `kernel.persistence` (ADR-0006). This module
orchestrates; it opens no raw driver connection and issues no SQL.

POLICY IS ENFORCED, NOT ASSUMED. `lifecycle.recovery` is rank 5 and
`control.policy` is rank 1, so the PEP call is a legal downward edge. Reads use
`READ_FILE`, writes use `WRITE_WORKSPACE_FILE`. `WRITE_STABLE_FILE` and
`ROLLBACK_STABLE` are never requested: this is not Stable rollback, and the
Recovery Supervisor is Phase 22B.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Callable
from typing import Final

from sqlalchemy import Engine

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.kernel.contracts.state_machine import StateMachineInstance
from arkali.kernel.persistence.backup import (
    copy_database,
    file_digest,
    integrity_check,
    restore_database,
)
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import applied_revision
from arkali.lifecycle.recovery.backup_restore_state_machine import build
from arkali.lifecycle.recovery.manifest import (
    IMAGE_SUFFIX,
    BackupManifest,
    ManifestError,
    read_manifest,
    verify_against,
    write_manifest,
)

#: The actor this context presents to the PDP. Read by the audit trail.
ACTOR: Final[str] = "lifecycle.recovery"
#: Local-first recovery runs on the host with no isolation requirement.
TRUST_TIER: Final[str] = "TRUST-0"

#: A caller-supplied check that the restored database really holds state A.
#: It receives a live engine over the restored image and answers truthfully.
Verifier = Callable[[Engine], bool]


class BackupVerificationFailed(Exception):
    """A restore completed but the restored state was not what was expected."""


class BackupSet:
    """One backup: an image, its manifest, and the lifecycle instance."""

    def __init__(self, image: pathlib.Path, manifest: BackupManifest,
                 machine: StateMachineInstance) -> None:
        self.image = image
        self.manifest = manifest
        self._machine = machine

    @property
    def state(self) -> str:
        return self._machine.state

    @property
    def machine(self) -> StateMachineInstance:
        """The lifecycle instance. Exposed read-only; transitions go through
        this service, which is the only caller that can supply a restore proof."""
        return self._machine


class RecoveryService:
    """Minimal backup/restore under `lifecycle.recovery`.

    Not the Recovery Supervisor (Phase 22B) and not Stable rollback. It backs
    up and restores an ordinary workspace database.
    """

    def __init__(self, pep: PolicyEnforcementPoint) -> None:
        self._pep = pep

    @property
    def audit_trail(self) -> tuple[object, ...]:
        """Every PDP decision this flow produced, via the Phase 4 surface."""
        return self._pep.audit_trail

    def _request(self, operation: str) -> PolicyRequest:
        return PolicyRequest(
            operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
        )

    def create_backup(
        self, engine: Engine, workspace: pathlib.Path, backup_id: str
    ) -> BackupSet:
        """Take an image and write its manifest. The result is NOT verified.

        The returned set sits in the running state. Nothing here may promote it:
        only `prove_by_restore` can, and only with a real restore behind it.
        """
        if not backup_id.strip():
            raise ValueError("a backup must be identified")
        self._pep.require_auto(self._request("READ_FILE"))
        self._pep.require_auto(self._request("WRITE_WORKSPACE_FILE"))

        instance = build().start(_initial_state())
        instance.apply(_running_state())

        image = workspace / f"{backup_id}{IMAGE_SUFFIX}"
        copy_database(engine, image)
        manifest = BackupManifest(
            backup_id=backup_id,
            source_database=pathlib.Path(engine.url.database or "unknown").name,
            schema_revision=applied_revision(engine),
            created_at=dt.datetime.now(dt.timezone.utc),
            digest=file_digest(image),
            size_bytes=image.stat().st_size,
        )
        write_manifest(image, manifest)
        return BackupSet(image, manifest, instance)

    def prove_by_restore(
        self, backup: BackupSet, scratch: pathlib.Path, verifier: Verifier
    ) -> BackupSet:
        """Restore into a scratch target and verify, then promote the backup.

        Every refusal drives the lifecycle to its failure state, so a backup
        that could not be proven is never left looking merely unfinished.
        """
        try:
            self._integrity_gate(backup)
            restored_revision = self._restore_into(scratch, backup)
            self._compatibility_gate(backup.manifest, restored_revision)
            self._verify(scratch, backup, verifier)
        except Exception:
            backup.machine.apply(_failed_state())
            raise
        backup.machine.apply(_verified_state(), {"restore_proven": True})
        return backup

    def restore(self, backup: BackupSet, target: pathlib.Path,
                verifier: Verifier) -> BackupSet:
        """Restore a proven backup to a real target and verify the result."""
        backup.machine.apply(_restoring_state())
        try:
            self._integrity_gate(backup)
            restored_revision = self._restore_into(target, backup)
            self._compatibility_gate(backup.manifest, restored_revision)
            self._verify(target, backup, verifier)
        except Exception:
            backup.machine.apply(_failed_state())
            raise
        backup.machine.apply(_restore_verified_state())
        return backup

    def _integrity_gate(self, backup: BackupSet) -> None:
        """Recompute integrity from the bytes, and re-read the manifest on disk.

        Both halves matter: re-reading catches a tampered manifest, recomputing
        catches tampered image bytes.
        """
        self._pep.require_auto(self._request("READ_FILE"))
        on_disk = read_manifest(backup.image)
        if on_disk != backup.manifest:
            raise ManifestError(
                f"manifest for {backup.manifest.backup_id} on disk differs from "
                "the one recorded when the backup was taken"
            )
        verify_against(backup.image, on_disk)

    def _restore_into(self, target: pathlib.Path, backup: BackupSet) -> str | None:
        self._pep.require_auto(self._request("WRITE_WORKSPACE_FILE"))
        target.parent.mkdir(parents=True, exist_ok=True)
        engine = create_persistence_engine(sqlite_url(target))
        try:
            restore_database(backup.image, engine)
        finally:
            engine.dispose()
        reopened = create_persistence_engine(sqlite_url(target))
        try:
            if integrity_check(reopened) != "ok":
                raise BackupVerificationFailed(
                    f"restored database at {target.name} fails its own integrity check"
                )
            return applied_revision(reopened)
        finally:
            reopened.dispose()

    @staticmethod
    def _compatibility_gate(manifest: BackupManifest, actual: str | None) -> None:
        if not manifest.compatible_with(actual):
            raise ManifestError(
                f"schema revision mismatch: manifest records "
                f"{manifest.schema_revision!r}, restored database reports "
                f"{actual!r}. Migrating during restore is Phase 20, not Phase 5"
            )

    def _verify(self, target: pathlib.Path, backup: BackupSet,
                verifier: Verifier) -> None:
        """Reopen through a fresh engine and let the caller check the state."""
        self._pep.require_auto(self._request("READ_FILE"))
        engine = create_persistence_engine(sqlite_url(target))
        try:
            if not verifier(engine):
                raise BackupVerificationFailed(
                    f"restored state from {backup.manifest.backup_id} does not "
                    "match the expected state"
                )
        finally:
            engine.dispose()


def _initial_state() -> str:
    """The one declared state with no incoming transition."""
    definition = build().definition
    return next(
        state for state in definition.states
        if all(target != state for _, target in definition.transitions)
    )


def _running_state() -> str:
    """The successor of the initial state."""
    definition = build().definition
    start = _initial_state()
    return next(target for source, target in definition.transitions if source == start)


def _verified_state() -> str:
    """The guarded target: the transition the machine protects with a guard."""
    machine = build()
    return machine.guarded_transitions[0][1]


def _restoring_state() -> str:
    """The successor of the verified state."""
    definition = build().definition
    verified = _verified_state()
    return next(
        target for source, target in definition.transitions if source == verified
    )


def _failed_state() -> str:
    """The terminal state the running state can fall to."""
    definition = build().definition
    running = _running_state()
    return next(
        target for source, target in definition.transitions
        if source == running and target in definition.terminal
    )


def _restore_verified_state() -> str:
    """The non-failure terminal reachable from the restoring state."""
    definition = build().definition
    restoring, failed = _restoring_state(), _failed_state()
    return next(
        target for source, target in definition.transitions
        if source == restoring and target in definition.terminal and target != failed
    )
