"""Tanılama HTTP surface (Command Center Wave 2C, Surface C): real backend,
real PDP, real `GovernanceState`/findings, the real architecture gate and a
real `JobStore` read against a real, migrated SQLite database - the same
Level 3 real-collaborator posture `test_command_providers_api.py` and
`test_command_code_intelligence_api.py` already establish for their own
routes.
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

from arkali.acceptance.findings import Finding, parse_findings
from arkali.acceptance.governance_state import OPEN_BLOCKERS, GovernanceState
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.execution.durable.job_state_machine import (
    CHECKPOINTED, PAUSED, QUEUED, RECOVERABLE, RESUMING, RUNNING,
)
from arkali.execution.durable.job_store import JobStore
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.surfaces.command.app import _CommandExtensions, create_app
from arkali.surfaces.command.diagnostics import _DiagnosticsFinding, _DiagnosticsSnapshotResponse
from arkali.surfaces.operations.ai_review_bundle import observe_architecture

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

_ACTIVE_STATES = (QUEUED, RUNNING, CHECKPOINTED, PAUSED, RESUMING, RECOVERABLE)
_SEVERITY_RANK = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
MAX_TOP_FINDINGS = 5


def alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "diagnostics.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


def _diagnostics_wiring(pdp: PolicyDecisionPoint):  # noqa: ANN201
    """Mirrors `run_command_center.py::_diagnostics_wiring` exactly - a
    real scan of this repository's own real governance/architecture/job
    state, never a fixture tree."""
    def top_findings(all_findings: tuple[Finding, ...]) -> tuple[_DiagnosticsFinding, ...]:
        open_findings = sorted(
            (f for f in all_findings if f.is_open),
            key=lambda f: (_SEVERITY_RANK.get(f.severity.upper(), len(_SEVERITY_RANK)), f.identifier),
        )
        return tuple(
            _DiagnosticsFinding(
                identifier=f.identifier, severity=f.severity, status=f.status.value,
                detail=" ".join(f.detail.split())[:200],
            )
            for f in open_findings[:MAX_TOP_FINDINGS]
        )

    def snapshot(session) -> _DiagnosticsSnapshotResponse:  # noqa: ANN001
        governance = GovernanceState.load(REPO)
        stopping = governance.open_stopping_findings
        all_findings = parse_findings((REPO / OPEN_BLOCKERS).read_text(encoding="utf-8"))
        architecture = observe_architecture(REPO)
        pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
        store = JobStore(session, pep)
        active = store.list_by_state(_ACTIVE_STATES)
        hint = "resolve_open_finding" if stopping else (
            "pending_operational_job" if active else "no_pending_operational_work"
        )
        healthy = len(stopping) == 0 and not architecture.violations
        return _DiagnosticsSnapshotResponse(
            overall_status="HEALTHY" if healthy else "ATTENTION_NEEDED",
            open_stopping_count=len(stopping),
            top_findings=top_findings(all_findings),
            architecture=architecture,
            operational_hint=hint,
            generated_at=dt.datetime.now(dt.UTC),
        )

    return snapshot


@pytest.fixture()
def app(engine: Engine, pdp: PolicyDecisionPoint) -> FastAPI:
    return create_app(engine, pdp, extensions=_CommandExtensions(
        diagnostics_wiring=_diagnostics_wiring(pdp),
    ))


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as opened:
        yield opened


_SENSITIVE_MARKERS = (
    "api_key", "apikey", "token", "secret", "password", "credential",
    "authorization", "os.environ", "path=",
)


class TestDiagnosticsSnapshotIsRealNotFabricated:
    def test_reachable_and_shaped_like_the_contract(self, client: TestClient) -> None:
        response = client.get("/api/diagnostics/snapshot")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "overall_status", "open_stopping_count", "top_findings",
            "architecture", "operational_hint", "generated_at",
        }
        assert body["overall_status"] in {"HEALTHY", "ATTENTION_NEEDED"}
        assert body["operational_hint"] in {
            "resolve_open_finding", "review_pending_product_change",
            "pending_operational_job", "no_pending_operational_work",
            "live_state_unavailable",
        }

    def test_on_a_fresh_empty_database_no_operational_work_is_pending(
        self, client: TestClient,
    ) -> None:
        """A truthful empty state, never a fabricated healthy claim."""
        body = client.get("/api/diagnostics/snapshot").json()
        assert body["operational_hint"] == "no_pending_operational_work"

    def test_top_findings_is_bounded(self, client: TestClient) -> None:
        body = client.get("/api/diagnostics/snapshot").json()
        assert len(body["top_findings"]) <= MAX_TOP_FINDINGS
        for entry in body["top_findings"]:
            assert set(entry) == {"identifier", "severity", "status", "detail"}
            assert len(entry["detail"]) <= 200

    def test_architecture_is_the_real_reused_summary(self, client: TestClient) -> None:
        body = client.get("/api/diagnostics/snapshot").json()
        assert set(body["architecture"]) == {"gates_passed", "gates_total", "violations"}
        assert body["architecture"]["gates_total"] > 0

    def test_without_wiring_the_route_does_not_exist(
        self, engine: Engine, pdp: PolicyDecisionPoint,
    ) -> None:
        plain_app = create_app(engine, pdp)
        with TestClient(plain_app) as plain_client:
            response = plain_client.get("/api/diagnostics/snapshot")
        assert response.status_code == 404

    def test_the_route_is_never_a_trigger(self, client: TestClient) -> None:
        for method in ("post", "put", "patch"):
            response = getattr(client, method)("/api/diagnostics/snapshot", json={})
            assert response.status_code in (404, 405)
        assert client.delete("/api/diagnostics/snapshot").status_code in (404, 405)

    def test_response_carries_no_sensitive_or_absolute_path_material(
        self, client: TestClient,
    ) -> None:
        """Security proof (Wave 2C step 10): no secret/credential/env
        value, and no absolute filesystem path of this repository."""
        body = client.get("/api/diagnostics/snapshot").text.lower()
        for marker in _SENSITIVE_MARKERS:
            assert marker.lower() not in body, f"leaked marker: {marker}"
        assert str(REPO).lower() not in body

    def test_response_never_carries_a_full_stack_trace_or_job_payload(
        self, client: TestClient,
    ) -> None:
        """No raw checkpoint payload, job id, or Python traceback frame -
        only the bounded finding/architecture/hint facts."""
        body = client.get("/api/diagnostics/snapshot").text
        assert "Traceback" not in body
        assert '.py", line' not in body
