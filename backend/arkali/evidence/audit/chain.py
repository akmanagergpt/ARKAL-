"""C-15 audit chain: the sole write authority for evidence records.

Owner: `evidence.audit` (Protected Core).

THE PUBLIC SURFACE IS DELIBERATELY SMALL. `append`, `get`, `require`, `head`,
`records`, `verify`, `superseded_by`. There is no `update`, `amend`,
`overwrite`, `replace`, `delete` or `purge`, and a control asserts no such name
appears in this context. Correcting an outcome means appending a record that
supersedes the old one; the old one stays visible in `records()` forever.

SOLE WRITER (section 2.2 rule 7). `evidence.audit` owns the chain and no other
context may write or amend an evidence record. Other contexts call `append`;
none constructs `AuditRecord` or imports its table, and a structural control
proves that over the whole package tree rather than trusting it.

IDENTITY IS DERIVED. `append` computes `record_hash` from the record's own
fields and its predecessor's digest. There is no parameter by which a caller can
name the record it is writing, so the digest cannot disagree with the content.

LINKAGE IS CHECKED AT APPEND (section 2.2 rules 2 and 3). The requirement must
exist in the canonical register - the sole denominator, read at call time - and
the artifact must be one `evidence.artifact` has actually registered.

THE ARTIFACT CHECK IS THE FOREIGN KEY, NOT AN IMPORT. `evidence.artifact` is a
sibling in the same layer and `allow_same_layer: false`, so importing its mapped
record merely to ask "does this exist?" would be a same-layer edge surviving only
on the `evidence_write_from_any_layer` exemption - an exemption about *writes*,
not about reading another context's tables. The persisted reference contract
already answers the question: `audit_record.artifact_id` is a real foreign key
into C-14, so the database refuses an unregistered reference. The insert is
attempted inside a SAVEPOINT and the driver's refusal is translated into this
context's typed error, so the guarantee is enforced by the schema and the caller
still gets a domain refusal rather than a driver exception.

NO SELF-AUDIT RECURSION. Appending is a governed write and consults the PEP; the
PEP records its decision on its own Phase 4 trail, which is not this chain.
Nothing here appends an evidence record about its own append, so the boundary is
structural rather than a depth counter.

TRANSACTION BOUNDARIES BELONG TO THE CALLER. Like `ProjectRegistry` and
`ArtifactStore`, this service never commits.
"""

from __future__ import annotations

import pathlib
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.secret_reference import assert_no_raw_secret
from arkali.control.specification.register_parser import RequirementRegister
from arkali.evidence.audit.errors import (
    IllegalSupersession,
    InvalidEvidenceRecord,
    OrphanEvidence,
    UnknownEvidenceRecord,
)
from arkali.evidence.audit.integrity import (
    ChainVerification,
    digest_of,
    require_intact,
    verify_chain,
)
from arkali.evidence.audit.records import AuditRecord, utc_now
from arkali.kernel.contracts.results import HonestState

#: The actor this context presents to the PDP.
ACTOR: Final[str] = "evidence.audit"
TRUST_TIER: Final[str] = "TRUST-0"

READ: Final[str] = "READ_FILE"
WRITE: Final[str] = "WRITE_WORKSPACE_FILE"

#: The sink Phase 4 declared for the evidence path. Used, not redefined.
SECRET_SINK: Final[str] = "evidence artifact"


def canonical_results() -> frozenset[str]:
    """The `Result` vocabulary, read from the kernel rather than listed here."""
    return frozenset(state.value for state in HonestState)


class EvidenceInput:
    """What a producer must supply to append one evidence record.

    A value object rather than seven keyword arguments, because
    `max_parameters_per_public_function` is 6 and ADR-0008 makes decomposition
    the answer to a budget. It carries no identity field: `record_hash`,
    `previous_hash` and `sequence` are derived by the chain, so there is nothing
    here a caller could use to name the record it is writing.
    """

    __slots__ = (
        "requirement_id", "artifact_id", "producer", "result",
        "contract_id", "test_id", "supersedes",
    )

    def __init__(
        self,
        *,
        requirement_id: str,
        artifact_id: str,
        producer: str,
        result: str,
        contract_id: str | None = None,
        test_id: str | None = None,
        supersedes: str | None = None,
    ) -> None:
        self.requirement_id = requirement_id
        self.artifact_id = artifact_id
        self.producer = producer
        self.result = result
        self.contract_id = contract_id
        self.test_id = test_id
        self.supersedes = supersedes

    def strings(self) -> tuple[str, ...]:
        """Every value that will be persisted, for the secret guard."""
        return (
            self.requirement_id, self.artifact_id, self.producer, self.result,
            self.contract_id or "", self.test_id or "",
        )


