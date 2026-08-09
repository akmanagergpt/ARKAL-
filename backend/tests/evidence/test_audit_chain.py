"""C-15 audit / evidence integrity chain on real persistence.

Real SQLite migrated by the real Alembic chain, a real PDP from the authority
map, a real C-14 artifact store. Nothing is substituted.

Scope note: Package 2 of Phase 6. It does NOT discharge ARK-REQ-0004,
ARK-REQ-0057 or ARK-REQ-0349 - discharge belongs to the Phase 6 traceability
record, report and gate.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_errors import PolicyDenied, RawSecretLeak
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.evidence.audit.chain import (
    ACTOR,
    AuditChain,
    EvidenceInput,
    canonical_results,
)
from arkali.evidence.audit.errors import (
    ChainIntegrityViolation,
    EvidenceImmutabilityViolation,
    IllegalSupersession,
    InvalidEvidenceRecord,
    OrphanEvidence,
    UnknownEvidenceRecord,
)
from arkali.evidence.audit.integrity import digest_of, verify_chain
from arkali.evidence.audit.records import AuditRecord
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import (
    ALEMBIC_INI,
    applied_revision,
    head_revision,
)
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "evidence.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "evidence.audit.chain")


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, pep: PolicyEnforcementPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(tmp_path / "blobs", pep)


def register_artifact(session: object, blobs: ArtifactBlobStore, payload: bytes) -> str:
    return ArtifactStore(session, blobs).register(  # type: ignore[arg-type]
        payload,
        ProvenanceInput(
            producer_agent="pytest", provider_model="none", task_id="TASK-1",
            specification_version="spec-1", context_hash="ctx-1",
        ),
    )


@pytest.fixture()
def artifact(engine: Engine, blobs: ArtifactBlobStore) -> str:
    with unit_of_work(create_session_factory(engine)) as session:
        return register_artifact(session, blobs, b"evidence payload")


def chain_of(engine: Engine, pep: PolicyEnforcementPoint):  # noqa: ANN201
    return create_session_factory(engine), pep


def detached(record: AuditRecord, **changes: object) -> AuditRecord:
    """A detached copy of a record, optionally altered.

    The ORM guard refuses any update to a persisted row, which is the point of
    it - so a tamper test cannot stage its own corruption through the session.
    These copies are never attached, so they exercise the *verification* logic
    on exactly the shape a corrupted row would present.
    """
    fields = {
        name: getattr(record, name)
        for name in (
            "record_hash", "sequence", "previous_hash", "requirement_id",
            "contract_id", "artifact_id", "test_id", "producer", "result",
            "recorded_at", "supersedes",
        )
    }
    fields.update(changes)
    return AuditRecord(**fields)


def tamper_on_disk(database_path: pathlib.Path, record_hash: str, **columns: str) -> None:
    """Alter a stored row behind the ORM, as someone with file access could.

    This is the threat the `before_update` guard cannot address: it protects the
    application path, not the file. Raw SQL is used deliberately and only here -
    the engine-confinement control scopes its ban to `backend/arkali`, because
    tests do not ship and are not a production persistence path.
    """
    import sqlite3

    assignments = ", ".join(f"{name} = ?" for name in columns)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            f"UPDATE audit_record SET {assignments} WHERE record_hash = ?",  # noqa: S608
            (*columns.values(), record_hash),
        )
        connection.commit()
    finally:
        connection.close()


class TestAppendAndOrdering:
    def test_the_chain_starts_empty_and_verifies_as_empty(
        self, engine: Engine, pep: PolicyEnforcementPoint
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            verification = AuditChain(session, pep, REPO).verify()
        assert verification.verified
        assert verification.is_empty
        assert "VERIFIED_EMPTY" in verification.render()

    def test_records_are_appended_in_a_contiguous_chain(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            first = chain.append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
            second = chain.append(EvidenceInput(
                requirement_id="ARK-REQ-0057", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
            assert first.sequence == 1 and first.previous_hash is None
            assert second.sequence == 2
            assert second.previous_hash == first.record_hash
            assert chain.head().record_hash == second.record_hash
            assert chain.verify().verified

    def test_the_digest_is_derived_not_supplied(self) -> None:
        """NEGATIVE CONTROL: nothing a caller supplies can name the record."""
        import inspect

        supplied = set(inspect.signature(AuditChain.append).parameters)
        assert supplied == {"self", "evidence"}
        for derived in ("record_hash", "previous_hash", "sequence"):
            assert derived not in EvidenceInput.__slots__

    def test_the_result_vocabulary_comes_from_the_kernel(self) -> None:
        from arkali.kernel.contracts.results import HonestState

        assert canonical_results() == {state.value for state in HonestState}

    def test_a_non_canonical_result_is_refused(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(InvalidEvidenceRecord):
                AuditChain(session, pep, REPO).append(EvidenceInput(
                    requirement_id="ARK-REQ-0004", artifact_id=artifact,
                    producer="pytest", result="PROBABLY_FINE",
                ))

    def test_a_record_without_a_producer_is_refused(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(InvalidEvidenceRecord):
                AuditChain(session, pep, REPO).append(EvidenceInput(
                    requirement_id="ARK-REQ-0004", artifact_id=artifact,
                    producer="   ", result="PASS",
                ))


class TestAppendOnly:
    def test_a_persisted_record_cannot_be_updated(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            AuditChain(session, pep, REPO).append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
        with pytest.raises(EvidenceImmutabilityViolation):
            with unit_of_work(factory) as session:
                record = session.query(AuditRecord).one()
                record.result = "FAIL"
                session.flush()

    def test_a_persisted_record_cannot_be_deleted(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """A chain you can delete from is not a chain."""
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            AuditChain(session, pep, REPO).append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
        with pytest.raises(EvidenceImmutabilityViolation):
            with unit_of_work(factory) as session:
                session.delete(session.query(AuditRecord).one())
                session.flush()

    def test_the_public_authority_exposes_no_escape(self) -> None:
        """NEGATIVE CONTROL: no update/amend/overwrite/delete on the API."""
        public = {name for name in dir(AuditChain) if not name.startswith("_")}
        for forbidden in (
            "update", "amend", "overwrite", "replace", "delete", "purge",
            "edit", "set_result", "rewrite",
        ):
            assert forbidden not in public
        assert public == {"append", "get", "require", "head", "records",
                          "verify", "superseded_by"}

    def test_append_only_survives_reopen(
        self, engine: Engine, database_path: pathlib.Path,
        pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            AuditChain(session, pep, REPO).append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
        engine.dispose()
        restarted = create_persistence_engine(sqlite_url(database_path))
        try:
            with pytest.raises(EvidenceImmutabilityViolation):
                with unit_of_work(create_session_factory(restarted)) as session:
                    session.query(AuditRecord).one().producer = "someone else"
                    session.flush()
        finally:
            restarted.dispose()


class TestIntegrityIsRecomputed:
    def test_content_mutation_is_detected(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """The record's own digest no longer matches its fields."""
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            chain = AuditChain(session, pep, REPO)
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0004", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            altered = detached(chain.records()[0], result="FAIL")
            assert digest_of(altered) != altered.record_hash
            assert not verify_chain([altered]).verified

    def test_metadata_mutation_is_detected(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0004", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            altered = detached(chain.records()[0], producer="impostor")
            assert not verify_chain([altered]).verified

    def test_linkage_mutation_is_detected(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0004", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0057", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            records = list(chain.records())
            broken = [records[0], detached(records[1], previous_hash=None)]
            verification = verify_chain(broken)
            assert not verification.verified
            assert any("links to" in fault for fault in verification.faults)

    def test_a_missing_predecessor_is_detected(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """Dropping the genesis record leaves an unanchored chain."""
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0004", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0057", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            verification = verify_chain(list(chain.records())[1:])
            assert not verification.verified
            assert any("genesis" in f for f in verification.faults)

    def test_ordering_corruption_is_detected(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0004", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0057", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            reversed_chain = list(reversed(chain.records()))
            assert not verify_chain(reversed_chain).verified

    def test_verification_recomputes_rather_than_trusting_a_stored_status(
        self,
    ) -> None:
        """NEGATIVE CONTROL: no stored flag exists to trust."""
        columns = {c.name for c in AuditRecord.__table__.columns}
        for forbidden in ("integrity_verified", "verified", "is_valid", "checksum_ok"):
            assert forbidden not in columns
        from arkali.evidence.audit import integrity

        assert "digest_of(record)" in pathlib.Path(integrity.__file__).read_text(
            encoding="utf-8"
        )

    def test_on_disk_tampering_is_detected_after_reopen(
        self, engine: Engine, database_path: pathlib.Path,
        pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """The threat the ORM guard cannot reach: the file itself.

        `before_update` protects the application path. Someone with file access
        goes around it entirely, so the integrity chain - not the guard - is what
        has to notice.
        """
        with unit_of_work(create_session_factory(engine)) as session:
            record = AuditChain(session, pep, REPO).append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
            tampered_hash = record.record_hash
        engine.dispose()

        tamper_on_disk(database_path, tampered_hash, result="FAIL")

        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                verification = AuditChain(session, pep, REPO).verify()
                assert not verification.verified
                assert any("recomputes to" in f for f in verification.faults)
        finally:
            reopened.dispose()

    def test_a_corrupt_chain_cannot_be_extended(
        self, engine: Engine, database_path: pathlib.Path,
        pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """Appending onto corruption would launder it into everything after."""
        with unit_of_work(create_session_factory(engine)) as session:
            record = AuditChain(session, pep, REPO).append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
            target = record.record_hash
        engine.dispose()

        tamper_on_disk(database_path, target, producer="impostor")

        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                with pytest.raises(ChainIntegrityViolation):
                    AuditChain(session, pep, REPO).append(EvidenceInput(
                        requirement_id="ARK-REQ-0057", artifact_id=artifact,
                        producer="pytest", result="PASS",
                    ))
        finally:
            reopened.dispose()

    def test_the_chain_verifies_after_close_and_reopen(
        self, engine: Engine, database_path: pathlib.Path,
        pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            for requirement in ("ARK-REQ-0004", "ARK-REQ-0057", "ARK-REQ-0349"):
                chain.append(EvidenceInput(requirement_id=requirement, artifact_id=artifact,
                             producer="pytest", result="PASS"))
        engine.dispose()
        restarted = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(restarted)) as session:
                verification = AuditChain(session, pep, REPO).verify()
                assert verification.verified
                assert verification.length == 3
        finally:
            restarted.dispose()

    def test_the_database_is_at_the_declared_chain_head(self, engine: Engine) -> None:
        """Derived, never transcribed (F-0032)."""
        assert applied_revision(engine) == head_revision(BACKEND)
