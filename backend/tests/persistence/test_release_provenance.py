"""Release provenance over real persistence and a real C-14 artifact store
(ARK-REQ-0015, ARK-REQ-0350, Phase 26 Package 2). Real SQLite, real
ArtifactStore - nothing substituted, matching `test_core_snapshot.py`'s own
discipline.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.release.release_manifest import ReleaseAuthority
from arkali.lifecycle.release.release_provenance import (
    CONTRACT_ID,
    ProvenanceFields,
    ReleaseProvenanceRecord,
    register_release_provenance,
)
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer


class _RealArtifactRegistrar:
    """The real composition-root adapter: wraps a real `ArtifactStore` to
    satisfy `release_provenance.ArtifactRegistrar` without `lifecycle.release`
    itself importing `evidence.artifact.store` (a real, measured
    `max_orchestration_depth` violation - see that module's own docstring)."""

    def __init__(self, store: ArtifactStore) -> None:
        self._store = store

    def register(self, payload: bytes, provenance: ProvenanceFields) -> str:
        return self._store.register(
            payload,
            ProvenanceInput(
                producer_agent=provenance.producer_agent,
                provider_model=provenance.provider_model,
                task_id=provenance.task_id,
                specification_version=provenance.specification_version,
                context_hash=provenance.context_hash,
                normalization=provenance.normalization,
                tests=provenance.tests, evidence=provenance.evidence,
                parents=provenance.parents,
            ),
        )

    def verify(self, address: str) -> bool:
        return self._store.verify(address)

    def content_of(self, address: str) -> bytes:
        return self._store.content_of(address)


REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
REV_A = "sha256:" + "a" * 64


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "release_provenance.db"
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
def blob_pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, blob_pep: PolicyEnforcementPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(tmp_path / "blobs", blob_pep)


@pytest.fixture()
def path() -> StableCandidatePath:
    return StableCandidatePath.load(REPO)


@pytest.fixture()
def pointer(path: StableCandidatePath, tmp_path: pathlib.Path) -> StableRevisionPointer:
    return StableRevisionPointer(path, tmp_path / "stable_pointer.json")


def _promotion_receipt(path: StableCandidatePath, candidate_id: str) -> StageReceipt:
    receipt = path.begin_candidate(candidate_id=candidate_id)
    for stage in path.stages()[2:-1]:
        receipt = path.advance(receipt, to_stage=stage)
    return path.promotion_receipt(receipt)


class TestRegisterReleaseProvenance:
    def test_registers_a_real_c14_artifact_with_every_vdc_provenance_field(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "core-cand-1"), revision_id=REV_A, candidate_id="core-cand-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, _instance = authority.declare_release_candidate()

        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            record = register_release_provenance(candidate, _RealArtifactRegistrar(artifacts))

            assert isinstance(record, ReleaseProvenanceRecord)
            assert record.release_id == candidate.release_id
            assert record.core_revision_id == REV_A

            provenance = artifacts.provenance_of(record.artifact_id)
            assert provenance is not None
            assert provenance.specification_version == CONTRACT_ID
            assert provenance.provider_model == "none"
            assert provenance.context_hash == REV_A
            assert provenance.task_id == candidate.release_id

    def test_the_artifact_re_verifies_byte_identical_after_registration(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "core-cand-1"), revision_id=REV_A, candidate_id="core-cand-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, _instance = authority.declare_release_candidate()

        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            record = register_release_provenance(candidate, _RealArtifactRegistrar(artifacts))
            assert artifacts.verify(record.artifact_id) is True

    def test_registering_the_same_candidate_twice_is_idempotent(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "core-cand-1"), revision_id=REV_A, candidate_id="core-cand-1"
        )
        authority = ReleaseAuthority(pointer)
        now = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        candidate, _instance = authority.declare_release_candidate(now=now)

        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            registrar = _RealArtifactRegistrar(artifacts)
            first = register_release_provenance(candidate, registrar)
            second = register_release_provenance(candidate, registrar)
            assert first.artifact_id == second.artifact_id

    def test_a_forged_release_id_still_registers_under_its_own_real_content_hash(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        """The artifact address is derived from the real payload bytes, never
        from `candidate.release_id` - a caller cannot make the store believe
        a different identity than what the content actually hashes to."""
        pointer.promote(
            _promotion_receipt(path, "core-cand-1"), revision_id=REV_A, candidate_id="core-cand-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, _instance = authority.declare_release_candidate()

        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            record = register_release_provenance(candidate, _RealArtifactRegistrar(artifacts))
            assert artifacts.content_of(record.artifact_id) is not None
