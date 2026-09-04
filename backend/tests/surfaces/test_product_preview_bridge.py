"""Managed Product -> real preview bridge (D-029's own follow-on).

Two halves: direct unit coverage of the resolver
(`product_preview_resolution.py`) and the re-runnable submission helpers
(`jobs.py`'s `_submit_or_recover_preview`/`_find_current_preview`), plus a
real, end-to-end `TestClient` proof that `POST`/`GET /api/projects/
{project_id}/preview` genuinely reach the same durable job a candidate-
direct preview would, resolved through the real `ProjectRegistry` ->
`provenance_ref` -> `ArtifactStore` -> `CandidateLedger` chain -- no mock
of any of the three real authorities involved.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.execution.durable.job_store import JobStore
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import (
    create_base_schema,
    create_session_factory,
    unit_of_work,
)
from arkali.surfaces.command.app import _CommandExtensions, create_app
from arkali.surfaces.command.jobs import (
    _find_current_preview,
    _preview_scope_key,
    _PREVIEW_JOB_TYPE,
    _submit_or_recover_preview,
)
from arkali.surfaces.command.product_preview_resolution import (
    _MANAGED_PRODUCT_PROVENANCE_SPEC,
    _NoRevisionForProjectError,
    _PreviewBridgeWiring,
    _ProvenanceNotManagedProductError,
    _ReferencedCandidateNotEligibleError,
    _RevisionHasNoProvenanceError,
    _resolve_candidate_for_project,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"


def _alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "test.readback")


# ---------------------------------------------------------------------------
# Part 1: the re-runnable preview submission helpers, against a real JobStore
# ---------------------------------------------------------------------------


@pytest.fixture()
def job_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    path = tmp_path / "jobs.db"
    command.upgrade(_alembic_config(path), "head")
    built = create_persistence_engine(sqlite_url(path))
    yield built
    built.dispose()


@pytest.fixture()
def job_store(job_engine: Engine, pep: PolicyEnforcementPoint) -> Iterator[JobStore]:
    with unit_of_work(create_session_factory(job_engine)) as session:
        yield JobStore(session, pep)


class TestPreviewScopeKey:
    def test_attempt_one_is_the_bare_candidate_id_unchanged(self) -> None:
        """Byte-for-byte the original, already-shipped identity — an
        already-open or already-terminal FIRST preview is unaffected."""
        assert _preview_scope_key("golden-work-1", 1) == "golden-work-1"

    def test_attempt_two_and_beyond_are_suffixed(self) -> None:
        assert _preview_scope_key("golden-work-1", 2) == "golden-work-1#2"
        assert _preview_scope_key("golden-work-1", 3) == "golden-work-1#3"


class TestSubmitOrRecoverPreview:
    def test_the_first_open_creates_a_real_job_at_attempt_one(self, job_store: JobStore) -> None:
        record = _submit_or_recover_preview(job_store, "golden-work-t1")
        assert record.idempotency_key == "golden-work-t1"
        assert record.job_id == "preview-golden-work-t1"

    def test_double_open_while_active_returns_the_same_job(self, job_store: JobStore) -> None:
        """Part I: double-click must never create two active runtimes."""
        first = _submit_or_recover_preview(job_store, "golden-work-t2")
        second = _submit_or_recover_preview(job_store, "golden-work-t2")
        assert first.job_id == second.job_id
        assert first.idempotency_key == second.idempotency_key

    def test_reopen_after_a_real_terminal_cancel_mints_a_new_job(self, job_store: JobStore) -> None:
        """The exact previously-verified limitation, now fixed: CANCELLED no
        longer masquerades as reusable."""
        first = _submit_or_recover_preview(job_store, "golden-work-t3")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "CANCELLED")

        second = _submit_or_recover_preview(job_store, "golden-work-t3")
        assert second.job_id != first.job_id
        assert second.idempotency_key == "golden-work-t3#2"
        assert second.lifecycle_state == "QUEUED"

    def test_a_second_reopen_after_another_terminal_cycle_mints_a_third(
        self, job_store: JobStore,
    ) -> None:
        first = _submit_or_recover_preview(job_store, "golden-work-t4")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "CANCELLED")
        second = _submit_or_recover_preview(job_store, "golden-work-t4")
        job_store.transition(second.job_id, "RUNNING")
        job_store.transition(second.job_id, "CANCELLED")
        third = _submit_or_recover_preview(job_store, "golden-work-t4")

        assert third.idempotency_key == "golden-work-t4#3"
        assert len({first.job_id, second.job_id, third.job_id}) == 3

    def test_a_recoverable_job_is_rediscovered_not_replaced(self, job_store: JobStore) -> None:
        """RECOVERABLE is not in the Job machine's own declared `terminal`
        set — a later real recovery could still move it forward, so minting
        a fresh identity underneath it would orphan that path."""
        first = _submit_or_recover_preview(job_store, "golden-work-t5")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "FAILED")
        job_store.transition(first.job_id, "RECOVERABLE")

        again = _submit_or_recover_preview(job_store, "golden-work-t5")
        assert again.job_id == first.job_id


class TestFindCurrentPreview:
    def test_nothing_submitted_yet_is_none(self, job_store: JobStore) -> None:
        assert _find_current_preview(job_store, "golden-work-never-opened") is None

    def test_finds_the_active_job_not_an_old_terminal_one(self, job_store: JobStore) -> None:
        first = _submit_or_recover_preview(job_store, "golden-work-t6")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "CANCELLED")
        second = _submit_or_recover_preview(job_store, "golden-work-t6")

        found = _find_current_preview(job_store, "golden-work-t6")
        assert found is not None
        assert found.job_id == second.job_id
        assert found.lifecycle_state == "QUEUED"

    def test_refresh_while_active_rediscovers_the_same_job(self, job_store: JobStore) -> None:
        active = _submit_or_recover_preview(job_store, "golden-work-t7")
        found = _find_current_preview(job_store, "golden-work-t7")
        assert found is not None
        assert found.job_id == active.job_id

    def test_after_a_terminal_cycle_the_terminal_job_is_still_found_honestly(
        self, job_store: JobStore,
    ) -> None:
        """No newer cycle exists yet: the terminal one is the honest truth,
        never hidden and never pretended active (the caller reads
        `lifecycle_state` itself to know which)."""
        first = _submit_or_recover_preview(job_store, "golden-work-t8")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "CANCELLED")
        found = _find_current_preview(job_store, "golden-work-t8")
        assert found is not None
        assert found.job_id == first.job_id
        assert found.lifecycle_state == "CANCELLED"


# ---------------------------------------------------------------------------
# Part 2: the Managed Product -> candidate resolver, against real
# ProjectRegistry + ArtifactStore, and a fake structural CandidateLedger
# ---------------------------------------------------------------------------


class _FakeLedger:
    """Structural `_CandidateLedgerSource` double -- a plain in-memory
    stand-in for the real `CandidateLedger`, matching only its public
    `history` shape. Never used to prove the real ledger's own behaviour
    (that is `test_candidate_ledger.py`'s job); used only to control what
    this resolver observes when eligibility is or is not present."""

    def __init__(self, states: dict[str, list[dict[str, object]]]) -> None:
        self._states = states

    def history(self, candidate_id: str) -> tuple[dict[str, object], ...]:
        return tuple(self._states.get(candidate_id, ()))


@pytest.fixture()
def registry_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(tmp_path / "command_center.db"))
    create_base_schema(built)
    yield built
    built.dispose()


@pytest.fixture()
def artifact_engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    path = tmp_path / "evidence.db"
    command.upgrade(_alembic_config(path), "head")
    built = create_persistence_engine(sqlite_url(path))
    yield built
    built.dispose()


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, pep: PolicyEnforcementPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(tmp_path / "blobs", pep)


def _register_managed_product_artifact(
    artifact_session: Session, blobs: ArtifactBlobStore, *, candidate_id: str,
) -> str:
    payload = json.dumps(
        {"schema": _MANAGED_PRODUCT_PROVENANCE_SPEC, "goal_hash": "sha256:" + "a" * 64,
         "candidate_id": candidate_id, "accepted_at": "2026-01-01T00:00:00Z",
         "acceptance_detail": {}},
        sort_keys=True,
    ).encode("utf-8")
    return ArtifactStore(artifact_session, blobs).register(
        payload,
        ProvenanceInput(
            producer_agent="engineering.factory", provider_model="n/a", task_id=candidate_id,
            specification_version=_MANAGED_PRODUCT_PROVENANCE_SPEC, context_hash="sha256:" + "a" * 64,
        ),
    )


def _register_unrelated_artifact(artifact_session: Session, blobs: ArtifactBlobStore) -> str:
    payload = b'{"unrelated": true}'
    return ArtifactStore(artifact_session, blobs).register(
        payload,
        ProvenanceInput(
            producer_agent="some.other.producer", provider_model="n/a", task_id="not-a-candidate",
            specification_version="something-else/1.0.0", context_hash="sha256:" + "b" * 64,
        ),
    )


def _accepted_ledger(candidate_id: str) -> _FakeLedger:
    return _FakeLedger({candidate_id: [
        {"candidate_id": candidate_id, "state": "ALLOCATED", "goal_hash": "sha256:" + "a" * 64},
        {"candidate_id": candidate_id, "state": "ACCEPTED"},
    ]})


class TestResolveCandidateForProject:
    def test_unknown_project_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        from arkali.control.registry.project.errors import UnknownProject

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-x"),
            )
            with pytest.raises(UnknownProject):
                _resolve_candidate_for_project(
                    "no-such-project", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_project_with_no_revision_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-norev", "No Revision Yet")
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-x"),
            )
            with pytest.raises(_NoRevisionForProjectError):
                _resolve_candidate_for_project(
                    "prj-norev", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_project_with_more_than_one_revision_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        """No canonical current-revision pointer exists — never silently
        guessed."""
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-multirev", "Two Revisions")
            registry.create_revision("prj-multirev", "prj-multirev-r1")
            registry.create_revision("prj-multirev", "prj-multirev-r2")
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-x"),
            )
            with pytest.raises(_NoRevisionForProjectError):
                _resolve_candidate_for_project(
                    "prj-multirev", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_revision_without_provenance_ref_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-noprov", "No Provenance")
            registry.create_revision("prj-noprov", "prj-noprov-r1", provenance_ref=None)
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-x"),
            )
            with pytest.raises(_RevisionHasNoProvenanceError):
                _resolve_candidate_for_project(
                    "prj-noprov", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_malformed_provenance_ref_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        from arkali.evidence.artifact.errors import InvalidArtifactIdentity

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-badref", "Bad Reference")
            registry.create_revision(
                "prj-badref", "prj-badref-r1", provenance_ref="not-a-real-address",
            )
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-x"),
            )
            with pytest.raises(InvalidArtifactIdentity):
                _resolve_candidate_for_project(
                    "prj-badref", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_missing_provenance_artifact_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        from arkali.evidence.artifact.content_address import address_of
        from arkali.evidence.artifact.errors import UnknownArtifact

        never_registered = address_of(b"never actually registered")
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-missing", "Missing Artifact")
            registry.create_revision(
                "prj-missing", "prj-missing-r1", provenance_ref=never_registered,
            )
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-x"),
            )
            with pytest.raises(UnknownArtifact):
                _resolve_candidate_for_project(
                    "prj-missing", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_artifact_not_a_managed_product_provenance_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-wrongkind", "Wrong Kind Of Artifact")
            ref = _register_unrelated_artifact(artifact_session, blobs)
            registry.create_revision("prj-wrongkind", "prj-wrongkind-r1", provenance_ref=ref)
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-x"),
            )
            with pytest.raises(_ProvenanceNotManagedProductError):
                _resolve_candidate_for_project(
                    "prj-wrongkind", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_referenced_candidate_not_accepted_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-notaccepted", "Not Accepted")
            ref = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-stage-failed",
            )
            registry.create_revision("prj-notaccepted", "prj-notaccepted-r1", provenance_ref=ref)
            not_accepted_ledger = _FakeLedger({
                "golden-work-stage-failed": [
                    {"candidate_id": "golden-work-stage-failed", "state": "GENERATING"},
                    {"candidate_id": "golden-work-stage-failed", "state": "STAGE_FAILED"},
                ],
            })
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=not_accepted_ledger,
            )
            with pytest.raises(_ReferencedCandidateNotEligibleError):
                _resolve_candidate_for_project(
                    "prj-notaccepted", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_a_real_accepted_managed_product_resolves_to_its_candidate(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-good", "A Real Managed Product")
            ref = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-real",
            )
            registry.create_revision("prj-good", "prj-good-r1", provenance_ref=ref)
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-real"),
            )
            resolved = _resolve_candidate_for_project(
                "prj-good", registry=registry,
                artifact_session=artifact_session, wiring=wiring,
            )
            assert resolved == "golden-work-real"


# ---------------------------------------------------------------------------
# Part 3: end-to-end HTTP proof over a real FastAPI app
# ---------------------------------------------------------------------------


@pytest.fixture()
def command_center_db(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "command_center.db"
    command.upgrade(_alembic_config(path), "head")
    return path


@pytest.fixture()
def command_center_engine(command_center_db: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(command_center_db))
    yield built
    built.dispose()


@pytest.fixture()
def http_app(
    command_center_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    pdp: PolicyDecisionPoint,
) -> FastAPI:
    artifact_factory = create_session_factory(artifact_engine)

    def artifact_session_scope() -> Iterator[Session]:
        with unit_of_work(artifact_factory) as session:
            yield session

    with unit_of_work(create_session_factory(command_center_engine)) as session:
        registry = ProjectRegistry(session)
        registry.create_project("prj-http", "HTTP Journey Product")
        with unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            ref = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-http",
            )
        registry.create_revision("prj-http", "prj-http-r1", provenance_ref=ref)

    wiring = _PreviewBridgeWiring(
        artifact_session_scope=artifact_session_scope, artifact_blobs=blobs,
        ledger=_accepted_ledger("golden-work-http"),
    )
    return create_app(
        command_center_engine, pdp,
        extensions=_CommandExtensions(preview_bridge=wiring),
    )


@pytest.fixture()
def http_client(http_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(http_app) as opened:
        yield opened


class TestProjectPreviewHttpRoute:
    def test_start_project_preview_reaches_the_same_job_type_as_the_candidate_route(
        self, http_client: TestClient,
    ) -> None:
        response = http_client.post("/api/projects/prj-http/preview")
        assert response.status_code == 202
        body = response.json()
        assert body["job_type"] == _PREVIEW_JOB_TYPE
        assert body["idempotency_key"] == "golden-work-http"
        assert "prj-http" not in body["job_id"]
        assert "golden-work-http" in body["job_id"]

    def test_double_post_returns_the_same_active_job(self, http_client: TestClient) -> None:
        first = http_client.post("/api/projects/prj-http/preview").json()
        second = http_client.post("/api/projects/prj-http/preview").json()
        assert first["job_id"] == second["job_id"]

    def test_get_before_any_open_is_null(self, http_client: TestClient) -> None:
        response = http_client.get("/api/projects/prj-http/preview")
        assert response.status_code == 200
        assert response.json() is None

    def test_get_after_open_rediscovers_the_active_job(self, http_client: TestClient) -> None:
        opened = http_client.post("/api/projects/prj-http/preview").json()
        found = http_client.get("/api/projects/prj-http/preview").json()
        assert found is not None
        assert found["job_id"] == opened["job_id"]

    def test_unknown_project_is_a_404(self, http_client: TestClient) -> None:
        response = http_client.post("/api/projects/no-such-project/preview")
        assert response.status_code == 404

    def test_reopen_after_a_real_cancel_mints_a_genuinely_new_job(
        self, http_client: TestClient, command_center_engine: Engine, pdp: PolicyDecisionPoint,
    ) -> None:
        first = http_client.post("/api/projects/prj-http/preview").json()
        # Real job-lifecycle progression, through the same real durable
        # service the worker itself uses -- never faked through the HTTP
        # surface, which structurally cannot transition anything.
        pep = PolicyEnforcementPoint(pdp, "test.readback")
        with unit_of_work(create_session_factory(command_center_engine)) as session:
            store = JobStore(session, pep)
            store.transition(first["job_id"], "RUNNING")
            store.transition(first["job_id"], "CANCELLED")

        second = http_client.post("/api/projects/prj-http/preview").json()
        assert second["job_id"] != first["job_id"]
        assert second["lifecycle_state"] == "QUEUED"
