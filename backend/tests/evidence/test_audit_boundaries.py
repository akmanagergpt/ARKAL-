"""C-15 linkage and security boundaries on real persistence.

Split from `test_audit_chain.py`, which reached 562 logical lines against the
400-line budget. ADR-0008 makes decomposition the answer to a budget rather than
an exception, and the seam is a real one: how the chain behaves on one side, and
what it refuses to let across its boundary on the other.

Same substitution policy as its sibling: real SQLite, real Alembic chain, real
PDP, real C-14 store. Nothing here discharges a Phase 6 requirement.
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


class TestOrphanEvidenceAndReferences:
    def test_an_unknown_requirement_is_refused(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """Section 2.2 rule 3, enforced at the storage boundary."""
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(OrphanEvidence):
                AuditChain(session, pep, REPO).append(EvidenceInput(
                    requirement_id="ARK-REQ-9999", artifact_id=artifact,
                    producer="pytest", result="PASS",
                ))

    def test_the_register_is_read_not_copied(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """Every real Phase 6 requirement is acceptable; a fabricated one is not."""
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            for requirement in ("ARK-REQ-0004", "ARK-REQ-0057", "ARK-REQ-0349"):
                chain.append(EvidenceInput(requirement_id=requirement, artifact_id=artifact,
                             producer="pytest", result="PASS"))
            assert len(chain.records()) == 3

    def test_an_unregistered_artifact_reference_is_refused(
        self, engine: Engine, pep: PolicyEnforcementPoint
    ) -> None:
        """Section 2.2 rule 2: evidence references the artifact it came from."""
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(UnknownEvidenceRecord):
                AuditChain(session, pep, REPO).append(EvidenceInput(
                    requirement_id="ARK-REQ-0004",
                    artifact_id="sha256:" + "a" * 64,
                    producer="pytest", result="PASS",
                ))

    def test_a_refused_append_leaves_no_trace(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """No row, and no gap in the sequence."""
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0004", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            with pytest.raises(OrphanEvidence):
                chain.append(EvidenceInput(requirement_id="ARK-REQ-9999", artifact_id=artifact,
                             producer="pytest", result="PASS"))
            after = chain.append(EvidenceInput(requirement_id="ARK-REQ-0057", artifact_id=artifact,
                                 producer="pytest", result="PASS"))
            assert after.sequence == 2
            assert chain.verify().verified


class TestSecurity:
    def test_every_operation_is_audited_through_the_phase_4_pep(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            AuditChain(session, pep, REPO).append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
        trail = [r for r in pep.audit_trail if r.actor == ACTOR]
        assert trail
        assert {r.operation_class for r in trail} <= {"READ_FILE", "WRITE_WORKSPACE_FILE"}

    def test_the_real_pdp_denies_a_stable_write_to_this_actor(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        from arkali.control.policy.policy_contract import PolicyRequest

        probe = PolicyEnforcementPoint(pdp, "probe")
        for operation in ("WRITE_STABLE_FILE", "ROLLBACK_STABLE"):
            with pytest.raises(PolicyDenied):
                probe.enforce(
                    PolicyRequest(
                        operation_class=operation, trust_tier="TRUST-0", actor=ACTOR
                    )
                )

    @pytest.mark.parametrize(
        "field", ["producer", "contract_id", "test_id", "requirement_id"]
    )
    def test_a_secret_shaped_value_is_refused(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str, field: str
    ) -> None:
        secret = "sk-" + "z" * 32
        payload = {
            "requirement_id": "ARK-REQ-0004", "artifact_id": artifact,
            "producer": "pytest", "result": "PASS",
        }
        payload[field] = f"prefix {secret}"
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(RawSecretLeak):
                AuditChain(session, pep, REPO).append(
                    EvidenceInput(**payload)  # type: ignore[arg-type]
                )

    def test_a_refused_secret_persists_nothing(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(RawSecretLeak):
                AuditChain(session, pep, REPO).append(EvidenceInput(
                    requirement_id="ARK-REQ-0004", artifact_id=artifact,
                    producer="sk-" + "y" * 32, result="PASS",
                ))
        with unit_of_work(create_session_factory(engine)) as session:
            assert session.query(AuditRecord).count() == 0

    def test_appending_does_not_recurse(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """One append produces exactly one record, not a cascade.

        The PEP keeps its own decision trail; that trail is not this chain, so
        auditing an append cannot append.
        """
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            chain.append(EvidenceInput(requirement_id="ARK-REQ-0004", artifact_id=artifact,
                         producer="pytest", result="PASS"))
            assert len(chain.records()) == 1


class TestSupersession:
    def test_supersession_appends_and_preserves(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            original = chain.append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="FAIL",
            ))
            corrected = chain.append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS", supersedes=original.record_hash,
            ))
            assert corrected.supersedes == original.record_hash
            assert chain.get(original.record_hash) is not None
            assert chain.get(original.record_hash).result == "FAIL"
            assert len(chain.records()) == 2
            assert chain.verify().verified

    def test_multi_generation_supersession(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            generations = []
            previous = None
            for result in ("FAIL", "BLOCKED", "PASS"):
                record = chain.append(EvidenceInput(
                    requirement_id="ARK-REQ-0004", artifact_id=artifact,
                    producer="pytest", result=result, supersedes=previous,
                ))
                generations.append(record)
                previous = record.record_hash
            assert [r.result for r in chain.records()] == ["FAIL", "BLOCKED", "PASS"]
            assert chain.superseded_by(generations[0].record_hash).record_hash == (
                generations[1].record_hash
            )
            assert chain.superseded_by(generations[2].record_hash) is None
            assert chain.verify().verified

    def test_superseding_a_nonexistent_record_is_refused(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(UnknownEvidenceRecord):
                AuditChain(session, pep, REPO).append(EvidenceInput(
                    requirement_id="ARK-REQ-0004", artifact_id=artifact,
                    producer="pytest", result="PASS",
                    supersedes="sha256:" + "0" * 64,
                ))

    def test_a_record_cannot_be_superseded_twice(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """History is a chain, not a fan."""
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            original = chain.append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="FAIL",
            ))
            chain.append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS", supersedes=original.record_hash,
            ))
            with pytest.raises(IllegalSupersession):
                chain.append(EvidenceInput(
                    requirement_id="ARK-REQ-0004", artifact_id=artifact,
                    producer="pytest", result="BLOCKED",
                    supersedes=original.record_hash,
                ))

    def test_self_supersession_is_structurally_impossible_and_detected(
        self, engine: Engine, pep: PolicyEnforcementPoint, artifact: str
    ) -> None:
        """A record cannot name its own digest, and tampering to do so is caught."""
        with unit_of_work(create_session_factory(engine)) as session:
            chain = AuditChain(session, pep, REPO)
            record = chain.append(EvidenceInput(
                requirement_id="ARK-REQ-0004", artifact_id=artifact,
                producer="pytest", result="PASS",
            ))
            # The digest is unknown until after the fields are fixed, so no
            # caller can pass it. Forcing it afterwards is caught by verify.
            verification = verify_chain(
                [detached(record, supersedes=record.record_hash)]
            )
            assert not verification.verified
            assert any("supersedes itself" in f for f in verification.faults)
