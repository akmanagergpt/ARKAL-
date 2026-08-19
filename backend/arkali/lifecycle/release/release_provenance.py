"""C-31 release provenance: registers a release candidate's declaration as a
real, content-addressed C-14 artifact with real VDC §Provenance metadata
(ARK-REQ-0015, ARK-REQ-0350).

Owner: `lifecycle.release` (Protected Core).

REUSES C-14 UNMODIFIED - THROUGH A STRUCTURAL PROTOCOL. `evidence.artifact.
store.ArtifactStore`/`ProvenanceInput` are the real, unmodified Phase 6
mechanism. A real, measured `max_orchestration_depth` violation (5 of 4) was
found by running the gate: `lifecycle.evolution -> lifecycle.release` is
already a real, declared edge (`core_promotion.py`'s own "promotion
handoff"), so a direct `evidence.artifact.store` import here would have
extended that chain through `evidence.artifact -> control.policy ->
kernel.contracts` to five hops. `lifecycle.recovery.core_snapshot` could
import `ArtifactStore` directly because `lifecycle.evolution -> lifecycle.
recovery` stays Protocol-only (`RestorableSnapshotProof`) - this context has
no such luxury on its own inbound edge. `ArtifactRegistrar` is that same
ADR-0008 shape, reduced to the three primitive operations this module
needs; a real caller still constructs the real `ArtifactStore` and adapts it
at the composition root (see `test_release_provenance.py`'s own adapter),
so the genuine C-14 mechanism - not a second one - still does the work.

EVERY VDC §PROVENANCE FIELD IS POPULATED, NEVER LEFT DEFAULT. hash (the
artifact's own content address), producer/task (`PRODUCER`/`candidate.
release_id`), provider/model ("none" - packaging is fully deterministic, no
AI provider is contacted), spec version (`CONTRACT_ID` = "C-31", the same
producer-names-its-own-contract convention every other registrant in this
repository already uses), context hash (the candidate's own core revision
id, tying this artifact to the exact Stable Core content it packages).

PARENTS ARE ASSEMBLED LATER, NEVER GUESSED HERE. An artifact's parents are
the artifacts it was derived from; at declaration time this record derives
from nothing yet. Package 3's SBOM artifact and Package 4's suspicious-
package-review artifact are each their own, separate C-14 registrations;
Package 7's final release-manifest artifact is the one that cites all of
them as real, already-registered parents - the point in this pipeline
where a genuine derivation actually exists to record.

RE-VERIFIED AFTER WRITE, NEVER TRUSTED FROM THE WRITE ALONE.
`register_release_provenance` reads the artifact back and re-checks its
hash before returning - the same discipline `core_snapshot.take_core_
snapshot` already established for exactly this reason (a PASS must never
rest on a stored boolean).
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.error_root import ArkaliError
from arkali.lifecycle.release.release_manifest import ReleaseCandidate

CONTRACT_ID: Final[str] = "C-31"
PRODUCER: Final[str] = "lifecycle.release.release_provenance"


class ReleaseProvenanceNotVerifiableError(ArkaliError):
    """A registered release-provenance artifact did not prove restorable
    when read back - refused rather than trusted on the strength of the
    write alone."""

    code = "ARK-ERR-0165"


class ProvenanceFields(BaseModel):
    """The VDC §Provenance fields a registration needs, grouped into one
    value so `ArtifactRegistrar.register` stays under
    `max_parameters_per_public_function` (6) - a real, measured violation at
    10 keyword parameters, found by running the gate. Structurally mirrors
    `evidence.artifact.store.ProvenanceInput` without importing it; the
    composition-root adapter builds the real one from this."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    producer_agent: str
    provider_model: str
    task_id: str
    specification_version: str
    context_hash: str
    normalization: str = "none"
    tests: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    parents: tuple[str, ...] = ()


@runtime_checkable
class ArtifactRegistrar(Protocol):
    """Structural view of `evidence.artifact.store.ArtifactStore`'s real
    register/verify/content_of surface. See the module docstring for why
    this is a `Protocol` and not a direct import."""

    def register(self, payload: bytes, provenance: ProvenanceFields) -> str:
        """Store `payload` with real provenance and return its content
        address. The real `ArtifactStore.register` accepts a `ProvenanceInput`
        object; the adapter at the composition root translates one from the
        other."""
        ...

    def verify(self, address: str) -> bool:
        """Whether the stored bytes at `address` still hash to it."""
        ...

    def content_of(self, address: str) -> bytes:
        """The registered bytes at `address`, verified against their address."""
        ...


class ReleaseProvenanceRecord(BaseModel):
    """C-31/ARK-REQ-0015/ARK-REQ-0350: what one provenance registration proved."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    release_id: str
    artifact_id: str
    core_revision_id: str
    registered_at: dt.datetime


def register_release_provenance(
    candidate: ReleaseCandidate, artifacts: ArtifactRegistrar,
) -> ReleaseProvenanceRecord:
    """Register the real, re-verified provenance record for `candidate`.

    Refuses (via `ReleaseProvenanceNotVerifiableError`) if the artifact read
    back after registration does not hash to its own registered address or
    does not round-trip byte-identical - real re-verification, never a
    stored boolean.
    """
    # `registered_at` is deliberately NOT part of the hashed payload: the
    # provenance of a release candidate is fully determined by the candidate
    # itself (release_id, core_revision_id, declared_at), never by when a
    # caller happens to invoke this function. Including a call-time
    # timestamp in the hash would make the same candidate register a
    # different artifact on every call - real idempotency breakage this
    # module's own test suite caught by exercising the exact defence
    # against "release replay" it exists to provide.
    registered_at = dt.datetime.now(dt.UTC)
    payload = json.dumps(
        {
            "contract": CONTRACT_ID,
            "release_id": candidate.release_id,
            "core_revision_id": candidate.core_revision_id,
            "declared_at": candidate.declared_at.isoformat(),
        },
        sort_keys=True,
    ).encode("utf-8")
    artifact_id = artifacts.register(
        payload,
        ProvenanceFields(
            producer_agent=PRODUCER,
            provider_model="none",
            task_id=candidate.release_id,
            specification_version=CONTRACT_ID,
            context_hash=candidate.core_revision_id,
        ),
    )
    if not artifacts.verify(artifact_id) or artifacts.content_of(artifact_id) != payload:
        raise ReleaseProvenanceNotVerifiableError(
            f"release provenance artifact {artifact_id!r} for release "
            f"{candidate.release_id!r} did not prove restorable"
        )
    return ReleaseProvenanceRecord(
        release_id=candidate.release_id,
        artifact_id=artifact_id,
        core_revision_id=candidate.core_revision_id,
        registered_at=registered_at,
    )


__all__ = [
    "ArtifactRegistrar",
    "ProvenanceFields",
    "ReleaseProvenanceNotVerifiableError",
    "ReleaseProvenanceRecord",
    "register_release_provenance",
]
