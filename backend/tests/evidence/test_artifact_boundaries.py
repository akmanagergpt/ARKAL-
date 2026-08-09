"""C-14 security and linkage behaviour on real persistence.

Split from `test_artifact_store.py`, which reached 403 logical lines against the
400-line budget. ADR-0008 makes decomposition the answer to a budget rather than
an exception, and the seam is a real one: registration and identity on one side,
the boundaries the artifact plane must not cross on the other.

Same substitution policy as its sibling: real SQLite, real Alembic chain, real
PDP, real filesystem. Nothing here discharges a Phase 6 requirement.
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


class TestSecretsNeverEnterAnArtifact:
    @pytest.mark.parametrize(
        "field",
        ["producer_agent", "provider_model", "task_id", "specification_version",
         "context_hash", "normalization"],
    )
    def test_a_raw_secret_in_any_provenance_field_is_refused(
        self, engine: Engine, blobs: ArtifactBlobStore, field: str
    ) -> None:
        """ARK-REQ-0098. Reuses the Phase 4 guard for the 'evidence artifact' sink."""
        secret = "sk-" + "a" * 32
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(RawSecretLeak):
                ArtifactStore(session, blobs).register(
                    b"payload", provenance(**{field: f"prefix {secret}"})
                )

    def test_a_raw_secret_in_tests_or_evidence_is_refused(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        secret = "ghp_" + "b" * 36
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            for overrides in ({"tests": (secret,)}, {"evidence": (secret,)}):
                with pytest.raises(RawSecretLeak):
                    store.register(b"payload", provenance(**overrides))

    def test_nothing_was_persisted_when_a_secret_was_refused(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        """The refusal must happen before any row or blob is written."""
        secret = "sk-" + "c" * 32
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(RawSecretLeak):
                ArtifactStore(session, blobs).register(
                    b"secret payload", provenance(task_id=secret)
                )
        with unit_of_work(create_session_factory(engine)) as session:
            assert session.query(ArtifactRecord).count() == 0
            assert session.query(ArtifactProvenanceRecord).count() == 0
        assert not blobs.contains(content_address.address_of(b"secret payload"))

    def test_an_ordinary_reference_is_not_refused(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        """Proves the guard discriminates rather than rejecting everything."""
        with unit_of_work(create_session_factory(engine)) as session:
            ArtifactStore(session, blobs).register(
                b"ordinary", provenance(evidence=("EV-0043", "secret-vault://handle/h1"))
            )


class TestPolicyEnforcement:
    def test_every_blob_write_and_read_is_audited(
        self, engine: Engine, blobs: ArtifactBlobStore, pep: PolicyEnforcementPoint
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            store = ArtifactStore(session, blobs)
            address = store.register(b"audited", provenance())
            store.content_of(address)
        trail = pep.audit_trail
        assert trail
        assert {record.actor for record in trail} == {ACTOR}
        assert {record.operation_class for record in trail} == {
            "READ_FILE", "WRITE_WORKSPACE_FILE"
        }

    def test_the_real_pdp_denies_a_stable_write_to_this_actor(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """NEGATIVE CONTROL: DENY is a hard refusal for this actor too."""
        from arkali.control.policy.policy_contract import PolicyRequest
        from arkali.control.policy.policy_errors import PolicyDenied

        probe = PolicyEnforcementPoint(pdp, "probe")
        for operation in ("WRITE_STABLE_FILE", "ROLLBACK_STABLE"):
            with pytest.raises(PolicyDenied):
                probe.enforce(
                    PolicyRequest(
                        operation_class=operation, trust_tier="TRUST-0", actor=ACTOR
                    )
                )


class TestProjectRevisionLinkage:
    def test_a_revision_reference_resolves_to_the_artifact(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            address = ArtifactStore(session, blobs).register(b"revision bytes", provenance())
            registry = ProjectRegistry(session)
            registry.create_project("prj-1", "Linked")
            registry.create_revision("prj-1", "rev-1", address)
        with unit_of_work(factory) as session:
            store = ArtifactStore(session, blobs)
            assert provenance_ref_of(session, "rev-1") == address
            resolved = resolve(store, session, "rev-1")
            assert resolved is not None
            assert resolved.artifact_id == address

    def test_a_revision_without_a_reference_resolves_to_none(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        """Honest for every revision created before Phase 6."""
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-2", "Unlinked")
            registry.create_revision("prj-2", "rev-2", None)
        with unit_of_work(factory) as session:
            assert resolve(ArtifactStore(session, blobs), session, "rev-2") is None

    def test_a_hand_written_reference_cannot_masquerade_as_an_address(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        """NEGATIVE CONTROL: only derived identities enter the artifact surface."""
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-3", "Handwritten")
            registry.create_revision("prj-3", "rev-3", "artifact-42")
        with unit_of_work(factory) as session:
            with pytest.raises(InvalidArtifactIdentity):
                resolve(ArtifactStore(session, blobs), session, "rev-3")

    def test_c12_still_owns_revision_identity(
        self, engine: Engine, blobs: ArtifactBlobStore
    ) -> None:
        """Nothing in this package creates or renames a revision."""
        import inspect

        from arkali.evidence.artifact import revision_link

        source = inspect.getsource(revision_link)
        assert "create_revision" not in source
        assert "ProjectRevisionRecord(" not in source
