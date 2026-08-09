"""C-15 evidence record: the append-only audit chain table.

Owner: `evidence.audit` (Protected Core).

APPEND-ONLY IS ENFORCED, NOT REQUESTED. The table refuses `before_update` **and**
`before_delete`. `VERIFICATION_ARCHITECTURE.md` section 2.2 rule 1 says evidence
is never edited or deleted and a superseded result is retained under a
`supersedes` edge; that invariant does not depend on callers choosing not to
write, and deletion is refused as firmly as modification because a chain you can
delete from is not a chain.

THE DIGEST COVERS THE PREDECESSOR. `record_hash` is derived over every field
including `previous_hash` and `sequence`, so altering any record breaks the
linkage of every record after it. The digest is computed by `integrity.py`; this
module stores it and never derives one.

REFERENCES, NOT COPIES. `artifact_id` is a foreign key into C-14's table. This
context mints no artifact identity and stores no artifact metadata beyond the
reference - `evidence.artifact` is the identity authority and a control asserts
this context computes no digest of artifact content.

ENGINE-NEUTRAL (ARK-REQ-0012). Declarative mapping only, on the kernel base.
`String`, `Integer`, `DateTime` and standard constraints, rendered for SQLite and
PostgreSQL alike. No engine, driver, dialect branch or raw SQL.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from sqlalchemy import DateTime, ForeignKey, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column

from arkali.evidence.audit.errors import EvidenceImmutabilityViolation
from arkali.kernel.persistence.base import PersistenceBase

AUDIT_TABLE: Final[str] = "audit_record"
ARTIFACT_TABLE: Final[str] = "artifact"

#: `sha256:` + 64 hex characters, the same address shape C-14 uses.
DIGEST_LENGTH: Final[int] = 71
FIELD_LENGTH: Final[int] = 200


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class AuditRecord(PersistenceBase):
    """One evidence record in the chain.

    The `Evidence` node of `VERIFICATION_ARCHITECTURE.md` section 2.1 - record,
    timestamp and producer - carrying the `Result` it yields and the linkage that
    makes it reachable from a requirement.
    """

    __tablename__ = AUDIT_TABLE

    record_hash: Mapped[str] = mapped_column(String(DIGEST_LENGTH), primary_key=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    #: NULL for the genesis record only; `integrity.py` refuses a second genesis.
    previous_hash: Mapped[str | None] = mapped_column(
        String(DIGEST_LENGTH), nullable=True
    )
    #: Reachability from the canonical denominator (section 2.2 rule 3).
    requirement_id: Mapped[str] = mapped_column(String(FIELD_LENGTH), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(String(FIELD_LENGTH), nullable=True)
    #: The artifact this evidence was produced against (section 2.2 rule 2).
    artifact_id: Mapped[str] = mapped_column(
        String(DIGEST_LENGTH),
        ForeignKey(f"{ARTIFACT_TABLE}.artifact_id"),
        nullable=False,
    )
    test_id: Mapped[str | None] = mapped_column(String(FIELD_LENGTH), nullable=True)
    producer: Mapped[str] = mapped_column(String(FIELD_LENGTH), nullable=False)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    supersedes: Mapped[str | None] = mapped_column(
        String(DIGEST_LENGTH), ForeignKey(f"{AUDIT_TABLE}.record_hash"), nullable=True
    )


def _refuse(action: str, identity: str) -> EvidenceImmutabilityViolation:
    return EvidenceImmutabilityViolation(
        f"evidence record {identity!r} cannot be {action}; the chain is "
        "append-only and a corrected outcome is a NEW record that supersedes "
        "this one, which stays visible",
        source="docs/contracts/audit_record.md section 4",
    )


@event.listens_for(AuditRecord, "before_update", propagate=True)
def _refuse_update(_mapper: object, _connection: object, target: AuditRecord) -> None:
    raise _refuse("modified", target.record_hash)


@event.listens_for(AuditRecord, "before_delete", propagate=True)
def _refuse_delete(_mapper: object, _connection: object, target: AuditRecord) -> None:
    raise _refuse("deleted", target.record_hash)
