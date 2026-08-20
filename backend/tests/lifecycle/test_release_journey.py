"""Phase 26 composed VDC journey: C-31 Release / Supply Chain / Deployment,
end to end against real infrastructure - a real SQLite database, a real
C-14 artifact store, the real unmodified `Release` state machine, and the
real `HUMAN_GATE_7` singleton mechanism. No test double stands in for any
of them.
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from arkali.acceptance.governance_state import GovernanceState
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.contracts.state_machine import GuardRejected
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.release import release_state_machine as rsm
from arkali.lifecycle.release.release_composition import (
    compose_release_manifest,
    verify_evidence_complete,
)
from arkali.lifecycle.release.release_gate import GATE_7, authorize_release
from arkali.lifecycle.release.release_manifest import ReleaseAuthority
from arkali.lifecycle.release.release_provenance import ProvenanceFields, register_release_provenance
from arkali.lifecycle.release.sbom import generate_sbom
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer
from arkali.lifecycle.release.suspicious_package_review import review_sbom

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
RECORDS = "docs/acceptance/HUMAN_GATE_RECORDS.md"
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
    path = tmp_path / "release_journey.db"
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


class TestComposedReleaseJourney:
    def test_the_full_journey_from_core_promotion_to_a_real_gate_refusal(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        # 1. A real Stable Core revision exists (Phase 22B's own, unmodified
        #    pointer) - nothing to release before this.
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )

        # 2. Declare a real release candidate over it (Package 1).
        authority = ReleaseAuthority(pointer)
        candidate, instance = authority.declare_release_candidate()
        assert instance.state == "DRAFT"
        authority.assert_still_stable(candidate)

        with unit_of_work(create_session_factory(engine)) as session:
            registrar = _RealArtifactRegistrar(ArtifactStore(session, blobs))

            # 3. Real provenance (Package 2).
            provenance = register_release_provenance(candidate, registrar)

            # 4. Real, deterministic SBOM over this repository's own real
            #    manifests, and a real suspicious-package review over it
            #    (Packages 3-4) - genuinely clean on this real repository.
            sbom = generate_sbom(REPO)
            review = review_sbom(sbom)
            assert review.clean is True

            # 5. Final composition: SBOM/review registered as real
            #    artifacts, the manifest artifact citing all three as real
            #    parents (Package 6).
            composition = compose_release_manifest(
                registrar, release_id=candidate.release_id,
                core_revision_id=candidate.core_revision_id,
                provenance_artifact_id=provenance.artifact_id, sbom=sbom, review=review,
            )
            assert verify_evidence_complete(registrar, composition) is True

            # 6. Advance the real, unmodified Release machine through every
            #    intermediate stage - never skippable (Package 5's own
            #    structural proof, exercised here for real).
            for target in ("BUILT", "VERIFIED", "SIGNED_READY"):
                instance.apply(target)
            assert instance.state == "SIGNED_READY"

            # 7. Without a real HUMAN_GATE_7 grant, RELEASED is genuinely
            #    refused - not merely asserted refused (Package 6).
            state = GovernanceState.load(REPO)
            assert GATE_7 not in state.accepted_human_gates
            context = authorize_release(state, registrar, composition)
            assert context == {"human_gate_7_recorded": False, "evidence_complete": True}
            with pytest.raises(GuardRejected):
                instance.apply("RELEASED", context)

    def test_released_is_reachable_once_a_genuine_gate_7_grant_exists(
        self, path: StableCandidatePath, engine: Engine,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore, tmp_path: pathlib.Path,
    ) -> None:
        """A real, temporary HUMAN_GATE_RECORDS.md granting Gate 7 - the
        singleton mechanism proven in `test_release_gate.py` - genuinely
        unblocks the real, unmodified guard. No accepted repository state
        is touched; this never runs against the live docs/ tree."""
        pointer.promote(
            _promotion_receipt(path, "core-1"), revision_id=REV_A, candidate_id="core-1"
        )
        authority = ReleaseAuthority(pointer)
        candidate, instance = authority.declare_release_candidate()

        with unit_of_work(create_session_factory(engine)) as session:
            registrar = _RealArtifactRegistrar(ArtifactStore(session, blobs))
            provenance = register_release_provenance(candidate, registrar)
            sbom = generate_sbom(REPO)
            review = review_sbom(sbom)
            composition = compose_release_manifest(
                registrar, release_id=candidate.release_id,
                core_revision_id=candidate.core_revision_id,
                provenance_artifact_id=provenance.artifact_id, sbom=sbom, review=review,
            )
            for target in ("BUILT", "VERIFIED", "SIGNED_READY"):
                instance.apply(target)

            granted_repo = tmp_path / "granted_repo"
            shutil.copytree(REPO / "docs", granted_repo / "docs")
            (granted_repo / RECORDS).write_text(
                "# HUMAN GATE RECORDS\n\n"
                "## HGR-999 — HUMAN GATE 7: Final Production Release\n\n"
                "| Field | Value |\n|---|---|\n"
                "| **Decision** | **ACCEPTED** |\n",
                encoding="utf-8",
            )
            granted_state = GovernanceState.load(granted_repo)
            assert GATE_7 in granted_state.accepted_human_gates
            context = authorize_release(granted_state, registrar, composition)
            assert context == {"human_gate_7_recorded": True, "evidence_complete": True}

            outcome = instance.apply("RELEASED", context)
            assert instance.state == "RELEASED"
            assert instance.is_terminal is True
            assert outcome.machine == rsm.DEFINITION.machine == "Release"
