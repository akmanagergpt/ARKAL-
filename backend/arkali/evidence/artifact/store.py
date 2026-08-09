"""C-14 Artifact Store service.

Owner: `evidence.artifact`.

REGISTRATION IS ONE OPERATION. Bytes, descriptor, provenance and parent edges are
recorded together. Splitting them would allow an artifact that exists without
provenance, which `VDC §Provenance` forbids for exactly the artifacts this store
is for.

IDENTITY IS NEVER ACCEPTED FROM A CALLER. `register` takes bytes and returns the
address. There is no parameter by which a producer can name the artifact it is
producing, so the descriptor cannot disagree with the content.

IDEMPOTENT, NOT OVERWRITING. Registering the same bytes twice returns the
existing record. Registering *different* bytes cannot collide, because the
address is derived. So there is no update path and none is needed.

SECRETS STOP HERE. Every persisted string is passed through
`assert_no_raw_secret` with sink "evidence artifact" - the guard Phase 4 already
declared for this exact boundary. No second secret model is introduced, and the
existing control is reused rather than reimplemented.

TRANSACTION BOUNDARIES BELONG TO THE CALLER. Like `ProjectRegistry`, this service
never commits, so a caller cannot obtain a partially committed store.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from arkali.control.policy.secret_reference import assert_no_raw_secret
from arkali.evidence.artifact import content_address
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.errors import (
    InvalidArtifactIdentity,
    UnknownArtifact,
)
from arkali.evidence.artifact.records import (
    ArtifactParentEdge,
    ArtifactProvenanceRecord,
    ArtifactRecord,
)

#: The sink name Phase 4 declared for this boundary. Used, not redefined.
SECRET_SINK = "evidence artifact"


class ProvenanceInput:
    """The provenance a producer must supply. Every field is canonical metadata.

    A plain object rather than a mapping so a missing item is a TypeError at the
    call site instead of a silently absent column.
    """

    __slots__ = (
        "producer_agent", "provider_model", "task_id", "specification_version",
        "context_hash", "normalization", "tests", "evidence", "parents",
    )

    def __init__(
        self,
        *,
        producer_agent: str,
        provider_model: str,
        task_id: str,
        specification_version: str,
        context_hash: str,
        normalization: str = "none",
        tests: Sequence[str] = (),
        evidence: Sequence[str] = (),
        parents: Sequence[str] = (),
    ) -> None:
        self.producer_agent = producer_agent
        self.provider_model = provider_model
        self.task_id = task_id
        self.specification_version = specification_version
        self.context_hash = context_hash
        self.normalization = normalization
        self.tests = tuple(tests)
        self.evidence = tuple(evidence)
        self.parents = tuple(parents)

    def strings(self) -> tuple[str, ...]:
        """Every string that will be persisted, for the secret guard."""
        return (
            self.producer_agent, self.provider_model, self.task_id,
            self.specification_version, self.context_hash, self.normalization,
            *self.tests, *self.evidence,
        )


class ArtifactStore:
    """Registers and resolves content-addressed artifacts over one session."""

    def __init__(self, session: Session, blobs: ArtifactBlobStore) -> None:
        self._session = session
        self._blobs = blobs

    def get(self, address: str) -> ArtifactRecord | None:
        content_address.parse(address)
        return self._session.execute(
            select(ArtifactRecord).where(ArtifactRecord.artifact_id == address)
        ).scalar_one_or_none()

    def require(self, address: str) -> ArtifactRecord:
        found = self.get(address)
        if found is None:
            raise UnknownArtifact(f"no artifact {address!r} is registered")
        return found

    def provenance_of(self, address: str) -> ArtifactProvenanceRecord | None:
        return self._session.execute(
            select(ArtifactProvenanceRecord).where(
                ArtifactProvenanceRecord.artifact_id == address
            )
        ).scalar_one_or_none()

    def parents_of(self, address: str) -> tuple[str, ...]:
        rows = self._session.execute(
            select(ArtifactParentEdge)
            .where(ArtifactParentEdge.artifact_id == address)
            .order_by(ArtifactParentEdge.position)
        ).scalars()
        return tuple(row.parent_artifact_id for row in rows)

    def register(self, payload: bytes, provenance: ProvenanceInput) -> str:
        """Store bytes with their provenance and return the content address.

        Idempotent: the same bytes with the same provenance return the existing
        address without a second row. The parents must already be registered -
        the foreign key says so, and this check turns it into a typed refusal.
        """
        for value in provenance.strings():
            assert_no_raw_secret(value, sink=SECRET_SINK)

        address = self._blobs.put(payload)
        if self.get(address) is not None:
            return address

        for parent in provenance.parents:
            if self.get(parent) is None:
                raise UnknownArtifact(
                    f"parent artifact {parent!r} is not registered; a provenance "
                    "chain may not cite an artifact that does not exist"
                )

        algorithm, digest = content_address.parse(address)
        self._session.add(
            ArtifactRecord(
                artifact_id=address,
                hash_algorithm=algorithm,
                digest=digest,
                byte_size=len(payload),
                normalization=provenance.normalization,
            )
        )
        self._session.flush()
        self._session.add(
            ArtifactProvenanceRecord(
                artifact_id=address,
                producer_agent=provenance.producer_agent,
                provider_model=provenance.provider_model,
                task_id=provenance.task_id,
                specification_version=provenance.specification_version,
                context_hash=provenance.context_hash,
                tests=list(provenance.tests),
                evidence=list(provenance.evidence),
            )
        )
        for position, parent in enumerate(provenance.parents):
            self._session.add(
                ArtifactParentEdge(
                    artifact_id=address,
                    parent_artifact_id=parent,
                    position=position,
                )
            )
        self._session.flush()
        return address

    def content_of(self, address: str) -> bytes:
        """The registered artifact's bytes, verified against their address."""
        self.require(address)
        return self._blobs.get(address)

    def verify(self, address: str) -> bool:
        """Whether the stored bytes still hash to the registered address."""
        self.require(address)
        return self._blobs.verify(address)

    def assert_derived_identity(self, address: str) -> None:
        """Refuse an address that is not the canonical form.

        Used where an identity arrives from outside this context - a stored
        `provenance_ref`, for instance - so a hand-written string cannot enter
        the artifact surface as though it were a derived address.
        """
        if not content_address.is_address(address):
            raise InvalidArtifactIdentity(
                f"{address!r} is not a derived content address; artifact identity "
                "is computed from bytes and never supplied"
            )
