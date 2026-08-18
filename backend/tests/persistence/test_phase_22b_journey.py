"""Phase 22B composed journey: the real VDC "Recovery Supervisor" sequence.

VDC section "Recovery Supervisor": "Bad ARKALI upgrade candidate -> launch ->
health failure -> known-good rollback -> failure record -> stable available."
Every step below is a real call against real SQLite (via the real Alembic
chain), the real PDP, the real Stable-revision pointer, and the real C-14/C-15
evidence plane - matching this build's own established discipline for a
composed real-authority journey (`test_phase_20_journey.py`,
`test_phase_21_...` equivalents).
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
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore
from arkali.evidence.audit.chain import AuditChain
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.recovery.recovery_supervisor import (
    HealthCheckResult,
    RecoverySupervisor,
)
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import (
    StablePointerError,
    StableRevisionPointer,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
ARKALI_SOURCE = BACKEND / "arkali"

REV_GOOD = "sha256:" + "1" * 64
REV_BAD = "sha256:" + "2" * 64


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "journey.db"
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
def pointer_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "stable_pointer.json"


@pytest.fixture()
def pointer(
    path: StableCandidatePath, pointer_path: pathlib.Path
) -> StableRevisionPointer:
    return StableRevisionPointer(path, pointer_path)


def _promotion_receipt(path: StableCandidatePath, candidate_id: str) -> StageReceipt:
    receipt = path.begin_candidate(candidate_id=candidate_id)
    for stage in path.stages()[2:-1]:
        receipt = path.advance(receipt, to_stage=stage)
    return path.promotion_receipt(receipt)


class TestTheComposedVDCSequence:
    """Bad candidate -> launch -> health failure -> known-good rollback ->
    failure record -> stable available, end to end."""

    def test_the_whole_sequence_leaves_a_known_good_stable_and_a_failure_record(
        self, path: StableCandidatePath, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        # A good revision reaches Stable through the real canonical path.
        pointer.promote(
            _promotion_receipt(path, "good-candidate"),
            revision_id=REV_GOOD, candidate_id="good-candidate",
        )
        # A bad upgrade candidate is promoted on top of it (this is the
        # "launch" - a new revision genuinely reached Stable and is now live).
        pointer.promote(
            _promotion_receipt(path, "bad-candidate"),
            revision_id=REV_BAD, candidate_id="bad-candidate",
        )
        assert pointer.current().revision_id == REV_BAD  # type: ignore[union-attr]

        # Health failure is detected (supplied, not invented by this module).
        health = HealthCheckResult(
            candidate_id="bad-candidate", healthy=False,
            detail="post-launch smoke test failed: /health returned 500",
        )

        with unit_of_work(create_session_factory(engine)) as session:
            supervisor = RecoverySupervisor(
                pep, pointer, ArtifactStore(session, blobs), AuditChain(session, pep, REPO)
            )
            # Known-good rollback + failure record, in one evidenced call.
            record = supervisor.rollback(health=health, target_revision_id=REV_GOOD)

        # Stable is available again, at the known-good revision.
        assert pointer.current().revision_id == REV_GOOD  # type: ignore[union-attr]
        assert record.to_revision_id == REV_GOOD
        assert record.from_revision_id == REV_BAD
        assert "post-launch smoke test failed" in record.reason
        assert len(record.evidence_record_hashes) == 3

        with unit_of_work(create_session_factory(engine)) as verify_session:
            audit = AuditChain(verify_session, pep, REPO)
            assert audit.verify().verified
            assert {r.requirement_id for r in audit.records()} == {
                "ARK-REQ-0160", "ARK-REQ-0338", "ARK-REQ-0339",
            }


class TestIdempotentRetry:
    def test_repeating_a_successful_rollback_stays_safe_and_keeps_evidencing(
        self, path: StableCandidatePath, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_GOOD, candidate_id="cand-1"
        )
        health = HealthCheckResult(
            candidate_id="cand-1", healthy=False, detail="crash on start"
        )
        for _ in range(2):
            with unit_of_work(create_session_factory(engine)) as session:
                supervisor = RecoverySupervisor(
                    pep, pointer, ArtifactStore(session, blobs),
                    AuditChain(session, pep, REPO),
                )
                record = supervisor.rollback(health=health, target_revision_id=REV_GOOD)
                assert record.to_revision_id == REV_GOOD
        assert pointer.current().revision_id == REV_GOOD  # type: ignore[union-attr]
        assert pointer.history() == (), "rolling back to the current revision is a no-op"


class TestCrashDuringSwitchLeavesNoPartialState:
    def test_a_stray_temp_file_from_an_interrupted_write_never_leaks_into_current(
        self, path: StableCandidatePath, pointer_path: pathlib.Path,
    ) -> None:
        """Simulates a process death between the temp-file write and the
        `os.replace` swap: a stray temp file must never be mistaken for the
        durable pointer state."""
        pointer = StableRevisionPointer(path, pointer_path)
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_GOOD, candidate_id="cand-1"
        )
        stray = pointer_path.parent / ".stable_pointer_leftover.tmp"
        stray.write_text('{"pointer_version": "1.0.0", "current": null, "history": []}')

        reopened = StableRevisionPointer(path, pointer_path)
        assert reopened.current().revision_id == REV_GOOD  # type: ignore[union-attr]
        assert stray.is_file(), "the stray file itself is untouched, merely ignored"


class TestNoNovelContentNoAIInvocation:
    """ARK-REQ-0159: no novel content, no transformation, no direct AI call."""

    @pytest.mark.parametrize(
        "module", ["recovery_supervisor.py"],
    )
    def test_recovery_supervisor_imports_no_engineering_or_ai_context(
        self, module: str
    ) -> None:
        text = (ARKALI_SOURCE / "lifecycle" / "recovery" / module).read_text(
            encoding="utf-8"
        )
        for forbidden in ("arkali.engineering", "openai", "anthropic", "ollama"):
            assert forbidden not in text, (
                f"{module} must never import an AI or candidate-generation "
                f"authority; found {forbidden!r}"
            )

    def test_stable_pointer_imports_no_engineering_or_ai_context(self) -> None:
        text = (ARKALI_SOURCE / "lifecycle" / "release" / "stable_pointer.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("arkali.engineering", "openai", "anthropic", "ollama"):
            assert forbidden not in text

    def test_rollback_is_an_identity_switch_never_a_content_rewrite(
        self, path: StableCandidatePath, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        """The registered rollback artifact itself states the transformation
        performed: none. Asserted against the real, persisted artifact bytes,
        not merely claimed in prose."""
        import json as jsonlib

        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_GOOD, candidate_id="cand-1"
        )
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)
            supervisor = RecoverySupervisor(
                pep, pointer, artifacts, AuditChain(session, pep, REPO)
            )
            record = supervisor.rollback(
                health=HealthCheckResult(
                    candidate_id="cand-1", healthy=False, detail="crash"
                ),
                target_revision_id=REV_GOOD,
            )
            evidence_records = AuditChain(session, pep, REPO).records()
            artifact_id = evidence_records[0].artifact_id
            payload = jsonlib.loads(artifacts.content_of(artifact_id))

        assert record.to_revision_id == REV_GOOD
        assert payload["transformation"] == "none - atomic identity pointer switch only"


class TestSeparationOfRollbackAndAcceptanceAuthority:
    def test_recovery_supervisor_never_imports_acceptance_engine(self) -> None:
        text = (
            ARKALI_SOURCE / "lifecycle" / "recovery" / "recovery_supervisor.py"
        ).read_text(encoding="utf-8")
        assert "arkali.acceptance" not in text, (
            "rollback authority must stay structurally separate from "
            "acceptance/verdict authority"
        )


class TestWrongCandidateAndCorruptedTargetRefusal:
    def test_rollback_to_a_target_belonging_to_no_promotion_is_pdp_denied(
        self, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
    ) -> None:
        with pytest.raises(PolicyDenied):
            with unit_of_work(create_session_factory(engine)) as session:
                RecoverySupervisor(
                    pep, pointer, ArtifactStore(session, blobs),
                    AuditChain(session, pep, REPO),
                ).rollback(
                    health=HealthCheckResult(
                        candidate_id="cand-x", healthy=False, detail="crash"
                    ),
                    target_revision_id=REV_BAD,
                )

    def test_the_pointer_itself_refuses_a_direct_rollback_to_an_unrecorded_id(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        """Defence in depth: even bypassing the Recovery Supervisor and the
        PDP entirely, the pointer's own mechanic refuses the same target."""
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_GOOD, candidate_id="cand-1"
        )
        with pytest.raises(StablePointerError):
            pointer.rollback_to(REV_BAD)
