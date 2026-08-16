"""C-20 workflow HTTP surface, over a real application (Phase 17 Package 6).

REAL INFRASTRUCTURE ONLY. A real migrated SQLite file, a real PDP, a real
`GraphVocabulary`/`WorkflowApprovalGate`, and the real `WorkflowGraphStore`/
`WorkflowExecutor` behind the composition-root wiring `create_app` accepts.

THIS TEST FILE IS THE COMPOSITION ROOT `workflow.py` deliberately does not
contain. It imports `execution.workflow` directly to build the three factory
callables `create_app(..., workflow_wiring=...)` takes - legitimate here
because `backend/tests/` is outside the measured architecture graph, exactly
as `scripts/run_command_center.py` will be for the real launcher.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.workflow_approval import APPROVED, WorkflowApprovalGate
from arkali.execution.workflow.graph_model import WorkflowEdge, WorkflowGraphDocument, WorkflowNode
from arkali.execution.workflow.graph_store import WorkflowGraphStore
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from arkali.execution.workflow.executor import WorkflowExecutor
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.surfaces.command.app import create_app

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

TRIGGER_DATA_GRAPH: dict[str, Any] = {
    "nodes": [
        {"node_id": "n-trigger", "kind": "trigger", "label": "Start"},
        {"node_id": "n-data", "kind": "data", "label": "Transform"},
    ],
    "edges": [{"edge_id": "e-1", "source_node_id": "n-trigger", "target_node_id": "n-data"}],
}


def _migrated(path: pathlib.Path) -> None:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")


def _wiring(pdp: PolicyDecisionPoint, vocabulary: GraphVocabulary, approval_gate: WorkflowApprovalGate):
    def document_builder(
        workflow_id: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> WorkflowGraphDocument:
        return WorkflowGraphDocument.build(
            vocabulary,
            workflow_id,
            nodes=[WorkflowNode(**n) for n in nodes],
            edges=[WorkflowEdge(**e) for e in edges],
        )

    def graph_store_factory(session: Session) -> WorkflowGraphStore:
        pep = PolicyEnforcementPoint(pdp, "execution.workflow.graph_store")
        return WorkflowGraphStore(session, pep, vocabulary)

    def executor_factory(session: Session) -> WorkflowExecutor:
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return document_builder, graph_store_factory, executor_factory


@pytest.fixture()
def engine(tmp_path: pathlib.Path) -> Iterator[Engine]:
    database = tmp_path / "workflow_api.db"
    _migrated(database)
    built = create_persistence_engine(sqlite_url(database))
    try:
        yield built
    finally:
        built.dispose()


@pytest.fixture()
def app(engine: Engine) -> FastAPI:
    pdp = PolicyDecisionPoint.load(REPO)
    vocabulary = GraphVocabulary.load(REPO)
    approval_gate = WorkflowApprovalGate.load(REPO)
    return create_app(engine, pdp, workflow_wiring=_wiring(pdp, vocabulary, approval_gate))


@pytest.fixture()
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestPublishAndReadRevisions:
    def test_publish_derives_revision_one_and_reads_back(self, client: TestClient) -> None:
        response = client.post(
            "/api/workflows/wf-1/revisions",
            json={**TRIGGER_DATA_GRAPH, "semver_bump": "PATCH"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["revision_number"] == 1
        assert body["semver"] == "1.0.0"
        assert body["revision_hash"].startswith("sha256:")
        assert {n["node_id"] for n in body["nodes"]} == {"n-trigger", "n-data"}

        latest = client.get("/api/workflows/wf-1")
        assert latest.status_code == 200
        assert latest.json()["revision_number"] == 1

        specific = client.get("/api/workflows/wf-1/revisions/1")
        assert specific.status_code == 200
        assert specific.json()["revision_hash"] == body["revision_hash"]

        history = client.get("/api/workflows/wf-1/revisions")
        assert history.status_code == 200
        assert [r["revision_number"] for r in history.json()["revisions"]] == [1]

    def test_a_second_publish_derives_revision_two(self, client: TestClient) -> None:
        client.post("/api/workflows/wf-2/revisions", json=TRIGGER_DATA_GRAPH)
        second = client.post(
            "/api/workflows/wf-2/revisions",
            json={**TRIGGER_DATA_GRAPH, "semver_bump": "MINOR"},
        )
        assert second.status_code == 201
        assert second.json()["revision_number"] == 2
        assert second.json()["semver"] == "1.1.0"

    def test_unknown_workflow_is_404(self, client: TestClient) -> None:
        response = client.get("/api/workflows/ghost")
        assert response.status_code == 404

    def test_an_invalid_graph_is_refused_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/workflows/wf-invalid/revisions",
            json={"nodes": [{"node_id": "n-data", "kind": "data"}], "edges": []},
        )
        assert response.status_code == 400


class TestExecutions:
    def test_start_runs_to_completion(self, client: TestClient) -> None:
        client.post("/api/workflows/wf-exec/revisions", json=TRIGGER_DATA_GRAPH)
        response = client.post(
            "/api/workflows/wf-exec/executions", json={"execution_id": "exec-api-1"}
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["lifecycle_state"] == "SUCCEEDED"
        assert {e["node_id"] for e in body["evidence"]} == {"n-trigger", "n-data"}

        fetched = client.get("/api/workflows/wf-exec/executions/exec-api-1")
        assert fetched.status_code == 200
        assert fetched.json()["lifecycle_state"] == "SUCCEEDED"

    def test_unknown_execution_is_404(self, client: TestClient) -> None:
        response = client.get("/api/workflows/wf-exec/executions/ghost")
        assert response.status_code == 404

    def test_wait_pauses_and_signal_resumes(self, client: TestClient) -> None:
        graph = {
            "nodes": [
                {"node_id": "n-trigger", "kind": "trigger"},
                {"node_id": "n-wait", "kind": "logic", "control_construct": "WAIT"},
                {"node_id": "n-after", "kind": "data"},
            ],
            "edges": [
                {"edge_id": "e-1", "source_node_id": "n-trigger", "target_node_id": "n-wait"},
                {"edge_id": "e-2", "source_node_id": "n-wait", "target_node_id": "n-after"},
            ],
        }
        client.post("/api/workflows/wf-wait/revisions", json=graph)
        started = client.post(
            "/api/workflows/wf-wait/executions", json={"execution_id": "exec-api-wait"}
        )
        assert started.json()["lifecycle_state"] == "WAITING_SIGNAL"

        resumed = client.post("/api/workflows/wf-wait/executions/exec-api-wait/signal")
        assert resumed.status_code == 200
        assert resumed.json()["lifecycle_state"] == "SUCCEEDED"

    def test_human_approval_pauses_and_approve_completes(self, client: TestClient) -> None:
        graph = {
            "nodes": [
                {"node_id": "n-trigger", "kind": "trigger"},
                {"node_id": "n-approval", "kind": "logic", "control_construct": "HUMAN APPROVAL"},
                {"node_id": "n-after", "kind": "data"},
            ],
            "edges": [
                {"edge_id": "e-1", "source_node_id": "n-trigger", "target_node_id": "n-approval"},
                {"edge_id": "e-2", "source_node_id": "n-approval", "target_node_id": "n-after"},
            ],
        }
        client.post("/api/workflows/wf-approve/revisions", json=graph)
        started = client.post(
            "/api/workflows/wf-approve/executions", json={"execution_id": "exec-api-approve"}
        )
        body = started.json()
        assert body["lifecycle_state"] == "WAITING_APPROVAL"
        bound = body["bound_revision_hash"]

        approved = client.post(
            "/api/workflows/wf-approve/executions/exec-api-approve/approve",
            json={
                "node_id": "n-approval", "actor": "human",
                "decision": APPROVED, "approved_revision_hash": bound,
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["lifecycle_state"] == "SUCCEEDED"

    def test_the_workflow_actor_is_refused_403(self, client: TestClient) -> None:
        graph = {
            "nodes": [
                {"node_id": "n-trigger", "kind": "trigger"},
                {"node_id": "n-approval", "kind": "logic", "control_construct": "HUMAN APPROVAL"},
            ],
            "edges": [
                {"edge_id": "e-1", "source_node_id": "n-trigger", "target_node_id": "n-approval"},
            ],
        }
        client.post("/api/workflows/wf-approve-2/revisions", json=graph)
        started = client.post(
            "/api/workflows/wf-approve-2/executions", json={"execution_id": "exec-api-approve-2"}
        )
        bound = started.json()["bound_revision_hash"]
        response = client.post(
            "/api/workflows/wf-approve-2/executions/exec-api-approve-2/approve",
            json={
                "node_id": "n-approval", "actor": "workflow",
                "decision": APPROVED, "approved_revision_hash": bound,
            },
        )
        assert response.status_code == 403


class TestRouteAudienceIsBrowserSlice:
    def test_every_workflow_route_is_browser_slice(self, app: FastAPI) -> None:
        """Package 6 tagged these `backend-only` because no frontend called
        them yet. Package 7's Studio UI calls every one of them through
        `ArkaliApiClient`, added in the same commit as this flip -
        `test_contract_drift.py` enforces that a `browser-slice` route is
        never left uncalled and a `backend-only` route is never called."""
        schema = app.openapi()
        workflow_routes = {
            path: operations
            for path, operations in schema["paths"].items()
            if path.startswith("/api/workflows")
        }
        assert workflow_routes, "no workflow route published; this control would be vacuous"
        for path, operations in workflow_routes.items():
            for method, operation in operations.items():
                assert operation.get("tags") == ["browser-slice"], (
                    f"{method.upper()} {path} is not browser-slice"
                )
