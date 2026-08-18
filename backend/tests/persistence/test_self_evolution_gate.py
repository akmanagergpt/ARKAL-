"""Self-Evolution DENY-until-verified precondition (ARK-REQ-0135, ARK-REQ-0136).

`core_upgrade_state_machine.py`'s `recovery_supervisor_guard` has read the
`recovery_supervisor_verified` context key since Phase 3 - the machine's own
docstring already says entry "requires a verified Recovery Supervisor (Phase
22B) or the PDP returns DENY". What Phase 22B closes is the other half:
proving that key is never satisfiable by convention. Every case here drives
the real guard with the real, freshly-derived
`RecoverySupervisor.is_verified()` value - never a bare `True` a caller could
assert - on the same real SQLite/PDP/evidence composition
`test_recovery_supervisor.py` already establishes.
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
from arkali.evidence.audit.chain import AuditChain
from arkali.kernel.contracts.state_machine_errors import GuardRejected
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.evolution.core_upgrade_state_machine import build as build_core_upgrade
from arkali.lifecycle.recovery.recovery_supervisor import (
    ACTOR,
    TRUST_TIER,
    HealthCheckResult,
    RecoverySupervisor,
)
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer
from tests.persistence.conftest import AuditChainEvidenceSink, PepRollbackAuthorization

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
ARKALI_SOURCE = BACKEND / "arkali"
REV_A = "sha256:" + "a" * 64


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "gate.db"
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


class TestEntryDeniedBeforeVerification:
    def test_core_upgrade_entry_is_refused_before_any_real_rollback(
        self, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            supervisor = _supervisor(session, pep, pointer, blobs)
            assert supervisor.is_verified() is False

            machine = build_core_upgrade()
            instance = machine.start("SNAPSHOT_TAKEN")
            with pytest.raises(GuardRejected):
                instance.apply(
                    "CANDIDATE_BUILT",
                    {"recovery_supervisor_verified": supervisor.is_verified()},
                )


class TestEntryPermittedAfterVerification:
    def test_core_upgrade_entry_is_permitted_once_a_real_rollback_is_evidenced(
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
            assert supervisor.is_verified() is True

            machine = build_core_upgrade()
            instance = machine.start("SNAPSHOT_TAKEN")
            instance.apply(
                "CANDIDATE_BUILT",
                {"recovery_supervisor_verified": supervisor.is_verified()},
            )
            assert instance.state == "CANDIDATE_BUILT"

    def test_a_freshly_reopened_supervisor_over_the_same_evidence_agrees(
        self, path: StableCandidatePath, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        """`is_verified` is re-derived from durable evidence, not per-instance
        state: a brand-new RecoverySupervisor object over the same database
        sees the same fact a prior instance produced."""
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        with unit_of_work(create_session_factory(engine)) as session:
            _supervisor(session, pep, pointer, blobs).rollback(
                health=HealthCheckResult(
                    candidate_id="cand-1", healthy=False, detail="crash loop"
                ),
                target_revision_id=REV_A,
            )

        with unit_of_work(create_session_factory(engine)) as reopened_session:
            reopened = _supervisor(reopened_session, pep, pointer, blobs)
            assert reopened.is_verified() is True


class TestNotEnforceableByConvention:
    def test_only_recovery_supervisor_can_ever_emit_the_verification_requirement(
        self,
    ) -> None:
        """ARK-REQ-0136: the fact is PDP-derived, not conventionally asserted.

        `is_verified()` trusts nothing but a real `ARK-REQ-0338` PASS row in
        the evidence chain, and that row can only ever be produced by a
        genuine `RecoverySupervisor.rollback()` call, which itself cannot
        succeed without a real PDP AUTO grant (Package 2). This structurally
        proves no other shipped module can manufacture the fact: if it could,
        it would have to name the requirement id to do it, and this is the
        one production file that does.
        """
        producers = []
        for candidate in ARKALI_SOURCE.rglob("*.py"):
            text = candidate.read_text(encoding="utf-8")
            if "ARK-REQ-0338" in text:
                producers.append(candidate.relative_to(REPO).as_posix())
        assert producers == [
            "backend/arkali/lifecycle/recovery/recovery_supervisor.py"
        ], (
            "ARK-REQ-0338 evidence must be producible from exactly one "
            f"production module; found {producers}"
        )
