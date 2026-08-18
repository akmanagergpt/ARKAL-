"""Recovery Supervisor on real persistence, real PDP, real evidence plane.

Real SQLite migrated by the real Alembic chain, a real PDP from the authority
map, a real C-14 artifact store, a real C-15 audit chain, and a real
Stable-revision pointer - nothing is substituted (matching
`tests/evidence/test_audit_chain.py`'s own discipline for this exact
composition).
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from arkali.control.policy.pdp import PolicyAuthority, PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore
from arkali.evidence.audit.chain import AuditChain
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.recovery.recovery_supervisor import (
    ACTOR,
    TRUST_TIER,
    HealthCheckResult,
    RecoverySupervisor,
    RecoverySupervisorError,
)
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer
from tests.persistence.conftest import AuditChainEvidenceSink, PepRollbackAuthorization

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

REV_A = "sha256:" + "a" * 64
REV_B = "sha256:" + "b" * 64


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "recovery.db"
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
    return PolicyEnforcementPoint(pdp, "lifecycle.recovery.recovery_supervisor")


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


def _supervisor(
    session: object, pep: PolicyEnforcementPoint,
    pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
) -> RecoverySupervisor:
    return RecoverySupervisor(
        PepRollbackAuthorization(pep, actor=ACTOR, trust_tier=TRUST_TIER),
        pointer, ArtifactStore(session, blobs),  # type: ignore[arg-type]
        AuditChainEvidenceSink(AuditChain(session, pep, REPO)),  # type: ignore[arg-type]
    )


class TestHealthyCandidateRefusal:
    def test_rollback_is_refused_for_a_reported_healthy_candidate(
        self, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            supervisor = _supervisor(session, pep, pointer, blobs)
            with pytest.raises(RecoverySupervisorError):
                supervisor.rollback(
                    health=HealthCheckResult(
                        candidate_id="cand-2", healthy=True, detail="all green"
                    ),
                    target_revision_id=REV_A,
                )


class TestUnverifiedTargetRefusal:
    def test_rollback_is_denied_by_the_real_pdp_for_an_unrecorded_target(
        self, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        """No promotion has happened; the pointer's history is empty, so the
        PDP itself (not a convention) refuses this rollback."""
        with pytest.raises(PolicyDenied):
            with unit_of_work(create_session_factory(engine)) as session:
                supervisor = _supervisor(session, pep, pointer, blobs)
                supervisor.rollback(
                    health=HealthCheckResult(
                        candidate_id="cand-2", healthy=False, detail="startup crash"
                    ),
                    target_revision_id=REV_A,
                )
        assert pointer.current() is None, "a denied rollback must mutate nothing"


class TestGenuineRollback:
    def test_a_genuine_rollback_switches_the_pointer_and_emits_evidence(
        self, path: StableCandidatePath, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        pointer.promote(
            _promotion_receipt(path, "cand-2"), revision_id=REV_B, candidate_id="cand-2"
        )
        with unit_of_work(create_session_factory(engine)) as session:
            supervisor = _supervisor(session, pep, pointer, blobs)
            record = supervisor.rollback(
                health=HealthCheckResult(
                    candidate_id="cand-2", healthy=False, detail="startup crash"
                ),
                target_revision_id=REV_A,
            )

        assert record.from_revision_id == REV_B
        assert record.to_revision_id == REV_A
        assert len(record.evidence_record_hashes) == 3
        assert pointer.current().revision_id == REV_A  # type: ignore[union-attr]

    def test_evidence_is_really_persisted_and_chain_intact(
        self, path: StableCandidatePath, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        with unit_of_work(create_session_factory(engine)) as session:
            supervisor = _supervisor(session, pep, pointer, blobs)
            supervisor.rollback(
                health=HealthCheckResult(
                    candidate_id="cand-1", healthy=False, detail="crash loop"
                ),
                target_revision_id=REV_A,
            )

        with unit_of_work(create_session_factory(engine)) as verify_session:
            audit = AuditChain(verify_session, pep, REPO)
            records = audit.records()
            assert len(records) == 3
            assert {r.requirement_id for r in records} == {
                "ARK-REQ-0160", "ARK-REQ-0338", "ARK-REQ-0339",
            }
            assert audit.verify().verified

    def test_is_verified_is_false_before_any_rollback_and_true_after(
        self, path: StableCandidatePath, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        with unit_of_work(create_session_factory(engine)) as session:
            supervisor = _supervisor(session, pep, pointer, blobs)
            assert supervisor.is_verified() is False
            supervisor.rollback(
                health=HealthCheckResult(
                    candidate_id="cand-1", healthy=False, detail="crash loop"
                ),
                target_revision_id=REV_A,
            )
            assert supervisor.is_verified() is True

    def test_rollback_to_an_unrecorded_target_stays_denied_on_retry(
        self, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        """Idempotent retry safety: retrying a denied rollback stays denied."""
        for _ in range(2):
            with pytest.raises(PolicyDenied):
                with unit_of_work(create_session_factory(engine)) as session:
                    supervisor = _supervisor(session, pep, pointer, blobs)
                    supervisor.rollback(
                        health=HealthCheckResult(
                            candidate_id="cand-x", healthy=False, detail="crash"
                        ),
                        target_revision_id=REV_B,
                    )


class TestInvokerIdentity:
    def test_the_supervisors_actor_matches_the_canonical_rollback_invoker(self) -> None:
        assert ACTOR == PolicyAuthority.load(REPO).rollback_invoker
