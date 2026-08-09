"""C-15 chain integrity: digests recomputed, never trusted.

Owner: `evidence.audit` (Protected Core).

WHY THERE IS NO STORED VERIFICATION FLAG. A boolean saying "this record is
intact" is written by the same actor that could have altered the record, so it
proves nothing and is trivially made to lie. Every function here recomputes the
digest from the stored fields and compares. There is no `integrity_verified`
column, no cached verdict, and a control asserts neither appears.

THE DIGEST COVERS THE PREDECESSOR. `digest_of` serialises every field of a record
*including* `previous_hash` and `sequence`, so the chain is a hash chain:
altering any field of any record changes that record's digest and breaks the
`previous_hash` of every record after it. A tamperer must therefore rewrite the
entire suffix, and `verify` walks the whole chain.

CANONICAL SERIALISATION. Fields are serialised in a fixed declared order with an
unambiguous separator and explicit null marker, so the digest is deterministic
across processes and hosts and no two distinct records can serialise alike.

FAILS CLOSED. Every structural fault - a broken digest, a broken link, a missing
predecessor, a gap in the sequence, two genesis records - is a refusal naming
what was wrong. An empty chain reports verified-empty, never verified-good.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel, ConfigDict

#: The shared kernel primitive, so one address shape exists in the repository
#: and this context does not import its sibling merely to hash bytes.
#: `evidence.artifact` keeps artifact identity; this is the mechanism only.
from arkali.kernel.contracts.content_address import address_of
from arkali.evidence.audit.errors import ChainIntegrityViolation
from arkali.evidence.audit.records import AuditRecord

#: Serialisation order. Declared once; `digest_of` iterates it, so a field added
#: to the record without being added here changes no digest and is caught by the
#: reconciliation control rather than silently escaping the hash.
DIGESTED_FIELDS: Final[tuple[str, ...]] = (
    "sequence",
    "previous_hash",
    "requirement_id",
    "contract_id",
    "artifact_id",
    "test_id",
    "producer",
    "result",
    "recorded_at",
    "supersedes",
)

#: Unambiguous field separator and null marker. `\x1f` is the ASCII unit
#: separator and cannot occur in a validated field, so no two distinct records
#: can serialise to the same string by concatenation.
_SEP: Final[str] = "\x1f"
_NULL: Final[str] = "\x00none"


def _render(value: object) -> str:
    if value is None:
        return _NULL
    if isinstance(value, dt.datetime):
        # Normalised to UTC and to microsecond ISO form, so the same instant
        # always renders identically regardless of the driver's tzinfo handling.
        moment = value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
        return moment.astimezone(dt.timezone.utc).isoformat(timespec="microseconds")
    return str(value)


def canonical_payload(record: AuditRecord) -> str:
    """The exact string a record's digest is taken over."""
    return _SEP.join(_render(getattr(record, name)) for name in DIGESTED_FIELDS)


def digest_of(record: AuditRecord) -> str:
    """The digest a record's fields imply. Never read from the record itself."""
    return address_of(canonical_payload(record).encode("utf-8"))


class ChainVerification(BaseModel):
    """The result of walking the chain. Reports, never repairs."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verified: bool
    length: int
    head: str | None
    faults: tuple[str, ...] = ()

    @property
    def is_empty(self) -> bool:
        return self.length == 0

    def render(self) -> str:
        state = "VERIFIED" if self.verified else "CORRUPT"
        if self.verified and self.is_empty:
            state = "VERIFIED_EMPTY"
        return f"{state} length={self.length} head={self.head} faults={list(self.faults)}"


def verify_chain(records: Sequence[AuditRecord]) -> ChainVerification:
    """Recompute every digest and every link.

    `records` must arrive ordered by `sequence`; the ordering itself is checked,
    so a caller cannot hide a gap by sorting around it.
    """
    ordered = list(records)
    if not ordered:
        return ChainVerification(verified=True, length=0, head=None)

    faults: list[str] = []
    genesis = [r for r in ordered if r.previous_hash is None]
    if len(genesis) != 1:
        faults.append(
            f"a chain must have exactly one genesis record; found {len(genesis)}"
        )

    previous: AuditRecord | None = None
    for position, record in enumerate(ordered, start=1):
        if record.sequence != position:
            faults.append(
                f"sequence {record.sequence} appears at position {position}; the "
                "chain is not contiguous from 1"
            )
        recomputed = digest_of(record)
        if recomputed != record.record_hash:
            faults.append(
                f"record {record.record_hash} recomputes to {recomputed}; its "
                "stored content no longer matches its digest"
            )
        if record.supersedes == record.record_hash:
            faults.append(
                f"record {record.record_hash} supersedes itself; a record cannot "
                "replace its own history"
            )
        expected_previous = None if previous is None else previous.record_hash
        if record.previous_hash != expected_previous:
            faults.append(
                f"record {record.record_hash} links to {record.previous_hash}, but "
                f"its predecessor is {expected_previous}"
            )
        previous = record

    return ChainVerification(
        verified=not faults,
        length=len(ordered),
        head=ordered[-1].record_hash,
        faults=tuple(faults),
    )


def require_intact(records: Sequence[AuditRecord]) -> ChainVerification:
    """Verify, and refuse to proceed on a corrupt chain.

    Used before an append: extending a chain whose history no longer verifies
    would launder the corruption into everything that follows.
    """
    verification = verify_chain(records)
    if not verification.verified:
        raise ChainIntegrityViolation(
            f"the evidence chain does not verify: {verification.render()}",
            source="docs/contracts/audit_record.md section 5",
        )
    return verification
