"""ARK-REQ-0027 integration evidence — enqueue, never execute.

A real FastAPI application over a real SQLite file migrated by the real Alembic
chain, with a real PDP loaded from the authority map. Nothing is substituted:
`VERIFICATION_ARCHITECTURE.md` makes a tier from T5 upward that substitutes a
database NOT_CONFIGURED, never PASS.

WHAT THE REQUIREMENT ACTUALLY ASKS. `MS §Constitution 8` — no long AI work in
HTTP requests. It is not a latency budget, and none of the evidence below is a
timing measurement. What is asserted is that after the request returns, the work
demonstrably has **not** started: the job sits in the state the canonical machine
declares initial, no execution attempt exists, and no checkpoint exists. A route
that had run the work could not produce that state.

Scope note: this is the backend half of Package 4 and it **discharges nothing**.
ARK-REQ-0027 remains open until the Phase 7 traceability record, report and gate
in Package 5.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.execution.durable.errors import DuplicateJobIdentity, InvalidJobIdentity, UnknownJob
from arkali.execution.durable.execution import JobExecution
from arkali.execution.durable.job_store import JobStore
from arkali.execution.durable.records import INITIAL_STATE, DurableJobRecord
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.surfaces.command.app import create_app

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

START = dt.datetime(2026, 3, 4, 5, 6, 7, tzinfo=dt.timezone.utc)


def alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


def enqueue_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "job_id": "JOB-API-1",
        "job_type": "arkali.test.noop",
        "idempotency_key": "key-api-1",
        "payload": {"prompt": "opaque to this surface"},
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "jobs.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def app(engine: Engine, pdp: PolicyDecisionPoint) -> FastAPI:
    return create_app(engine, pdp, lambda: START)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as opened:
        yield opened


class TestEnqueueReturnsADurableReference:
    def test_a_valid_request_is_accepted_and_returns_the_reference(
        self, client: TestClient
    ) -> None:
        response = client.post("/api/jobs", json=enqueue_body())
        assert response.status_code == 202, (
            "202 Accepted is the contract: the request was accepted and the "
            "processing has not completed"
        )
        body = response.json()
        assert body["job_id"] == "JOB-API-1"
        assert body["job_type"] == "arkali.test.noop"
        assert body["idempotency_key"] == "key-api-1"
        assert body["lifecycle_state"] == INITIAL_STATE

    def test_the_response_carries_the_canonical_initial_state_not_a_literal(
        self, client: TestClient
    ) -> None:
        """Derived from the machine, so the surface cannot publish a state the
        canonical relation does not declare as the starting point."""
        body = client.post("/api/jobs", json=enqueue_body()).json()
        assert body["lifecycle_state"] == INITIAL_STATE

    def test_the_response_exposes_nothing_executional(
        self, client: TestClient
    ) -> None:
        """NEGATIVE CONTROL over the wire shape itself.

        Attempt numbers, owners, heartbeats, deadlines, retry counts, workers
        and queue positions must not be representable. Several of them describe
        decisions Phase 7 is not entitled to make at all.
        """
        body = client.post("/api/jobs", json=enqueue_body()).json()
        assert set(body) == {
            "job_id", "job_type", "idempotency_key", "lifecycle_state",
            "created_at",
        }
        forbidden = (
            "owner", "attempt", "heartbeat", "deadline", "worker", "queue",
            "priority", "capacity", "max_attempts", "payload", "path", "url",
        )
        rendered = response_text = str(body)
        for token in forbidden:
            assert token not in rendered, f"{token!r} leaked onto the wire"
        assert "sqlite" not in response_text.lower()

    def test_the_job_is_readable_through_the_status_route(
        self, client: TestClient
    ) -> None:
        client.post("/api/jobs", json=enqueue_body())
        response = client.get("/api/jobs/JOB-API-1")
        assert response.status_code == 200
        assert response.json()["job_id"] == "JOB-API-1"

    def test_an_unknown_job_reference_is_a_refusal_not_an_empty_success(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/jobs/JOB-NOT-THERE")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == UnknownJob.code


class TestNoLongWorkHappensInTheRequest:
    """`ARK-REQ-0027`, asserted by state rather than by a stopwatch."""

    def test_after_the_response_the_job_has_not_started(
        self, client: TestClient, engine: Engine, pdp: PolicyDecisionPoint
    ) -> None:
        """The core evidence. Read back through the canonical services.

        A handler that had executed the job could not leave this state: running
        it requires `begin_attempt`, which moves the job out of the initial
        state and writes an attempt row.
        """
        assert client.post("/api/jobs", json=enqueue_body()).status_code == 202
        pep = PolicyEnforcementPoint(pdp, "test.readback")
        with unit_of_work(create_session_factory(engine)) as session:
            execution = JobExecution(session, pep)
            record = execution.jobs.require("JOB-API-1")
            assert record.lifecycle_state == INITIAL_STATE
            assert execution.attempt_count("JOB-API-1") == 0, (
                "an execution attempt exists; the request ran the job"
            )
            assert execution.current_attempt("JOB-API-1") is None
            assert execution.jobs.checkpoints("JOB-API-1") == ()

    def test_repeated_enqueues_never_accumulate_execution_state(
        self, client: TestClient, engine: Engine, pdp: PolicyDecisionPoint
    ) -> None:
        for index in range(5):
            client.post(
                "/api/jobs",
                json=enqueue_body(
                    job_id=f"JOB-API-{index}", idempotency_key=f"key-{index}"
                ),
            )
        pep = PolicyEnforcementPoint(pdp, "test.readback")
        with unit_of_work(create_session_factory(engine)) as session:
            execution = JobExecution(session, pep)
            for index in range(5):
                assert execution.attempt_count(f"JOB-API-{index}") == 0

    def test_the_status_route_reports_state_and_never_advances_it(
        self, client: TestClient
    ) -> None:
        """A read that transitioned would be long work by another name."""
        client.post("/api/jobs", json=enqueue_body())
        for _read in range(5):
            body = client.get("/api/jobs/JOB-API-1").json()
            assert body["lifecycle_state"] == INITIAL_STATE


class TestIdempotencyIsTheDurableOne:
    def test_a_repeated_key_resolves_to_the_same_durable_job(
        self, client: TestClient
    ) -> None:
        first = client.post("/api/jobs", json=enqueue_body())
        second = client.post("/api/jobs", json=enqueue_body())
        assert first.status_code == second.status_code == 202
        assert first.json() == second.json()

    def test_a_repeated_key_creates_no_second_row(
        self, client: TestClient, engine: Engine
    ) -> None:
        for _repeat in range(4):
            client.post("/api/jobs", json=enqueue_body())
        with unit_of_work(create_session_factory(engine)) as session:
            rows = session.query(DurableJobRecord).all()
            assert len(rows) == 1

    def test_a_different_job_id_reusing_a_key_returns_the_recorded_job(
        self, client: TestClient
    ) -> None:
        """The persisted constraint decides, not the caller's new id.

        C-19 scopes idempotency by (`job_type`, `idempotency_key`), so a second
        submission under the same identity is the same work however it is
        labelled - and the surface must not invent a different answer.
        """
        client.post("/api/jobs", json=enqueue_body())
        again = client.post("/api/jobs", json=enqueue_body(job_id="JOB-OTHER"))
        assert again.status_code == 202
        assert again.json()["job_id"] == "JOB-API-1"

    def test_a_conflicting_job_id_under_a_new_key_is_refused(
        self, client: TestClient
    ) -> None:
        client.post("/api/jobs", json=enqueue_body())
        clash = client.post(
            "/api/jobs", json=enqueue_body(idempotency_key="key-other")
        )
        assert clash.status_code == 409
        assert clash.json()["detail"]["code"] == DuplicateJobIdentity.code


class TestTheErrorContract:
    @pytest.mark.parametrize(
        "body",
        [
            {},
            {"job_id": "J", "job_type": "t"},
            {"job_id": "", "job_type": "t", "idempotency_key": "k"},
            {"job_id": "J", "job_type": "t", "idempotency_key": "k", "extra": 1},
        ],
        ids=["empty", "missing-key", "blank-id", "unknown-field"],
    )
    def test_a_malformed_request_is_refused(
        self, client: TestClient, body: dict[str, object]
    ) -> None:
        assert client.post("/api/jobs", json=body).status_code == 422

    def test_a_whitespace_only_identity_is_refused_by_the_domain(
        self, client: TestClient
    ) -> None:
        """Passes the transport shape, refused by C-19's own rule."""
        response = client.post(
            "/api/jobs", json=enqueue_body(job_type="   ")
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == InvalidJobIdentity.code

    def test_a_refusal_leaks_no_internals(self, client: TestClient) -> None:
        """NEGATIVE CONTROL: no traceback, path, URL or SQL crosses the wire."""
        client.post("/api/jobs", json=enqueue_body())
        rendered = client.post(
            "/api/jobs", json=enqueue_body(idempotency_key="key-other")
        ).text.lower()
        for token in ("traceback", "sqlite", ".py", "c:\\", "/users/", "select "):
            assert token not in rendered, f"{token!r} leaked in a refusal"

    def test_an_undeclared_job_type_is_accepted_not_admitted(
        self, client: TestClient
    ) -> None:
        """Deliberate, and the consistent reading of C-19.

        The job-type registry is the authority on **pause capability**, not a
        precondition of submitting. Requiring registration here would be
        admission control, which is C-21 at Phase 8 - so an undeclared type
        enqueues, and only an operation that asks about its capabilities
        fails closed.
        """
        response = client.post(
            "/api/jobs", json=enqueue_body(job_type="arkali.test.never-declared")
        )
        assert response.status_code == 202


class TestPolicyIsEnforced:
    def test_a_denied_policy_refuses_and_writes_nothing(
        self, tmp_path: pathlib.Path, database_path: pathlib.Path
    ) -> None:
        """A REAL PDP over an authority map that denies workspace writes."""
        import shutil

        import yaml

        root = tmp_path / "denied"
        for relative in (
            "docs/canonical/AUTHORITY_MAP.yaml",
            "docs/canonical/SECURITY_ARCHITECTURE.md",
            "docs/canonical/ARCHITECTURE.md",
        ):
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        mapping = yaml.safe_load(
            (root / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
        )
        mapping["operation_classes"]["WRITE_WORKSPACE_FILE"] = {
            "default": "DENY", "fixed": "DENY"
        }
        (root / "docs/canonical/AUTHORITY_MAP.yaml").write_text(
            yaml.safe_dump(mapping), encoding="utf-8"
        )

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            denied_app = create_app(engine, PolicyDecisionPoint.load(root))
            with TestClient(denied_app) as denied_client:
                response = denied_client.post("/api/jobs", json=enqueue_body())
            assert response.status_code == 403
            # Derived from the error class, not transcribed: a code written
            # here as a literal expires the moment the taxonomy is renumbered.
            assert response.json()["detail"]["code"] == PolicyDenied.code
            with unit_of_work(create_session_factory(engine)) as session:
                assert session.query(DurableJobRecord).all() == [], (
                    "a denied enqueue left a durable row behind"
                )
        finally:
            engine.dispose()


class TestDurabilitySurvivesRestart:
    def test_the_job_resolves_from_a_completely_fresh_application(
        self, database_path: pathlib.Path, pdp: PolicyDecisionPoint
    ) -> None:
        """The restart proof, application by application.

        1-3 a fresh app enqueues and returns a reference.
        4   the engine and the application are disposed.
        5-7 a brand new engine and application resolve the same identity.
        8   the durable facts are unchanged and nothing ran in between.
        """
        first_engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with TestClient(create_app(first_engine, pdp, lambda: START)) as client:
                accepted = client.post("/api/jobs", json=enqueue_body())
                assert accepted.status_code == 202
                reference = accepted.json()
        finally:
            first_engine.dispose()

        second_engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with TestClient(create_app(second_engine, pdp, lambda: START)) as client:
                resolved = client.get("/api/jobs/JOB-API-1")
            assert resolved.status_code == 200
            assert resolved.json() == reference, (
                "the durable reference changed across a restart"
            )
            pep = PolicyEnforcementPoint(pdp, "test.readback")
            with unit_of_work(create_session_factory(second_engine)) as session:
                execution = JobExecution(session, pep)
                assert execution.jobs.require(
                    "JOB-API-1"
                ).lifecycle_state == INITIAL_STATE
                assert execution.attempt_count("JOB-API-1") == 0, (
                    "work started at some point; the request was supposed to "
                    "enqueue only"
                )
        finally:
            second_engine.dispose()

    def test_idempotency_still_holds_across_a_restart(
        self, database_path: pathlib.Path, pdp: PolicyDecisionPoint
    ) -> None:
        """An in-memory idempotency cache would forget here. The constraint does not."""
        first_engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with TestClient(create_app(first_engine, pdp, lambda: START)) as client:
                client.post("/api/jobs", json=enqueue_body())
        finally:
            first_engine.dispose()

        second_engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with TestClient(create_app(second_engine, pdp, lambda: START)) as client:
                repeat = client.post("/api/jobs", json=enqueue_body())
            assert repeat.status_code == 202
            assert repeat.json()["job_id"] == "JOB-API-1"
            with unit_of_work(create_session_factory(second_engine)) as session:
                assert len(session.query(DurableJobRecord).all()) == 1
        finally:
            second_engine.dispose()

    def test_the_enqueued_job_is_reachable_by_the_durable_services(
        self, database_path: pathlib.Path, pdp: PolicyDecisionPoint
    ) -> None:
        """The surface created a real C-19 job, not a surface-local record."""
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with TestClient(create_app(engine, pdp, lambda: START)) as client:
                client.post("/api/jobs", json=enqueue_body())
            pep = PolicyEnforcementPoint(pdp, "test.readback")
            with unit_of_work(create_session_factory(engine)) as session:
                store = JobStore(session, pep)
                found = store.find_submitted("arkali.test.noop", "key-api-1")
                assert found is not None and found.job_id == "JOB-API-1"
        finally:
            engine.dispose()
