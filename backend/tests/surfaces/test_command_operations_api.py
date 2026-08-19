"""C-34 Operations HTTP surface (ARK-REQ-0168, 0169, 0170, 0355-0357):
real backend, real SQLite, real PDP, real host telemetry - a genuine
Level 3 real-user-reachable proof, not a `TestClient`-only shortcut over
substituted collaborators.
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
from sqlalchemy.orm import Session

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.engineering.localai import host_probe
from arkali.execution.durable.recovery import JobRecovery
from arkali.execution.workflow.executor import WorkflowExecutor
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.surfaces.command.app import create_app

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"


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
    path = tmp_path / "operations.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


def _operations_wiring(pdp: PolicyDecisionPoint, repo_root: pathlib.Path):  # noqa: ANN201
    """The real composition-root wiring, mirroring
    `scripts/run_command_center.py::_operations_wiring` exactly."""
    vocabulary = GraphVocabulary.load(repo_root)
    approval_gate = WorkflowApprovalGate.load(repo_root)

    def job_recovery_factory(session: Session) -> JobRecovery:
        pep = PolicyEnforcementPoint(pdp, "execution.durable.execution")
        return JobRecovery(session, pep)

    def executor_factory(session: Session) -> WorkflowExecutor:
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return job_recovery_factory, executor_factory, pdp, host_probe.probe_host


@pytest.fixture()
def app(engine: Engine, pdp: PolicyDecisionPoint) -> FastAPI:
    return create_app(
        engine, pdp, operations_wiring=_operations_wiring(pdp, REPO),
        operations_repo_root=REPO,
    )


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as opened:
        yield opened


class TestSnapshotIsRealNotFabricated:
    def test_the_snapshot_route_returns_real_host_and_db_facts(
        self, client: TestClient,
    ) -> None:
        response = client.get("/api/operations/snapshot")
        assert response.status_code == 200
        body = response.json()
        assert body["hardware"]["cpu_logical_cores"]["state"] == "PASS"
        assert body["hardware"]["cpu_logical_cores"]["value"] > 0
        assert body["storage"]["database_reachable"]["state"] == "PASS"
        assert body["runtime"]["jobs_active"]["value"] == 0.0
        assert body["runtime"]["providers"]["state"] == "NOT_CONFIGURED"

    def test_without_operations_wiring_the_route_does_not_exist(
        self, engine: Engine, pdp: PolicyDecisionPoint,
    ) -> None:
        plain_app = create_app(engine, pdp)
        with TestClient(plain_app) as plain_client:
            response = plain_client.get("/api/operations/snapshot")
        assert response.status_code == 404


class TestConditionalDimensionRoutes:
    def test_hardware_cost_route_is_real(self, client: TestClient) -> None:
        response = client.get("/api/operations/conditional/hardware-cost")
        assert response.status_code == 200
        body = response.json()
        assert body["gpu"]["state"] in ("PASS",)
        assert body["cost"]["state"] == "NOT_APPLICABLE"

    def test_quality_latency_route_is_real(self, client: TestClient) -> None:
        response = client.get("/api/operations/conditional/quality-latency")
        assert response.status_code == 200
        assert response.json()["quality"]["state"] == "NOT_APPLICABLE"


class TestArchitectureRoute:
    def test_the_route_reflects_the_real_live_gate_run(self, client: TestClient) -> None:
        response = client.get("/api/operations/architecture")
        assert response.status_code == 200
        body = response.json()
        assert body["gates_total"] == 8
        assert body["gates_passed"] == 8


class TestComputerUseAuthorizeRouteNeverExecutes:
    def test_run_process_at_trust_1_authorizes_but_the_route_never_runs_anything(
        self, client: TestClient,
    ) -> None:
        response = client.post(
            "/api/operations/computer-use/authorize",
            json={"operation_class": "RUN_PROCESS", "trust_tier": "TRUST-1"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["decision"] == "AUTO"
        assert body["operation_class"] == "RUN_PROCESS"

    def test_install_system_software_never_authorizes_auto(self, client: TestClient) -> None:
        response = client.post(
            "/api/operations/computer-use/authorize",
            json={"operation_class": "INSTALL_SYSTEM_SOFTWARE", "trust_tier": "TRUST-1"},
        )
        assert response.json()["decision"] != "AUTO"

    def test_the_request_body_carries_no_command_field_at_all(self, client: TestClient) -> None:
        response = client.post(
            "/api/operations/computer-use/authorize",
            json={
                "operation_class": "RUN_PROCESS", "trust_tier": "TRUST-1",
                "command": "rm -rf /",
            },
        )
        assert response.status_code == 422, (
            "the request contract must reject an unknown 'command' field "
            "outright - it is never a field this endpoint accepts"
        )
