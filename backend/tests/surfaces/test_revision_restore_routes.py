""""Bu sürüme geri dön" HTTP surface (Managed Product Revision History +
Restore-as-New Convergence): `POST /api/projects/{project_id}/revisions/
{revision_id}/restore` shares the SAME `managed_product.change`
job/idempotency slot "Değişikliği Başlat" already uses -- proven here at
the HTTP layer, not just unit level (`test_revision_restore.py` already
covers `prepare_restore`/`promote_modification` directly).
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.surfaces.command.app import _CommandExtensions, create_app
from arkali.surfaces.command.product_change_bridge import _ProductChangeWiring

REPO = pathlib.Path(__file__).resolve().parents[3]


class _StubPromoter:
    """Never exercised by these tests — restore's own promotion path is
    covered directly, over real persistence, by `test_revision_restore.
    py::TestRestorePromotion`. This double exists only so `_CommandExtensions
    .product_change` is not `None`, the same real gate that includes the
    restore route in the app at all."""

    def promote(self, project_id: str, ready: dict) -> dict:  # pragma: no cover
        raise AssertionError("not exercised by these HTTP-layer tests")


@pytest.fixture()
def command_center_db(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "command_center.db"
    config = Config(str(REPO / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def command_center_engine(command_center_db: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(command_center_db))
    yield built
    built.dispose()


@pytest.fixture()
def http_app(command_center_engine: Engine) -> FastAPI:
    with unit_of_work(create_session_factory(command_center_engine)) as session:
        registry = ProjectRegistry(session)
        registry.create_project("prj-restore-http", "Restore HTTP Product")
        registry.create_revision("prj-restore-http", "prj-restore-http-r1")
        registry.create_revision("prj-restore-http", "prj-restore-http-r2")

        registry.create_project("prj-restore-http-other", "Other Product")
        registry.create_revision("prj-restore-http-other", "prj-restore-http-other-r1")

    pdp = PolicyDecisionPoint.load(REPO)
    return create_app(
        command_center_engine, pdp,
        extensions=_CommandExtensions(product_change=_ProductChangeWiring(promoter=_StubPromoter())),
    )


@pytest.fixture()
def http_client(http_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(http_app) as opened:
        yield opened


class TestStartRestoreHttpRoute:
    def test_start_restore_reaches_the_same_job_type_change_uses(self, http_client: TestClient) -> None:
        response = http_client.post(
            "/api/projects/prj-restore-http/revisions/prj-restore-http-r1/restore",
        )
        assert response.status_code == 202
        body = response.json()
        assert body["job_type"] == "managed_product.change"
        assert body["idempotency_key"] == "prj-restore-http"
        assert body["job_id"] == "change-prj-restore-http"

    def test_restore_and_change_share_the_same_per_project_slot(self, http_client: TestClient) -> None:
        """A project has exactly one active change-or-restore proposal —
        starting a restore then a natural-language change (or vice versa)
        rediscovers the SAME job, never a second, competing one."""
        restore_started = http_client.post(
            "/api/projects/prj-restore-http/revisions/prj-restore-http-r1/restore",
        ).json()
        change_started = http_client.post(
            "/api/projects/prj-restore-http/changes", json={"request_text": "anything"},
        ).json()
        assert restore_started["job_id"] == change_started["job_id"]

    def test_double_restore_returns_the_same_active_job(self, http_client: TestClient) -> None:
        first = http_client.post(
            "/api/projects/prj-restore-http/revisions/prj-restore-http-r1/restore",
        ).json()
        second = http_client.post(
            "/api/projects/prj-restore-http/revisions/prj-restore-http-r1/restore",
        ).json()
        assert first["job_id"] == second["job_id"]

    def test_find_change_rediscovers_a_restore_started_job(self, http_client: TestClient) -> None:
        """`GET /projects/{id}/changes` (unchanged) is also the real
        refresh-recovery counterpart for a restore, since both share one
        job slot."""
        started = http_client.post(
            "/api/projects/prj-restore-http/revisions/prj-restore-http-r2/restore",
        ).json()
        found = http_client.get("/api/projects/prj-restore-http/changes").json()
        assert found is not None
        assert found["job_id"] == started["job_id"]

    def test_restore_targeting_a_revision_of_a_different_project_is_accepted_at_submission(
        self, http_client: TestClient,
    ) -> None:
        """The submission route is deliberately payload-opaque (identical
        reasoning to `start_change`'s own `request_text`) — the REAL
        `UnknownSourceBasisRevisionError` refusal happens inside the
        worker (`prepare_restore`, proven by `test_revision_restore.py`),
        never re-validated at the route layer, matching how an invalid
        `request_text` is likewise never pre-validated here either."""
        response = http_client.post(
            "/api/projects/prj-restore-http/revisions/prj-restore-http-other-r1/restore",
        )
        assert response.status_code == 202
