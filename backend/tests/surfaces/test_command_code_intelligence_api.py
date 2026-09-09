"""Kod Zekâsı HTTP surface (Command Center Wave 2B, Surface B): real
backend, real PDP, a real `PythonGraphBuilder` scan of `backend/arkali` and
the real architecture gate - the same Level 3 real-collaborator posture
`test_command_providers_api.py` already establishes for its own route.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.surfaces.command.app import _CommandExtensions, create_app
from arkali.surfaces.command.code_intelligence import (
    MAX_TOP_DEPENDENCIES,
    _observe_code_intelligence,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND_ARKALI = REPO / "backend" / "arkali"


@pytest.fixture()
def engine(tmp_path: pathlib.Path):  # noqa: ANN201
    built = create_persistence_engine(sqlite_url(tmp_path / "codeintel.db"))
    yield built
    built.dispose()


@pytest.fixture()
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


def _code_intelligence_wiring():  # noqa: ANN201
    """Mirrors `run_command_center.py::_code_intelligence_wiring` exactly -
    a real scan of this repository's own real `backend/arkali`, never a
    fixture tree."""
    def snapshot():
        return _observe_code_intelligence(BACKEND_ARKALI, REPO)

    return snapshot


@pytest.fixture()
def app(engine, pdp: PolicyDecisionPoint) -> FastAPI:  # noqa: ANN001
    return create_app(engine, pdp, extensions=_CommandExtensions(
        code_intelligence_wiring=_code_intelligence_wiring(),
    ))


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as opened:
        yield opened


_SENSITIVE_MARKERS = (
    "api_key", "apikey", "token", "secret", "password", "credential",
    "authorization", "os.environ", "path=",
)


class TestCodeIntelligenceSnapshotIsRealNotFabricated:
    def test_reachable_and_shaped_like_the_contract(self, client: TestClient) -> None:
        response = client.get("/api/code-intelligence/snapshot")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"module_count", "top_dependencies", "architecture"}
        assert body["module_count"] > 0
        assert set(body["architecture"]) == {"gates_passed", "gates_total", "violations"}

    def test_top_dependencies_is_bounded(self, client: TestClient) -> None:
        """The whole point of this surface being a summary, not a graph
        dump: never an unbounded ranking."""
        body = client.get("/api/code-intelligence/snapshot").json()
        assert len(body["top_dependencies"]) <= MAX_TOP_DEPENDENCIES
        for entry in body["top_dependencies"]:
            assert set(entry) == {"area", "dependent_count"}
            assert entry["dependent_count"] > 0
            # Every reported area is an internal arkali bounded context, an
            # external stdlib/third-party import never leaks in here.
            assert "/" not in entry["area"]
            assert "\\" not in entry["area"]

    def test_without_wiring_the_route_does_not_exist(
        self, engine, pdp: PolicyDecisionPoint,  # noqa: ANN001
    ) -> None:
        plain_app = create_app(engine, pdp)
        with TestClient(plain_app) as plain_client:
            response = plain_client.get("/api/code-intelligence/snapshot")
        assert response.status_code == 404

    def test_the_route_is_never_a_trigger(self, client: TestClient) -> None:
        for method in ("post", "put", "patch"):
            response = getattr(client, method)("/api/code-intelligence/snapshot", json={})
            assert response.status_code in (404, 405)
        assert client.delete("/api/code-intelligence/snapshot").status_code in (404, 405)

    def test_response_carries_no_sensitive_or_absolute_path_material(
        self, client: TestClient,
    ) -> None:
        """Security proof (Wave 2B step 6): no secret/credential/env value,
        and no absolute filesystem path - every path in this repository's
        own real scan is relative to `backend/arkali`."""
        body = client.get("/api/code-intelligence/snapshot").text.lower()
        for marker in _SENSITIVE_MARKERS:
            assert marker.lower() not in body, f"leaked marker: {marker}"
        assert str(REPO).lower() not in body
        assert str(BACKEND_ARKALI).lower() not in body

    def test_response_carries_no_raw_graph_or_symbol_names(
        self, client: TestClient,
    ) -> None:
        """Never the raw node/edge list or a per-file/per-symbol identifier -
        only the bounded area-level aggregate and the module count."""
        body = client.get("/api/code-intelligence/snapshot").json()
        rendered = str(body)
        assert "::" not in rendered  # PythonGraphBuilder's own symbol-node separator
        assert ".py" not in rendered  # no per-file identifier of any kind
