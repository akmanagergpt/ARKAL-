"""C-14 artifact store on real persistence (T5/T11).

Every test drives a real SQLite file migrated by the real Alembic chain, a real
PDP loaded from the authority map, and a real filesystem blob store. Nothing is
substituted: the substitution policy in VERIFICATION_ARCHITECTURE.md makes a tier
from T5 upward that substitutes a database NOT_CONFIGURED, never PASS.

Scope note: this is Package 1 of Phase 6. It does NOT discharge ARK-REQ-0004,
ARK-REQ-0057 or ARK-REQ-0349 - `evidence.audit` (C-15) is Package 2, and
discharge belongs to the Phase 6 traceability record, report and gate in any
case.
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
from arkali.control.policy.policy_errors import RawSecretLeak
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.evidence.artifact import content_address
from arkali.evidence.artifact.blob_store import ACTOR, ArtifactBlobStore
from arkali.evidence.artifact.errors import (
    ArtifactContentMismatch,
    ArtifactImmutabilityViolation,
    InvalidArtifactIdentity,
    UnknownArtifact,
)
from arkali.evidence.artifact.records import (
    ArtifactParentEdge,
    ArtifactProvenanceRecord,
    ArtifactRecord,
)
from arkali.evidence.artifact.revision_link import provenance_ref_of, resolve
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI, applied_revision
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"


def alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "artifacts.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, pep: PolicyEnforcementPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(tmp_path / "blobs", pep)


def provenance(**overrides: object) -> ProvenanceInput:
    fields: dict[str, object] = {
        "producer_agent": "backend-engineer",
        "provider_model": "anthropic/claude",
        "task_id": "TASK-0001",
        "specification_version": "spec-1.0.0",
        "context_hash": "ctx-abc123",
        "normalization": "utf-8/lf",
    }
    fields.update(overrides)
    return ProvenanceInput(**fields)  # type: ignore[arg-type]


class TestRegistrationAndIdentity:
    def test_the_address_is_derived_from_the_bytes(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            address = ArtifactStore(session, blobs).register(b"hello", provenance())
        assert address == content_address.address_of(b"hello")

    def test_the_caller_cannot_supply_an_identity(self) -> None:
        """NEGATIVE CONTROL: there is no parameter to name an artifact.

        A store that accepted an identity would let the descriptor disagree with
        the content, which is the one failure content addressing prevents.
        """
        import inspect

        signature = inspect.signature(ArtifactStore.register)
        assert set(signature.parameters) == {"self", "payload", "provenance"}
        assert "artifact_id" not in ProvenanceInput.__slots__

    def test_registering_the_same_bytes_twice_is_idempotent(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            first = store.register(b"same", provenance())
            second = store.register(b"same", provenance(task_id="TASK-0002"))
            assert first == second
        with unit_of_work(create_session_factory(engine)) as session:
            rows = session.query(ArtifactRecord).all()
            assert len(rows) == 1

    def test_different_bytes_get_different_identities(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            assert store.register(b"one", provenance()) != store.register(
                b"two", provenance()
            )

    def test_an_unregistered_address_is_refused_by_type(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(UnknownArtifact):
                ArtifactStore(session, blobs).require(content_address.address_of(b"absent"))

    def test_a_malformed_address_is_refused_before_any_lookup(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(InvalidArtifactIdentity):
                ArtifactStore(session, blobs).get("not-an-address")


class TestProvenance:
    def test_every_canonical_metadata_item_is_persisted(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            address = ArtifactStore(session, blobs).register(
                b"metadata",
                provenance(tests=("T5::x",), evidence=("EV-0001",)),
            )
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            record = store.require(address)
            recorded = store.provenance_of(address)
            assert recorded is not None
            assert record.normalization == "utf-8/lf"
            assert record.byte_size == len(b"metadata")
            assert record.hash_algorithm == "sha256"
            assert record.digest == content_address.digest_of(b"metadata")
            assert recorded.producer_agent == "backend-engineer"
            assert recorded.provider_model == "anthropic/claude"
            assert recorded.task_id == "TASK-0001"
            assert recorded.specification_version == "spec-1.0.0"
            assert recorded.context_hash == "ctx-abc123"
            assert recorded.tests == ["T5::x"]
            assert recorded.evidence == ["EV-0001"]
            assert recorded.recorded_at is not None
            assert record.created_at is not None

    def test_parent_edges_are_recorded_in_order(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            first = store.register(b"p1", provenance())
            second = store.register(b"p2", provenance())
            child = store.register(b"child", provenance(parents=(first, second)))
            assert store.parents_of(child) == (first, second)

    def test_a_parent_that_was_never_registered_is_refused(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        """NEGATIVE CONTROL: a chain may not cite an artifact that never existed."""
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            ghost = content_address.address_of(b"never registered")
            with pytest.raises(UnknownArtifact):
                store.register(b"orphan child", provenance(parents=(ghost,)))


class TestImmutability:
    def test_a_persisted_artifact_cannot_be_updated(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            address = ArtifactStore(session, blobs).register(b"frozen", provenance())
        with pytest.raises(ArtifactImmutabilityViolation):
            with unit_of_work(factory) as session:
                record = ArtifactStore(session, blobs).require(address)
                record.normalization = "tampered"
                session.flush()

    def test_a_persisted_provenance_record_cannot_be_updated(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            address = ArtifactStore(session, blobs).register(b"frozen prov", provenance())
        with pytest.raises(ArtifactImmutabilityViolation):
            with unit_of_work(factory) as session:
                recorded = ArtifactStore(session, blobs).provenance_of(address)
                assert recorded is not None
                recorded.producer_agent = "someone else"
                session.flush()

    def test_a_parent_edge_cannot_be_updated(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            store = ArtifactStore(session, blobs)
            parent = store.register(b"pp", provenance())
            child = store.register(b"cc", provenance(parents=(parent,)))
        with pytest.raises(ArtifactImmutabilityViolation):
            with unit_of_work(factory) as session:
                edge = session.query(ArtifactParentEdge).filter_by(
                    artifact_id=child
                ).one()
                edge.position = 99
                session.flush()

    def test_a_refused_update_leaves_the_stored_value_unchanged(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            address = ArtifactStore(session, blobs).register(b"unchanged", provenance())
        with pytest.raises(ArtifactImmutabilityViolation):
            with unit_of_work(factory) as session:
                ArtifactStore(session, blobs).require(address).normalization = "x"
                session.flush()
        with unit_of_work(factory) as session:
            assert ArtifactStore(session, blobs).require(address).normalization == "utf-8/lf"


class TestContentVerification:
    def test_stored_content_verifies_against_its_address(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            address = store.register(b"verify me", provenance())
            assert store.verify(address)
            assert store.content_of(address) == b"verify me"

    def test_a_mutated_byte_is_detected_and_never_repaired(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        """The claim that makes content addressing worth having."""
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            address = ArtifactStore(session, blobs).register(b"original", provenance())

        blobs.path_for(address).write_bytes(b"tampered")

        with unit_of_work(factory) as session:
            store = ArtifactStore(session, blobs)
            assert store.verify(address) is False
            with pytest.raises(ArtifactContentMismatch):
                store.content_of(address)
            # The record still says what it always said; nothing was corrected.
            assert store.require(address).digest == content_address.digest_of(b"original")

    def test_reading_a_blob_that_is_absent_is_a_typed_refusal(
        self, blobs: ArtifactBlobStore
    ) -> None:
        with pytest.raises(UnknownArtifact):
            blobs.get(content_address.address_of(b"never stored"))

    def test_a_second_put_never_overwrites(self, blobs: ArtifactBlobStore) -> None:
        """Same address means same bytes, so there is no overwrite branch."""
        address = blobs.put(b"stable bytes")
        blobs.put(b"stable bytes")
        assert blobs.get(address) == b"stable bytes"


class TestPersistenceThroughRestart:
    def test_artifacts_survive_a_full_engine_restart(
        self, engine: Engine, database_path: pathlib.Path, blobs: ArtifactBlobStore
    ) -> None:
        """T11. A new engine on the same file, after the first is disposed."""
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            parent = store.register(b"durable parent", provenance())
            address = store.register(
                b"durable child", provenance(parents=(parent,), tests=("T11::restart",))
            )
        engine.dispose()

        restarted = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(restarted)) as session:
                store = ArtifactStore(session, blobs)
                assert store.require(address).byte_size == len(b"durable child")
                recorded = store.provenance_of(address)
                assert recorded is not None
                assert recorded.tests == ["T11::restart"]
                assert store.parents_of(address) == (parent,)
                assert store.content_of(address) == b"durable child"
        finally:
            restarted.dispose()

    def test_the_schema_revision_is_the_artifact_migration(
        self, engine: Engine
    ) -> None:
        assert applied_revision(engine) == "0003_artifact_provenance"
