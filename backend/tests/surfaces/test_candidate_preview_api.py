""""Uygulamayı Aç" / "Durdur" — the candidate-preview intake, discovery and
cancel-request routes over the real, live C-19 `JobStore`.

Same tier as `test_command_jobs_api.py`: a real FastAPI app over a real
SQLite file migrated by the real Alembic chain, nothing substituted.
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
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.surfaces.command.app import create_app

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
START = dt.datetime(2026, 3, 4, 5, 6, 7, tzinfo=dt.timezone.utc)


def alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


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


class TestStartPreview:
    def test_enqueues_a_real_candidate_preview_job(self, client: TestClient) -> None:
        response = client.post("/api/candidates/golden-work-129/preview")

        assert response.status_code == 202
        body = response.json()
        assert body["job_id"] == "preview-golden-work-129"
        assert body["job_type"] == "candidate.preview"
        assert body["idempotency_key"] == "golden-work-129"
        assert body["lifecycle_state"] == "QUEUED"

    def test_a_second_click_for_the_same_candidate_returns_the_same_job_not_a_duplicate(
        self, client: TestClient,
    ) -> None:
        """The whole duplicate-start dedup mechanism: C-19's own idempotent
        `submit`, not a new preview registry."""
        first = client.post("/api/candidates/golden-work-129/preview").json()
        second = client.post("/api/candidates/golden-work-129/preview").json()

        assert first["job_id"] == second["job_id"]
        assert first["created_at"] == second["created_at"]

    def test_two_different_candidates_get_two_real_distinct_jobs(
        self, client: TestClient,
    ) -> None:
        one = client.post("/api/candidates/golden-work-129/preview").json()
        two = client.post("/api/candidates/golden-work-130/preview").json()

        assert one["job_id"] != two["job_id"]


class TestFindPreview:
    def test_returns_null_for_a_candidate_nobody_has_opened(self, client: TestClient) -> None:
        response = client.get("/api/candidates/golden-work-999/preview")

        assert response.status_code == 200
        assert response.json() is None

    def test_rediscovers_a_real_job_after_it_was_opened(self, client: TestClient) -> None:
        started = client.post("/api/candidates/golden-work-129/preview").json()

        found = client.get("/api/candidates/golden-work-129/preview").json()

        assert found is not None
        assert found["job_id"] == started["job_id"]

    def test_never_creates_anything_itself(self, client: TestClient) -> None:
        client.get("/api/candidates/golden-work-129/preview")

        still_nothing = client.get("/api/candidates/golden-work-129/preview").json()
        assert still_nothing is None


class TestCancelPreview:
    def test_checkpoints_a_request_rather_than_transitioning_the_job(
        self, client: TestClient,
    ) -> None:
        started = client.post("/api/candidates/golden-work-129/preview").json()
        job_id = started["job_id"]

        response = client.post(f"/api/jobs/{job_id}/cancel")

        assert response.status_code == 200
        # The route itself never transitions -- the job is exactly where
        # `submit` left it (QUEUED, canonical initial state) until a real
        # worker claims it and, later, transitions it on its own.
        assert response.json()["lifecycle_state"] == "QUEUED"
        checkpoints = client.get(f"/api/jobs/{job_id}/checkpoints").json()
        assert any(c["payload"].get("phase") == "cancel_requested" for c in checkpoints)

    def test_is_idempotent_pressed_twice(self, client: TestClient) -> None:
        started = client.post("/api/candidates/golden-work-129/preview").json()
        job_id = started["job_id"]

        first = client.post(f"/api/jobs/{job_id}/cancel")
        second = client.post(f"/api/jobs/{job_id}/cancel")

        assert first.status_code == 200
        assert second.status_code == 200
        checkpoints = client.get(f"/api/jobs/{job_id}/checkpoints").json()
        assert sum(1 for c in checkpoints if c["payload"].get("phase") == "cancel_requested") == 2

    def test_refuses_cancelling_an_unknown_job(self, client: TestClient) -> None:
        response = client.post("/api/jobs/preview-does-not-exist/cancel")

        assert response.status_code >= 400
