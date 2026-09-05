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
    _MANAGED_PRODUCT_REVISION_SOURCE_SPEC,
    _NoRevisionForProjectError,
    _PreviewBridgeWiring,
    _ProvenanceNotManagedProductError,
    _ReferencedCandidateNotEligibleError,
    _RevisionHasNoProvenanceError,
    _UnknownRevisionForProjectError,
    _resolve_preview_subject_for_explicit_revision,
    _resolve_preview_subject_for_project,
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


def _submit(store: JobStore, subject_id: str):  # noqa: ANN201
    return _submit_or_recover_preview(store, subject_id, {"candidate_id": subject_id})


class TestSubmitOrRecoverPreview:
    def test_the_first_open_creates_a_real_job_at_attempt_one(self, job_store: JobStore) -> None:
        record = _submit(job_store, "golden-work-t1")
        assert record.idempotency_key == "golden-work-t1"
        assert record.job_id == "preview-golden-work-t1"

    def test_double_open_while_active_returns_the_same_job(self, job_store: JobStore) -> None:
        """Part I: double-click must never create two active runtimes."""
        first = _submit(job_store, "golden-work-t2")
        second = _submit(job_store, "golden-work-t2")
        assert first.job_id == second.job_id
        assert first.idempotency_key == second.idempotency_key

    def test_reopen_after_a_real_terminal_cancel_mints_a_new_job(self, job_store: JobStore) -> None:
        """The exact previously-verified limitation, now fixed: CANCELLED no
        longer masquerades as reusable."""
        first = _submit(job_store, "golden-work-t3")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "CANCELLED")

        second = _submit(job_store, "golden-work-t3")
        assert second.job_id != first.job_id
        assert second.idempotency_key == "golden-work-t3#2"
        assert second.lifecycle_state == "QUEUED"

    def test_a_second_reopen_after_another_terminal_cycle_mints_a_third(
        self, job_store: JobStore,
    ) -> None:
        first = _submit(job_store, "golden-work-t4")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "CANCELLED")
        second = _submit(job_store, "golden-work-t4")
        job_store.transition(second.job_id, "RUNNING")
        job_store.transition(second.job_id, "CANCELLED")
        third = _submit(job_store, "golden-work-t4")

        assert third.idempotency_key == "golden-work-t4#3"
        assert len({first.job_id, second.job_id, third.job_id}) == 3

    def test_a_recoverable_job_is_rediscovered_not_replaced(self, job_store: JobStore) -> None:
        """RECOVERABLE is not in the Job machine's own declared `terminal`
        set — a later real recovery could still move it forward, so minting
        a fresh identity underneath it would orphan that path."""
        first = _submit(job_store, "golden-work-t5")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "FAILED")
        job_store.transition(first.job_id, "RECOVERABLE")

        again = _submit(job_store, "golden-work-t5")
        assert again.job_id == first.job_id

    def test_the_payload_is_passed_through_unchanged(self, job_store: JobStore) -> None:
        """A revision-scoped subject's own payload (`project_id`/
        `revision_id`, no `candidate_id`) is stored verbatim — this helper
        never inspects or rewrites it."""
        record = _submit_or_recover_preview(
            job_store, "prj-rev2", {"project_id": "prj", "revision_id": "prj-r2"},
        )
        assert record.payload == {"project_id": "prj", "revision_id": "prj-r2"}


class TestFindCurrentPreview:
    def test_nothing_submitted_yet_is_none(self, job_store: JobStore) -> None:
        assert _find_current_preview(job_store, "golden-work-never-opened") is None

    def test_finds_the_active_job_not_an_old_terminal_one(self, job_store: JobStore) -> None:
        first = _submit(job_store, "golden-work-t6")
        job_store.transition(first.job_id, "RUNNING")
        job_store.transition(first.job_id, "CANCELLED")
        second = _submit(job_store, "golden-work-t6")

        found = _find_current_preview(job_store, "golden-work-t6")
        assert found is not None
        assert found.job_id == second.job_id
        assert found.lifecycle_state == "QUEUED"

    def test_refresh_while_active_rediscovers_the_same_job(self, job_store: JobStore) -> None:
        active = _submit(job_store, "golden-work-t7")
        found = _find_current_preview(job_store, "golden-work-t7")
        assert found is not None
        assert found.job_id == active.job_id

    def test_after_a_terminal_cycle_the_terminal_job_is_still_found_honestly(
        self, job_store: JobStore,
    ) -> None:
        """No newer cycle exists yet: the terminal one is the honest truth,
        never hidden and never pretended active (the caller reads
        `lifecycle_state` itself to know which)."""
        first = _submit(job_store, "golden-work-t8")
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


