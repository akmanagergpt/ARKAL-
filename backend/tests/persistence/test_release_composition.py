"""Final release manifest composition over real persistence and a real C-14
artifact store (Phase 26 Package 6).
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
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.release.release_composition import (
    ReleaseManifestComposition,
    compose_release_manifest,
    verify_evidence_complete,
)
from arkali.lifecycle.release.release_manifest import ReleaseAuthority
from arkali.lifecycle.release.release_provenance import ProvenanceFields, register_release_provenance
from arkali.lifecycle.release.sbom import generate_sbom
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer
from arkali.lifecycle.release.suspicious_package_review import review_sbom

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
REV_A = "sha256:" + "a" * 64


class _RealArtifactRegistrar:
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


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "release_composition.db"
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


class TestComposeReleaseManifest:
    def test_assembles_all_four_real_artifacts_with_correct_parent_edges(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, _instance = authority.declare_release_candidate()
        sbom = generate_sbom(REPO)
        review = review_sbom(sbom)

        with unit_of_work(create_session_factory(engine)) as session:
            registrar = _RealArtifactRegistrar(ArtifactStore(session, blobs))
            provenance = register_release_provenance(candidate, registrar)
            composition = compose_release_manifest(
                registrar, release_id=candidate.release_id,
                core_revision_id=candidate.core_revision_id,
                provenance_artifact_id=provenance.artifact_id, sbom=sbom, review=review,
            )

            assert isinstance(composition, ReleaseManifestComposition)
            store = ArtifactStore(session, blobs)
            parents = store.parents_of(composition.manifest_artifact_id)
            assert set(parents) == {
                composition.provenance_artifact_id,
                composition.sbom_artifact_id,
                composition.review_artifact_id,
            }

    def test_verify_evidence_complete_is_true_for_a_genuine_composition(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, _instance = authority.declare_release_candidate()
        sbom = generate_sbom(REPO)
        review = review_sbom(sbom)

        with unit_of_work(create_session_factory(engine)) as session:
            registrar = _RealArtifactRegistrar(ArtifactStore(session, blobs))
            provenance = register_release_provenance(candidate, registrar)
            composition = compose_release_manifest(
                registrar, release_id=candidate.release_id,
                core_revision_id=candidate.core_revision_id,
                provenance_artifact_id=provenance.artifact_id, sbom=sbom, review=review,
            )
            assert verify_evidence_complete(registrar, composition) is True

    def test_verify_evidence_complete_is_false_after_real_tampering(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        """`evidence_complete` is re-derived, never trusted from a stored
        flag: tampering with one real artifact after composition flips it."""
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, _instance = authority.declare_release_candidate()
        sbom = generate_sbom(REPO)
        review = review_sbom(sbom)

        with unit_of_work(create_session_factory(engine)) as session:
            registrar = _RealArtifactRegistrar(ArtifactStore(session, blobs))
            provenance = register_release_provenance(candidate, registrar)
            composition = compose_release_manifest(
                registrar, release_id=candidate.release_id,
                core_revision_id=candidate.core_revision_id,
                provenance_artifact_id=provenance.artifact_id, sbom=sbom, review=review,
            )
            blobs.path_for(composition.sbom_artifact_id).write_bytes(b"tampered sbom bytes")
            assert verify_evidence_complete(registrar, composition) is False
