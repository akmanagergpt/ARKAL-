"""C-33 core-upgrade snapshot: proves the current Stable revision is genuinely
restorable before a core-upgrade candidate proceeds (ARK-REQ-0137).

Owner: `lifecycle.recovery` (Protected Core).

NOT `RecoveryService` AND NOT `RecoverySupervisor`. `RecoveryService` (Phase
20) backs up an ordinary workspace SQLite database - explicitly not Stable
rollback. `RecoverySupervisor` (Phase 22B) performs a Stable rollback once a
candidate has already failed. This module answers a third, earlier question:
before a core-upgrade candidate is even built, is there a real, provably
restorable record of the Stable revision it is about to risk? "Restorable"
is proven the same way `RecoveryService.prove_by_restore` proves a backup
restorable - not by trusting the write, but by reading the bytes back and
checking they still hash to what was registered (`ArtifactStore.verify`/
`.content_of`, C-14, reused unmodified).

NO CONTENT TRANSFORMATION. Only the current revision's identity is recorded;
`StableRevisionPointer.rollback_to` remains the sole path that ever switches
which revision is current, and it stays an identity-only pointer switch
(ARK-REQ-0159). Nothing here reads, generates or rewrites core content.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Final

from pydantic import BaseModel, ConfigDict

from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.contracts.error_root import ArkaliError
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer

CONTRACT_ID: Final[str] = "C-33"
PRODUCER: Final[str] = "lifecycle.recovery.core_snapshot"


class NoStableRevisionToSnapshotError(ArkaliError):
    """A core upgrade was attempted with no Stable revision recorded yet."""

    code = "ARK-ERR-0155"


class SnapshotNotRestorableError(ArkaliError):
    """A registered snapshot artifact did not prove restorable when read
    back - refused rather than trusted on the strength of the write alone."""

    code = "ARK-ERR-0156"


class CoreSnapshotRecord(BaseModel):
    """C-33/ARK-REQ-0137: what one pre-upgrade snapshot proved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision_id: str
    artifact_id: str
    candidate_id: str
    taken_at: dt.datetime


def take_core_snapshot(
    pointer: StableRevisionPointer, artifacts: ArtifactStore, *, candidate_id: str,
) -> CoreSnapshotRecord:
    """Record and prove a restorable snapshot of the current Stable revision.

    Refuses before a candidate may proceed if no Stable revision exists yet
    (nothing to snapshot), or if the registered artifact does not prove
    restorable by being read back and re-verified.
    """
    current = pointer.current()
    if current is None:
        raise NoStableRevisionToSnapshotError(
            "no Stable revision is recorded; there is nothing to snapshot "
            f"before candidate {candidate_id!r} may proceed"
        )
    taken_at = dt.datetime.now(dt.UTC)
    payload = json.dumps(
        {
            "contract": CONTRACT_ID,
            "revision_id": current.revision_id,
            "candidate_id": candidate_id,
            "taken_at": taken_at.isoformat(),
        },
        sort_keys=True,
    ).encode("utf-8")
    artifact_id = artifacts.register(
        payload,
        ProvenanceInput(
            producer_agent=PRODUCER,
            provider_model="none",
            task_id=candidate_id,
            specification_version=CONTRACT_ID,
            context_hash=current.revision_id,
        ),
    )
    if not artifacts.verify(artifact_id) or artifacts.content_of(artifact_id) != payload:
        raise SnapshotNotRestorableError(
            f"snapshot artifact {artifact_id!r} for revision "
            f"{current.revision_id!r} did not prove restorable"
        )
    return CoreSnapshotRecord(
        revision_id=current.revision_id, artifact_id=artifact_id,
        candidate_id=candidate_id, taken_at=taken_at,
    )
