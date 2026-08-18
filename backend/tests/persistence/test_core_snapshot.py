"""Core-upgrade snapshot on real persistence and a real C-14 artifact store
(ARK-REQ-0137). Real SQLite, real ArtifactStore, real StableRevisionPointer -
nothing substituted, matching `test_recovery_supervisor.py`'s own discipline.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.evolution.core_upgrade_orchestrator import begin_core_upgrade
from arkali.lifecycle.recovery.core_snapshot import (
    CoreSnapshotRecord,
    NoStableRevisionToSnapshotError,
    SnapshotNotRestorableError,
    take_core_snapshot,
)
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
REV_A = "sha256:" + "a" * 64


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "core_snapshot.db"
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


class TestTakeCoreSnapshot:
    def test_refuses_when_no_stable_revision_exists(
        self, engine: Engine, pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            with pytest.raises(NoStableRevisionToSnapshotError):
                take_core_snapshot(pointer, artifacts, candidate_id="cand-1")
        assert pointer.current() is None

    def test_a_genuine_snapshot_proves_restorable_and_records_the_current_revision(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "cand-0"), revision_id=REV_A, candidate_id="cand-0"
        )
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            record = take_core_snapshot(pointer, artifacts, candidate_id="cand-1")

        assert isinstance(record, CoreSnapshotRecord)
        assert record.revision_id == REV_A
        assert record.candidate_id == "cand-1"
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            assert artifacts.verify(record.artifact_id) is True

    def test_snapshotting_does_not_mutate_the_pointer(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "cand-0"), revision_id=REV_A, candidate_id="cand-0"
        )
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            take_core_snapshot(pointer, artifacts, candidate_id="cand-1")
        assert pointer.current() is not None
        assert pointer.current().revision_id == REV_A  # type: ignore[union-attr]
        assert pointer.history() == ()  # nothing has been superseded yet


class _RevisionRecord:
    def __init__(self, revision_id: str) -> None:
        self.revision_id = revision_id


class _UnverifiablePointer:
    """A minimal test double reporting a current revision - `take_core_
    snapshot`'s own refusal is exercised without depending on a real
    tampered blob."""

    def current(self) -> _RevisionRecord:
        return _RevisionRecord(REV_A)


class _RefusingArtifactStore:
    """A minimal test double whose `verify` always reports the write did
    not prove restorable, proving `take_core_snapshot` refuses rather than
    trusts the registration alone."""

    def register(self, payload: bytes, provenance: object) -> str:
        return "sha256:" + "b" * 64

    def verify(self, address: str) -> bool:
        return False

    def content_of(self, address: str) -> bytes:
        raise AssertionError("must not be reached once verify() is False")


class TestSnapshotRefusesRatherThanTrustsTheWrite:
    def test_a_failed_verification_is_refused_not_trusted(self) -> None:
        with pytest.raises(SnapshotNotRestorableError):
            take_core_snapshot(
                _UnverifiablePointer(),  # type: ignore[arg-type]
                _RefusingArtifactStore(),  # type: ignore[arg-type]
                candidate_id="cand-1",
            )


class _RealSnapshotProof:
    """Composition-root adapter satisfying `RestorableSnapshotProof` over the
    real `take_core_snapshot` - matches `PepRollbackAuthorization`'s own
    shape: the concrete call is real, only the Protocol boundary moves."""

    def __init__(self, pointer: StableRevisionPointer, artifacts: ArtifactStore) -> None:
        self._pointer = pointer
        self._artifacts = artifacts

    def take_snapshot(self, *, candidate_id: str) -> str:
        return take_core_snapshot(
            self._pointer, self._artifacts, candidate_id=candidate_id
        ).revision_id


class TestBeginCoreUpgrade:
    def test_no_instance_is_obtainable_without_a_real_stable_revision(
        self, engine: Engine, pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            proof = _RealSnapshotProof(pointer, artifacts)
            with pytest.raises(NoStableRevisionToSnapshotError):
                begin_core_upgrade(proof, candidate_id="cand-1")

    def test_a_real_snapshot_yields_a_snapshot_taken_instance(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "cand-0"), revision_id=REV_A, candidate_id="cand-0"
        )
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            proof = _RealSnapshotProof(pointer, artifacts)
            instance, revision_id = begin_core_upgrade(proof, candidate_id="cand-1")

        assert instance.state == "SNAPSHOT_TAKEN"
        assert revision_id == REV_A
