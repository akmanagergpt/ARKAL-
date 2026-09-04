"""ACCEPTED candidate -> Managed Product registration composition
(`engineering.factory.product_registration`).

Every test drives real owners over real, isolated persistence -- a real
`CandidateLedger` (JSONL, `tmp_path`), a real `ProjectRegistry` over a real
SQLite file with the real schema, and a real `ArtifactStore` +
`ArtifactBlobStore` over a second real SQLite file and a real filesystem
blob store, all isolated per test via `tmp_path`. Nothing about
`golden-work-129` or any other historical candidate is touched.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.engineering.candidate.ledger import (
    ACCEPTANCE_RUNNING,
    ACCEPTED,
    CandidateLedger,
    GenerationProvenance,
    GENERATING,
    STAGED_GENERATION_PASS,
    STAGE_FAILED,
    hash_text,
)
from arkali.engineering.factory.errors import CandidateNotAcceptedError
from arkali.engineering.factory.product_registration import (
    register_accepted_candidate_as_managed_product,
)
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.content_address import is_address
from arkali.evidence.artifact.store import ArtifactStore
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.session import (
    create_base_schema,
    create_session_factory,
    unit_of_work,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


def _provenance(goal_text: str) -> GenerationProvenance:
    return GenerationProvenance(
        goal_hash=hash_text(goal_text), source_commit="abc123", runtime="ollama",
        endpoint="http://localhost:11434", model="qwen2.5-coder:14b",
        model_parameters={}, pipeline_version="phase-30-staged-generation/1.0.0",
    )


def _write(root: pathlib.Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _accept_candidate(
    ledger: CandidateLedger, candidates_root: pathlib.Path, candidate_id: str, goal_text: str,
) -> None:
    """Real ledger transitions through to a real terminal ACCEPTED entry --
    the exact sequence `run_golden_acceptance.py` drives, never a shortcut
    that skips a state `_TRANSITIONS` would otherwise refuse."""
    work = candidates_root / candidate_id
    work.mkdir(parents=True)
    _write(work, "backend/app.py", "# real candidate content\n")
    ledger.allocate(candidate_id, provenance=_provenance(goal_text))
    ledger.record_state(candidate_id, GENERATING, work)
    ledger.record_state(candidate_id, STAGED_GENERATION_PASS, work)
    ledger.record_state(candidate_id, ACCEPTANCE_RUNNING, work)
    ledger.record_state(
        candidate_id, ACCEPTED, work,
        detail={"outcome": "GOLDEN_ACCEPTANCE_PASS", "result_sha256": "deadbeef"},
    )


@pytest.fixture()
def ledger(tmp_path: pathlib.Path) -> CandidateLedger:
    return CandidateLedger(tmp_path / "ledger")


@pytest.fixture()
def candidates_root(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "candidates"
    root.mkdir()
    return root


@pytest.fixture()
def registry_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(tmp_path / "command_center.db"))
    create_base_schema(built)
    yield built
    built.dispose()


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def artifact_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    from alembic import command
    from alembic.config import Config
    from arkali.kernel.persistence.migrations import ALEMBIC_INI

    db_path = tmp_path / "evidence.db"
    config = Config(str(REPO / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(db_path))
    command.upgrade(config, "head")
    built = create_persistence_engine(sqlite_url(db_path))
    yield built
    built.dispose()


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, pdp: PolicyDecisionPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(
        tmp_path / "blobs", PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"),
    )


def _registration(
    candidate_id: str, ledger: CandidateLedger, registry_engine: Engine,
    artifact_engine: Engine, blobs: ArtifactBlobStore,
):
    with unit_of_work(create_session_factory(registry_engine)) as project_session, \
         unit_of_work(create_session_factory(artifact_engine)) as evidence_session:
        return register_accepted_candidate_as_managed_product(
            candidate_id,
            ledger=ledger,
            registry=ProjectRegistry(project_session),
            artifacts=ArtifactStore(evidence_session, blobs),
        )


class TestAcceptedCandidateRegistersManagedProduct:
    def test_accepted_candidate_registers_a_real_project_and_revision(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        _accept_candidate(ledger, candidates_root, "golden-work-t1", "build a task tracker")
        outcome = _registration("golden-work-t1", ledger, registry_engine, artifact_engine, blobs)

        assert outcome.created is True
        assert outcome.project.project_id.startswith("product-")
        assert outcome.revision.project_id == outcome.project.project_id
        assert outcome.revision.sequence == 1
        assert outcome.revision.provenance_ref == outcome.provenance_ref

    def test_provenance_ref_is_a_real_artifact_store_content_address(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        _accept_candidate(ledger, candidates_root, "golden-work-t2", "build an inventory app")
        outcome = _registration("golden-work-t2", ledger, registry_engine, artifact_engine, blobs)
        assert is_address(outcome.provenance_ref)


class TestNonAcceptedCandidateRefused:
    def test_stage_failed_candidate_is_refused(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        work = candidates_root / "golden-work-fail"
        work.mkdir()
        _write(work, "backend/app.py", "# broken\n")
        ledger.allocate("golden-work-fail", provenance=_provenance("a doomed goal"))
        ledger.record_state("golden-work-fail", GENERATING, work)
        ledger.record_state("golden-work-fail", STAGE_FAILED, work)

        with pytest.raises(CandidateNotAcceptedError):
            _registration("golden-work-fail", ledger, registry_engine, artifact_engine, blobs)

    def test_unknown_candidate_id_is_refused(
        self, ledger, registry_engine, artifact_engine, blobs,
    ) -> None:
        with pytest.raises(CandidateNotAcceptedError):
            _registration("golden-work-never-existed", ledger, registry_engine, artifact_engine, blobs)

    def test_still_in_flight_candidate_is_refused(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        work = candidates_root / "golden-work-inflight"
        work.mkdir()
        _write(work, "backend/app.py", "# mid-generation\n")
        ledger.allocate("golden-work-inflight", provenance=_provenance("a slow goal"))
        ledger.record_state("golden-work-inflight", GENERATING, work)

        with pytest.raises(CandidateNotAcceptedError):
            _registration("golden-work-inflight", ledger, registry_engine, artifact_engine, blobs)


class TestIdempotentConvergence:
    def test_registering_the_same_candidate_twice_yields_one_project(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        _accept_candidate(ledger, candidates_root, "golden-work-t3", "build a library system")
        first = _registration("golden-work-t3", ledger, registry_engine, artifact_engine, blobs)
        second = _registration("golden-work-t3", ledger, registry_engine, artifact_engine, blobs)

        assert first.project.project_id == second.project.project_id
        assert first.revision.revision_id == second.revision.revision_id
        assert first.provenance_ref == second.provenance_ref
        assert first.created is True
        assert second.created is False

        with unit_of_work(create_session_factory(registry_engine)) as session:
            all_projects = ProjectRegistry(session).list_projects()
        matching = [p for p in all_projects if p.project_id == first.project.project_id]
        assert len(matching) == 1

    def test_a_prior_failed_candidate_for_the_same_goal_does_not_create_a_second_product(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        """Test 4: a prior, real STAGE_FAILED attempt at the identical goal
        text is never registered (refused, per TestNonAcceptedCandidateRefused);
        only the later real ACCEPTED candidate for the SAME goal_hash is ever
        registered, converging to exactly one Managed Product."""
        goal_text = "build a payroll system"
        failed_work = candidates_root / "golden-work-attempt-1"
        failed_work.mkdir()
        _write(failed_work, "backend/app.py", "# first attempt, broken\n")
        ledger.allocate("golden-work-attempt-1", provenance=_provenance(goal_text))
        ledger.record_state("golden-work-attempt-1", GENERATING, failed_work)
        ledger.record_state("golden-work-attempt-1", STAGE_FAILED, failed_work)

        _accept_candidate(ledger, candidates_root, "golden-work-attempt-2", goal_text)
        outcome = _registration(
            "golden-work-attempt-2", ledger, registry_engine, artifact_engine, blobs,
        )

        with unit_of_work(create_session_factory(registry_engine)) as session:
            all_projects = ProjectRegistry(session).list_projects()
        assert len(all_projects) == 1
        assert all_projects[0].project_id == outcome.project.project_id


class TestCandidateLedgerUntouched:
    def test_candidate_ledger_history_is_unchanged_by_registration(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        _accept_candidate(ledger, candidates_root, "golden-work-t4", "build a CRM")
        before = ledger.history("golden-work-t4")
        _registration("golden-work-t4", ledger, registry_engine, artifact_engine, blobs)
        after = ledger.history("golden-work-t4")
        assert before == after
        assert str(after[-1]["state"]) == ACCEPTED


class TestNoDuplicateTruth:
    def test_provenance_artifact_references_candidate_without_copying_the_manifest(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        """Decision 7: reference the accepted candidate, never duplicate its
        full recorded manifest (a file-by-file hash dict) inside the
        provenance artifact."""
        _accept_candidate(ledger, candidates_root, "golden-work-t5", "build a helpdesk")
        outcome = _registration("golden-work-t5", ledger, registry_engine, artifact_engine, blobs)

        with unit_of_work(create_session_factory(artifact_engine)) as session:
            payload = json.loads(ArtifactStore(session, blobs).content_of(outcome.provenance_ref))
        assert payload["candidate_id"] == "golden-work-t5"
        assert "goal_hash" in payload
        assert "manifest" not in payload
        assert "history" not in payload

    def test_project_id_is_not_the_raw_candidate_id(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        """Decision 3/7: candidate identity must never become product identity."""
        _accept_candidate(ledger, candidates_root, "golden-work-t6", "build a wiki")
        outcome = _registration("golden-work-t6", ledger, registry_engine, artifact_engine, blobs)
        assert outcome.project.project_id != "golden-work-t6"
        assert "golden-work-t6" not in outcome.project.project_id
        assert "golden-work-t6" not in outcome.revision.revision_id


class TestGoalAnchoredIdentity:
    def test_same_goal_text_always_derives_the_same_project_id(
        self, ledger, candidates_root, registry_engine, artifact_engine, blobs,
    ) -> None:
        """The goal identity this composition anchors to is deterministic
        and content-derived (`GenerationProvenance.goal_hash`), the same
        value `RequirementBlueprint.goal.goal_id` computes for identical
        goal_text via the identical `content_address.address_of` primitive
        -- proven here without importing `control.specification` (would add
        a fourth touched context to this test module unnecessarily) by
        reproducing the same computation directly."""
        from arkali.evidence.artifact.content_address import address_of

        goal_text = "build a real-time chat app"
        assert hash_text(goal_text) == address_of(goal_text.encode("utf-8"))

        _accept_candidate(ledger, candidates_root, "golden-work-t7", goal_text)
        outcome = _registration("golden-work-t7", ledger, registry_engine, artifact_engine, blobs)
        assert outcome.project.project_id == f"product-{hash_text(goal_text).split(':', 1)[1][:32]}"