def _accepted_ledger(*candidate_ids: str) -> _FakeLedger:
    return _FakeLedger({
        candidate_id: [
            {"candidate_id": candidate_id, "state": "ALLOCATED", "goal_hash": "sha256:" + "a" * 64},
            {"candidate_id": candidate_id, "state": "ACCEPTED"},
        ]
        for candidate_id in candidate_ids
    })


def _register_revision_source_artifact(
    artifact_session: Session, blobs: ArtifactBlobStore, *, payload: bytes = b"PK\x05\x06" + b"\x00" * 18,
    context_hash: str = "sha256:" + "c" * 64,
) -> str:
    """A minimal, real, content-addressed `managed-product-revision-
    source/1.0.0` artifact — an empty-but-structurally-valid ZIP's own end-
    of-central-directory record by default, real enough for resolver-level
    tests that never reach real extraction (that is `TestMaterializedSource`
    /`test_product_change.py`'s own job)."""
    return ArtifactStore(artifact_session, blobs).register(
        payload,
        ProvenanceInput(
            producer_agent="engineering.product_change", provider_model="local",
            task_id="prj", specification_version=_MANAGED_PRODUCT_REVISION_SOURCE_SPEC,
            context_hash=context_hash,
        ),
    )


class TestResolvePreviewSubjectForProject:
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
                _resolve_preview_subject_for_project(
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
                _resolve_preview_subject_for_project(
                    "prj-norev", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_multiple_revisions_select_the_max_sequence_current_one(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        """F-0074: D-030's own ratified rule -- current = max(sequence) --
        never the old "exactly one revision" refusal. The SECOND-created
        revision (real, higher sequence) is deliberately given a
        `revision_id` that sorts LEXICALLY BEFORE the first one
        ("...-a-second" < "...-r1"), so a resolver that mistakenly picked
        the lexically-greatest id would return the wrong revision here --
        proving real sequence, never the id string, decides."""
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-multirev", "Two Revisions")
            ref1 = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-multirev",
            )
            ref2 = _register_revision_source_artifact(artifact_session, blobs)
            registry.create_revision("prj-multirev", "prj-multirev-r1", provenance_ref=ref1)
            registry.create_revision("prj-multirev", "prj-multirev-a-second", provenance_ref=ref2)
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-multirev"),
            )
            subject = _resolve_preview_subject_for_project(
                "prj-multirev", registry=registry,
                artifact_session=artifact_session, wiring=wiring,
            )
            assert subject.revision_id == "prj-multirev-a-second"
            assert subject.kind == "archive"
            assert subject.subject_id == "prj-multirev-a-second"
            assert "prj-multirev-a-second" < "prj-multirev-r1"  # lexically hostile, by construction

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
                _resolve_preview_subject_for_project(
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
                _resolve_preview_subject_for_project(
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
                _resolve_preview_subject_for_project(
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
                _resolve_preview_subject_for_project(
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
                _resolve_preview_subject_for_project(
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
            subject = _resolve_preview_subject_for_project(
                "prj-good", registry=registry,
                artifact_session=artifact_session, wiring=wiring,
            )
            assert subject.subject_id == "golden-work-real"
            assert subject.revision_id == "prj-good-r1"
            assert subject.kind == "candidate"

    def test_a_promoted_revision_resolves_to_an_archive_subject_no_candidate_needed(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        """Revision 2+: no `CandidateLedger` identity is required at all --
        a ledger double that RAISES the moment `.history()` is called
        proves this mechanically, never merely by returning an empty
        result a bug could also produce."""
        class _RaisingLedger:
            def history(self, candidate_id: str) -> tuple[dict[str, object], ...]:
                raise AssertionError(
                    f"CandidateLedger.history({candidate_id!r}) must never be called "
                    "for an archive-backed (D-030 promoted) revision"
                )

        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-archived", "A Promoted Revision")
            ref = _register_revision_source_artifact(artifact_session, blobs)
            registry.create_revision("prj-archived", "prj-archived-r2", provenance_ref=ref)
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_RaisingLedger(),
            )
            subject = _resolve_preview_subject_for_project(
                "prj-archived", registry=registry,
                artifact_session=artifact_session, wiring=wiring,
            )
            assert subject.kind == "archive"
            assert subject.subject_id == "prj-archived-r2"
            assert subject.revision_id == "prj-archived-r2"


class TestResolvePreviewSubjectForExplicitRevision:
    """Managed Product Revision History + Restore-as-New Convergence:
    "Önizle" on a non-current `Sürüm` must resolve exactly the named
    revision, never `max(sequence)` -- every real refusal reason a
    current-revision resolution would raise applies identically here."""

    def test_unknown_revision_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-explicit", "Explicit Revision Product")
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-explicit"),
            )
            with pytest.raises(_UnknownRevisionForProjectError):
                _resolve_preview_subject_for_explicit_revision(
                    "prj-explicit", "prj-explicit-r999", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_a_revision_of_a_different_project_is_refused(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-a", "Product A")
            registry.create_project("prj-b", "Product B")
            ref = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-b",
            )
            registry.create_revision("prj-b", "prj-b-r1", provenance_ref=ref)
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-b"),
            )
            with pytest.raises(_UnknownRevisionForProjectError):
                _resolve_preview_subject_for_explicit_revision(
                    "prj-a", "prj-b-r1", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )

    def test_an_older_non_current_candidate_backed_revision_resolves(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        """The project's CURRENT revision is r2 (archive-backed); this
        explicitly names r1 (candidate-backed) and must resolve to IT,
        never silently substituted with current."""
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-hist", "Historical Preview Product")
            ref1 = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-hist",
            )
            registry.create_revision("prj-hist", "prj-hist-r1", provenance_ref=ref1)
            ref2 = _register_revision_source_artifact(artifact_session, blobs)
            registry.create_revision("prj-hist", "prj-hist-r2", provenance_ref=ref2)

            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_accepted_ledger("golden-work-hist"),
            )
            # The current-revision path resolves r2 (archive) ...
            current_subject = _resolve_preview_subject_for_project(
                "prj-hist", registry=registry, artifact_session=artifact_session, wiring=wiring,
            )
            assert current_subject.revision_id == "prj-hist-r2"
            assert current_subject.kind == "archive"

            # ... but explicitly naming r1 resolves the historical,
            # candidate-backed one, never the current one.
            historical_subject = _resolve_preview_subject_for_explicit_revision(
                "prj-hist", "prj-hist-r1", registry=registry,
                artifact_session=artifact_session, wiring=wiring,
            )
            assert historical_subject.revision_id == "prj-hist-r1"
            assert historical_subject.kind == "candidate"
            assert historical_subject.subject_id == "golden-work-hist"

    def test_an_ineligible_candidate_is_refused_even_when_historical(
        self, registry_engine: Engine, artifact_engine: Engine, blobs: ArtifactBlobStore,
    ) -> None:
        """A historical preview is not a weaker eligibility rule: a
        candidate that is not currently ACCEPTED is refused exactly as it
        would be for a current-revision preview."""
        with unit_of_work(create_session_factory(registry_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            registry = ProjectRegistry(session)
            registry.create_project("prj-ineligible", "Ineligible Historical Candidate")
            ref = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-ineligible",
            )
            registry.create_revision("prj-ineligible", "prj-ineligible-r1", provenance_ref=ref)
            wiring = _PreviewBridgeWiring(
                artifact_session_scope=lambda: iter(()), artifact_blobs=blobs,
                ledger=_FakeLedger({}),  # no recorded history at all
            )
            with pytest.raises(_ReferencedCandidateNotEligibleError):
                _resolve_preview_subject_for_explicit_revision(
                    "prj-ineligible", "prj-ineligible-r1", registry=registry,
                    artifact_session=artifact_session, wiring=wiring,
                )


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

        # F-0074: a second real product, seeded with a Factory-origin r1
        # (current at fixture setup) — later revised to r2 (archive-backed,
        # `TestProjectPreviewMultiRevisionHttpRoute`'s own tests promote it
        # mid-test to prove revision-scoped identity), never touching the
        # single-revision `prj-http` fixture above.
        registry.create_project("prj-http-multi", "Multi-Revision Product")
        with unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            multi_ref1 = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-http-multi",
            )
        registry.create_revision("prj-http-multi", "prj-http-multi-r1", provenance_ref=multi_ref1)

        # Revision History + Restore-as-New Convergence: a third real
        # product, seeded with BOTH revisions already present at fixture
        # setup (r1 candidate-backed, r2 archive-backed/current) — never
        # touching the two fixtures above — so historical-preview HTTP
        # tests can name the non-current r1 deterministically.
        registry.create_project("prj-http-hist", "Historical Preview Product")
        with unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            hist_ref1 = _register_managed_product_artifact(
                artifact_session, blobs, candidate_id="golden-work-http-hist",
            )
        registry.create_revision("prj-http-hist", "prj-http-hist-r1", provenance_ref=hist_ref1)
        with unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            hist_ref2 = _register_revision_source_artifact(artifact_session, blobs)
        registry.create_revision("prj-http-hist", "prj-http-hist-r2", provenance_ref=hist_ref2)

    wiring = _PreviewBridgeWiring(
        artifact_session_scope=artifact_session_scope, artifact_blobs=blobs,
        ledger=_accepted_ledger("golden-work-http", "golden-work-http-multi", "golden-work-http-hist"),
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


class TestProjectPreviewMultiRevisionHttpRoute:
    """F-0074 (`PREVIEW_BRIDGE_MULTI_REVISION_GAP`): real, end-to-end proof
    that the SAME `POST`/`GET /api/projects/{project_id}/preview` routes
    correctly serve a Managed Product across a real current-revision
    change, never confusing an old revision's own active/terminal job with
    the new current revision's own."""

    def test_archive_backed_current_revision_resolves_without_a_candidate(
        self, http_client: TestClient, command_center_engine: Engine, artifact_engine: Engine,
        blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(command_center_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            ref2 = _register_revision_source_artifact(
                artifact_session, blobs, context_hash="sha256:" + "d" * 64,
            )
            ProjectRegistry(session).create_revision(
                "prj-http-multi", "prj-http-multi-r2", provenance_ref=ref2,
            )

        response = http_client.post("/api/projects/prj-http-multi/preview")
        assert response.status_code == 202
        body = response.json()
        assert body["idempotency_key"] == "prj-http-multi-r2"
        assert "prj-http-multi-r2" in body["job_id"]

    def test_revision_advance_mints_a_new_job_never_reusing_the_old_revisions(
        self, http_client: TestClient, command_center_engine: Engine, artifact_engine: Engine,
        blobs: ArtifactBlobStore,
    ) -> None:
        """Part H: Revision 1's own preview stays active/untouched; a
        request made once Revision 2 is current resolves Revision 2, on a
        genuinely different job — never the old job mutated or reused."""
        first = http_client.post("/api/projects/prj-http-multi/preview").json()
        assert first["idempotency_key"] == "golden-work-http-multi"

        with unit_of_work(create_session_factory(command_center_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            ref2 = _register_revision_source_artifact(
                artifact_session, blobs, context_hash="sha256:" + "e" * 64,
            )
            ProjectRegistry(session).create_revision(
                "prj-http-multi", "prj-http-multi-r2", provenance_ref=ref2,
            )

        second = http_client.post("/api/projects/prj-http-multi/preview").json()
        assert second["job_id"] != first["job_id"]
        assert second["idempotency_key"] == "prj-http-multi-r2"
        assert second["lifecycle_state"] == "QUEUED"

        # The old Revision 1 job is untouched -- still findable, still
        # itself, never silently repurposed for Revision 2.
        still_first = http_client.get("/api/candidates/golden-work-http-multi/preview").json()
        assert still_first is not None
        assert still_first["job_id"] == first["job_id"]

    def test_double_open_on_the_same_archive_backed_revision_returns_one_job(
        self, http_client: TestClient, command_center_engine: Engine, artifact_engine: Engine,
        blobs: ArtifactBlobStore,
    ) -> None:
        with unit_of_work(create_session_factory(command_center_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            ref2 = _register_revision_source_artifact(
                artifact_session, blobs, context_hash="sha256:" + "f" * 64,
            )
            ProjectRegistry(session).create_revision(
                "prj-http-multi", "prj-http-multi-r2", provenance_ref=ref2,
            )

        first = http_client.post("/api/projects/prj-http-multi/preview").json()
        second = http_client.post("/api/projects/prj-http-multi/preview").json()
        assert first["job_id"] == second["job_id"]

    def test_refresh_while_an_archive_backed_revision_is_active_rediscovers_it(
        self, http_client: TestClient, command_center_engine: Engine, artifact_engine: Engine,
        blobs: ArtifactBlobStore,
    ) -> None:
        """A real browser refresh (`GET`, never creating anything) during
        an active Revision 2 preview must rediscover that SAME real
        execution — no frontend-local authority, no duplicate job."""
        with unit_of_work(create_session_factory(command_center_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            ref2 = _register_revision_source_artifact(
                artifact_session, blobs, context_hash="sha256:" + "1" * 64,
            )
            ProjectRegistry(session).create_revision(
                "prj-http-multi", "prj-http-multi-r2", provenance_ref=ref2,
            )

        opened = http_client.post("/api/projects/prj-http-multi/preview").json()
        refreshed = http_client.get("/api/projects/prj-http-multi/preview").json()
        assert refreshed is not None
        assert refreshed["job_id"] == opened["job_id"]
        assert refreshed["idempotency_key"] == "prj-http-multi-r2"

    def test_reopen_after_terminal_on_an_archive_backed_revision_mints_a_new_job(
        self, http_client: TestClient, command_center_engine: Engine, artifact_engine: Engine,
        blobs: ArtifactBlobStore, pdp: PolicyDecisionPoint,
    ) -> None:
        with unit_of_work(create_session_factory(command_center_engine)) as session, \
             unit_of_work(create_session_factory(artifact_engine)) as artifact_session:
            ref2 = _register_revision_source_artifact(
                artifact_session, blobs, context_hash="sha256:" + "0" * 64,
            )
            ProjectRegistry(session).create_revision(
                "prj-http-multi", "prj-http-multi-r2", provenance_ref=ref2,
            )

        first = http_client.post("/api/projects/prj-http-multi/preview").json()
        pep = PolicyEnforcementPoint(pdp, "test.readback")
        with unit_of_work(create_session_factory(command_center_engine)) as session:
            store = JobStore(session, pep)
            store.transition(first["job_id"], "RUNNING")
            store.transition(first["job_id"], "CANCELLED")

        second = http_client.post("/api/projects/prj-http-multi/preview").json()
        assert second["job_id"] != first["job_id"]
        assert second["idempotency_key"] == "prj-http-multi-r2#2"
        assert second["lifecycle_state"] == "QUEUED"


class TestRevisionPreviewHttpRoute:
    """Managed Product Revision History + Restore-as-New Convergence:
    "Önizle" on an explicitly named historical `Sürüm`, over the real
    `prj-http-hist` fixture (r1 candidate-backed, r2 archive-backed and
    current)."""

    def test_previewing_the_historical_r1_reaches_the_candidate_job_never_the_current_one(
        self, http_client: TestClient,
    ) -> None:
        response = http_client.post("/api/projects/prj-http-hist/revisions/prj-http-hist-r1/preview")
        assert response.status_code == 202
        body = response.json()
        assert body["job_type"] == _PREVIEW_JOB_TYPE
        assert body["idempotency_key"] == "golden-work-http-hist"

    def test_previewing_the_current_r2_by_explicit_id_reaches_its_own_revision_scoped_job(
        self, http_client: TestClient,
    ) -> None:
        response = http_client.post("/api/projects/prj-http-hist/revisions/prj-http-hist-r2/preview")
        assert response.status_code == 202
        assert response.json()["idempotency_key"] == "prj-http-hist-r2"

    def test_historical_preview_never_touches_the_normal_current_revision_job(
        self, http_client: TestClient,
    ) -> None:
        """Opening a real historical (r1) preview and a real current
        (via the normal `/preview` route) preview for the SAME project
        mint two genuinely independent jobs, never one masquerading as
        the other."""
        historical = http_client.post(
            "/api/projects/prj-http-hist/revisions/prj-http-hist-r1/preview",
        ).json()
        current = http_client.post("/api/projects/prj-http-hist/preview").json()
        assert historical["job_id"] != current["job_id"]
        assert historical["idempotency_key"] != current["idempotency_key"]
        # And the current-revision route's own state is unaffected by the
        # historical preview: reading it back still returns the SAME
        # current job, not the historical one.
        still_current = http_client.get("/api/projects/prj-http-hist/preview").json()
        assert still_current["job_id"] == current["job_id"]

    def test_get_before_any_open_is_null(self, http_client: TestClient) -> None:
        response = http_client.get("/api/projects/prj-http-hist/revisions/prj-http-hist-r1/preview")
        assert response.status_code == 200
        assert response.json() is None

    def test_get_after_open_rediscovers_the_active_historical_job(self, http_client: TestClient) -> None:
        opened = http_client.post(
            "/api/projects/prj-http-hist/revisions/prj-http-hist-r1/preview",
        ).json()
        found = http_client.get("/api/projects/prj-http-hist/revisions/prj-http-hist-r1/preview").json()
        assert found is not None
        assert found["job_id"] == opened["job_id"]

    def test_unknown_revision_is_refused(self, http_client: TestClient) -> None:
        response = http_client.post(
            "/api/projects/prj-http-hist/revisions/no-such-revision/preview",
        )
        assert response.status_code >= 400

    def test_a_revision_of_a_different_project_is_refused(self, http_client: TestClient) -> None:
        response = http_client.post(
            "/api/projects/prj-http-hist/revisions/prj-http-multi-r1/preview",
        )
        assert response.status_code >= 400
