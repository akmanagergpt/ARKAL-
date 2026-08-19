"""C-34 composed VDC journey (Phase 25 Package 8): Operations Telemetry +
Computer-Use, proven end to end against real infrastructure - a real
FastAPI application, a real SQLite database migrated by the real Alembic
chain, a real PDP, and a real cross-package integration with the
pre-existing Phase 7 durable-job API.
"""

from __future__ import annotations

import pathlib
import sys
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
from arkali.surfaces.operations.computer_use import authorize_computer_use_action
from arkali.surfaces.operations.file_boundary import read_workspace_file, write_workspace_file
from arkali.surfaces.operations.process_boundary import execute_process
from arkali.surfaces.operations.source_export import export_source
from tests.security.test_protected_core_and_secrets import synthetic_secret

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"


def _alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


def _operations_wiring(pdp: PolicyDecisionPoint, repo_root: pathlib.Path):  # noqa: ANN201
    vocabulary = GraphVocabulary.load(repo_root)
    approval_gate = WorkflowApprovalGate.load(repo_root)

    def job_recovery_factory(session: Session) -> JobRecovery:
        return JobRecovery(session, PolicyEnforcementPoint(pdp, "execution.durable.execution"))

    def executor_factory(session: Session) -> WorkflowExecutor:
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return job_recovery_factory, executor_factory, pdp, host_probe.probe_host


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "journey.db"
    command.upgrade(_alembic_config(path), "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


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


class TestComposedOperationsJourney:
    def test_the_whole_vdc_condition_set_is_real(
        self, client: TestClient, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        # 1. Real-time telemetry starts honest and empty.
        before = client.get("/api/operations/snapshot").json()
        assert before["runtime"]["jobs_queued"]["value"] == 0.0
        assert before["hardware"]["cpu_logical_cores"]["value"] > 0
        assert before["runtime"]["providers"]["state"] == "NOT_CONFIGURED"

        # 2. A real job is submitted through the pre-existing Phase 7 API -
        #    Operations must observe it without touching execution.durable
        #    a second, independent way.
        enqueue = client.post(
            "/api/jobs",
            json={
                "job_id": "JOURNEY-JOB-1", "job_type": "arkali.test.noop",
                "idempotency_key": "journey-key-1", "payload": {},
            },
        )
        assert enqueue.status_code == 202

        after = client.get("/api/operations/snapshot").json()
        assert after["runtime"]["jobs_queued"]["value"] == 1.0

        # 3. Architecture reflects the real, live gate run - 8/8, this
        #    candidate's own work included.
        architecture = client.get("/api/operations/architecture").json()
        assert architecture["gates_passed"] == architecture["gates_total"] == 8

        # 4. CONDITIONAL dimensions are honestly evaluated, never skipped.
        conditional = client.get("/api/operations/conditional/hardware-cost").json()
        assert conditional["cost"]["state"] == "NOT_APPLICABLE"

        # 5. Computer-Use authorization: AUTO for a local process, ASK_USER
        #    for external browsing, DENY for a Stable write - matching
        #    SECURITY_ARCHITECTURE.md's own table exactly, over HTTP.
        run_process = client.post(
            "/api/operations/computer-use/authorize",
            json={"operation_class": "RUN_PROCESS", "trust_tier": "TRUST-1"},
        ).json()
        assert run_process["decision"] == "AUTO"

        browser = client.post(
            "/api/operations/computer-use/authorize",
            json={"operation_class": "BROWSER_EXTERNAL", "trust_tier": "TRUST-1"},
        ).json()
        assert browser["decision"] == "ASK_USER"

        stable_write = client.post(
            "/api/operations/computer-use/authorize",
            json={"operation_class": "WRITE_STABLE_FILE", "trust_tier": "TRUST-1"},
        ).json()
        assert stable_write["decision"] == "DENY"

        # 6. The real execution boundaries - not exposed over HTTP by
        #    design (see docs/contracts/operations_api.md section 3) - are
        #    exercised directly, gated by the identical real PDP decision.
        outcome = execute_process(
            pdp, command=(sys.executable, "-c", "print('journey-ok')"), trust_tier="TRUST-1",
        )
        assert outcome.executed and outcome.exit_code == 0
        assert "journey-ok" in outcome.stdout

        write_outcome = write_workspace_file(
            pdp, root=tmp_path, relative="journey.txt", payload=b"real file",
            trust_tier="TRUST-1",
        )
        assert write_outcome.executed
        read_outcome = read_workspace_file(
            pdp, root=tmp_path, relative="journey.txt", trust_tier="TRUST-1",
        )
        assert read_outcome.content == b"real file"

        # 7. Source Intelligence Export redacts a real secret in a real
        #    file, end to end.
        secret = synthetic_secret("openai")
        (tmp_path / "config.py").write_text(f"KEY = '{secret}'\n", encoding="utf-8")
        export = export_source(pdp, root=tmp_path, trust_tier="TRUST-1")
        exported_config = next(f for f in export.files if f.relative_path == "config.py")
        assert secret not in exported_config.content
        assert exported_config.redacted is True

        # 8. No invented evidence anywhere in this journey: providers/agents/
        #    workers stayed honestly NOT_CONFIGURED throughout, never
        #    reported as PASS despite the real activity above.
        final = client.get("/api/operations/snapshot").json()
        assert final["runtime"]["providers"]["state"] == "NOT_CONFIGURED"
        assert final["runtime"]["agents"]["state"] == "NOT_CONFIGURED"
        assert final["runtime"]["workers"]["state"] == "NOT_CONFIGURED"
