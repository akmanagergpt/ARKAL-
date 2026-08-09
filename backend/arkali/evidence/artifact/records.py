"""C-14 artifact descriptor, provenance record and parent edges.

Owner: `evidence.artifact` - AUTHORITY_MAP.yaml concern
`artifact_identity_and_provenance`.

IDENTITY IS THE CONTENT ADDRESS. `artifact_id` is not an opaque key that happens
to be a hash; it *is* the hash, produced by `content_address.address_of` and by
nothing else. `hash_algorithm` and `digest` are stored alongside it so a consumer
can select by algorithm without parsing a string, and a control asserts the three
always agree.

IMMUTABILITY IS ENFORCED, NOT REQUESTED. Both tables refuse `before_update`, the
same mechanism `control.registry.project` uses for revisions
(`ARCHITECTURE.md` section 7). It does not depend on callers choosing not to
write. This is stronger than a project revision's rule and deliberately so: a
revision may supersede another, whereas an artifact whose bytes changed is a
different artifact with a different address. There is no update path at all.

PARENTS ARE REAL EDGES. A foreign key means a parent must already be registered
before a child can claim it, so a provenance chain cannot cite an artifact that
never existed. A JSON list would have accepted any string.

NOTHING HERE IS AN AUDIT CHAIN. `provenance.evidence` holds references only.
`VERIFICATION_ARCHITECTURE.md` section 2.2 rule 7 gives the chain to
`evidence.audit`, which is Protected Core and is Package 2; a shadow chain built
here would be exactly the duplicate authority the architecture forbids.

ENGINE-NEUTRAL (ARK-REQ-0012). Declarative mapping only - `String`, `Integer`,
`DateTime`, `JSON` and standard constraints, all rendered for SQLite and
PostgreSQL alike. No PRAGMA, no raw SQL, no dialect branch. The engine is built
only by `kernel.persistence`.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from arkali.evidence.artifact.errors import ArtifactImmutabilityViolation
from arkali.kernel.persistence.base import PersistenceBase

ARTIFACT_TABLE: Final[str] = "artifact"
PROVENANCE_TABLE: Final[str] = "artifact_provenance"
PARENT_TABLE: Final[str] = "artifact_parent"

#: `sha256:` + 64 hex characters. Sized exactly, so a longer string is refused by
#: the column rather than silently truncated into a different identity.
ADDRESS_LENGTH: Final[int] = 71

#: `provenance_ref` on a C-12 revision is `String(200)`; an address is 71, so the
#: existing column already holds one and C-12 needs no change.
METADATA_LENGTH: Final[int] = 200


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ArtifactRecord(PersistenceBase):
    """A registered artifact, identified by the address of its bytes."""

    __tablename__ = ARTIFACT_TABLE

    artifact_id: Mapped[str] = mapped_column(String(ADDRESS_LENGTH), primary_key=True)
    hash_algorithm: Mapped[str] = mapped_column(String(20), nullable=False)
    digest: Mapped[str] = mapped_column(String(128), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    #: How the bytes were normalised before hashing, or "none". Canonical
    #: metadata (`MS §Artifact Fabric`); recorded, never inferred.
    normalization: Mapped[str] = mapped_column(String(METADATA_LENGTH), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    provenance: Mapped[ArtifactProvenanceRecord | None] = relationship(
        back_populates="artifact", uselist=False, cascade="save-update"
    )


class ArtifactProvenanceRecord(PersistenceBase):
    """How an artifact came to exist.

    One row per artifact. Every column is a canonical metadata item named by
    `MS §Artifact Fabric` and `VDC §Provenance`; a control reconciles this table
    against `docs/contracts/artifact.md` so neither can drift.
    """

    __tablename__ = PROVENANCE_TABLE

    artifact_id: Mapped[str] = mapped_column(
        String(ADDRESS_LENGTH),
        ForeignKey(f"{ARTIFACT_TABLE}.artifact_id"),
        primary_key=True,
    )
    producer_agent: Mapped[str] = mapped_column(String(METADATA_LENGTH), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(METADATA_LENGTH), nullable=False)
    task_id: Mapped[str] = mapped_column(String(METADATA_LENGTH), nullable=False)
    specification_version: Mapped[str] = mapped_column(
        String(METADATA_LENGTH), nullable=False
    )
    context_hash: Mapped[str] = mapped_column(String(METADATA_LENGTH), nullable=False)
    #: References to tests and evidence records. References only: the evidence
    #: chain itself belongs to `evidence.audit` (Package 2, Protected Core).
    tests: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    artifact: Mapped[ArtifactRecord] = relationship(back_populates="provenance")


class ArtifactParentEdge(PersistenceBase):
    """`artifact_id` was derived from `parent_artifact_id`.

    `position` preserves declared order without making order part of identity:
    two artifacts with the same bytes are the same artifact however their parents
    were listed.
    """

    __tablename__ = PARENT_TABLE

    artifact_id: Mapped[str] = mapped_column(
        String(ADDRESS_LENGTH),
        ForeignKey(f"{ARTIFACT_TABLE}.artifact_id"),
        primary_key=True,
    )
    parent_artifact_id: Mapped[str] = mapped_column(
        String(ADDRESS_LENGTH),
        ForeignKey(f"{ARTIFACT_TABLE}.artifact_id"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


def _refuse(table: str, identity: str) -> ArtifactImmutabilityViolation:
    return ArtifactImmutabilityViolation(
        f"{table} row {identity!r} is immutable; artifacts are never updated, and "
        "different bytes are a different artifact with a different address",
        source="docs/contracts/artifact.md section 3",
    )


@event.listens_for(ArtifactRecord, "before_update", propagate=True)
def _refuse_artifact_update(
    _mapper: object, _connection: object, target: ArtifactRecord
) -> None:
    raise _refuse(ARTIFACT_TABLE, target.artifact_id)


@event.listens_for(ArtifactProvenanceRecord, "before_update", propagate=True)
def _refuse_provenance_update(
    _mapper: object, _connection: object, target: ArtifactProvenanceRecord
) -> None:
    raise _refuse(PROVENANCE_TABLE, target.artifact_id)


@event.listens_for(ArtifactParentEdge, "before_update", propagate=True)
def _refuse_parent_update(
    _mapper: object, _connection: object, target: ArtifactParentEdge
) -> None:
    raise _refuse(PARENT_TABLE, f"{target.artifact_id}<-{target.parent_artifact_id}")