class AuditChain:
    """The append-only evidence chain over one session.

    `repo_root` is needed only to read the canonical requirement register, which
    is the denominator reachability is checked against. The PEP is injected;
    there is no default that would let a caller obtain a chain that writes
    without a policy decision.
    """

    def __init__(
        self, session: Session, pep: PolicyEnforcementPoint, repo_root: pathlib.Path
    ) -> None:
        self._session = session
        self._pep = pep
        self._repo_root = pathlib.Path(repo_root)

    def _guard(self, operation: str) -> None:
        self._pep.require_auto(
            PolicyRequest(
                operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
            )
        )

    def records(self) -> tuple[AuditRecord, ...]:
        """Every record, oldest first. Superseded records are included."""
        self._guard(READ)
        rows = self._session.execute(
            select(AuditRecord).order_by(AuditRecord.sequence)
        ).scalars()
        return tuple(rows)

    def get(self, record_hash: str) -> AuditRecord | None:
        self._guard(READ)
        return self._session.execute(
            select(AuditRecord).where(AuditRecord.record_hash == record_hash)
        ).scalar_one_or_none()

    def require(self, record_hash: str) -> AuditRecord:
        found = self.get(record_hash)
        if found is None:
            raise UnknownEvidenceRecord(f"no evidence record {record_hash!r}")
        return found

    def head(self) -> AuditRecord | None:
        """The most recent record, or None on an empty chain."""
        self._guard(READ)
        return self._session.execute(
            select(AuditRecord).order_by(AuditRecord.sequence.desc()).limit(1)
        ).scalar_one_or_none()

    def verify(self) -> ChainVerification:
        """Recompute every digest and link. Never reads a stored status."""
        return verify_chain(self.records())

    def superseded_by(self, record_hash: str) -> AuditRecord | None:
        """The record that superseded this one, if any."""
        self._guard(READ)
        return self._session.execute(
            select(AuditRecord).where(AuditRecord.supersedes == record_hash)
        ).scalar_one_or_none()

    def _requirement_exists(self, requirement_id: str) -> bool:
        """Whether the canonical register declares this id.

        Read from `REQUIREMENT_REGISTER.md` at call time. The register is the
        sole denominator; a copy here would be a second one.
        """
        return requirement_id in set(
            RequirementRegister.load(self._repo_root).all_ids()
        )

    def _resolve_supersession(self, supersedes: str | None) -> AuditRecord | None:
        """Refuse an impossible supersession before anything is written."""
        if supersedes is None:
            return None
        target = self.get(supersedes)
        if target is None:
            raise UnknownEvidenceRecord(
                f"cannot supersede {supersedes!r}: no such evidence record"
            )
        already = self._session.execute(
            select(func.count()).select_from(AuditRecord).where(
                AuditRecord.supersedes == supersedes
            )
        ).scalar_one()
        if already:
            raise IllegalSupersession(
                f"record {supersedes!r} is already superseded; history is a chain, "
                "not a fan"
            )
        return target

    def append(self, evidence: EvidenceInput) -> AuditRecord:
        """Append one evidence record and return it.

        Every refusal below happens before anything is written, so a rejected
        record leaves no trace and no gap in the sequence.
        """
        for value in evidence.strings():
            assert_no_raw_secret(value, sink=SECRET_SINK)

        if evidence.result not in canonical_results():
            raise InvalidEvidenceRecord(
                f"{evidence.result!r} is not a canonical Result; the vocabulary "
                f"is {sorted(canonical_results())}"
            )
        if not evidence.producer.strip():
            raise InvalidEvidenceRecord(
                "an evidence record must name its producer "
                "(VERIFICATION_ARCHITECTURE section 2.1)"
            )
        if not self._requirement_exists(evidence.requirement_id):
            raise OrphanEvidence(
                f"{evidence.requirement_id!r} is not in the canonical requirement "
                "register; evidence unreachable from an ARK-REQ is structurally "
                "orphaned",
                source="docs/canonical/REQUIREMENT_REGISTER.md",
            )
        superseded = self._resolve_supersession(evidence.supersedes)

        # Extending a chain whose history no longer verifies would launder the
        # corruption into everything that follows.
        existing = self.records()
        require_intact(existing)
        previous = existing[-1] if existing else None

        self._guard(WRITE)
        record = AuditRecord(
            record_hash="",
            sequence=len(existing) + 1,
            previous_hash=None if previous is None else previous.record_hash,
            requirement_id=evidence.requirement_id,
            contract_id=evidence.contract_id,
            artifact_id=evidence.artifact_id,
            test_id=evidence.test_id,
            producer=evidence.producer,
            result=evidence.result,
            supersedes=None if superseded is None else superseded.record_hash,
            # Set explicitly rather than left to the column default: the digest
            # is taken over this value, so it must exist before it is hashed.
            recorded_at=utc_now(),
        )
        record.record_hash = digest_of(record)
        try:
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as refused:
            # The only reference this table can violate is the artifact foreign
            # key; the supersession target was resolved above and the digest is
            # derived, so neither can collide. The SAVEPOINT has rolled back, so
            # the session stays usable and no partial row survives.
            raise UnknownEvidenceRecord(
                f"artifact {evidence.artifact_id!r} is not registered; an evidence "
                "record references the artifact it was produced against"
            ) from refused
        return record
