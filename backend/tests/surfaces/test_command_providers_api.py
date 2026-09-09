"""Sağlayıcılar ve Modeller HTTP surface (Command Center Wave 2, Surface A):
real backend, real PDP, real `compose_real_capability_authority`/`host_probe`
probe against this host - the same Level 3 real-collaborator posture
`test_command_factory_history_api.py` already establishes for its own route.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.engineering.localai import host_probe
from arkali.engineering.localai.capability_query import compose_real_capability_authority
from arkali.engineering.localai.ollama_adapter import OllamaAdapter
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.surfaces.command.app import _CommandExtensions, create_app
from arkali.surfaces.command.providers import _ProvidersSnapshotResponse
from arkali.surfaces.operations.contracts import DimensionReading

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture()
def engine(tmp_path: pathlib.Path):  # noqa: ANN201
    built = create_persistence_engine(sqlite_url(tmp_path / "providers.db"))
    yield built
    built.dispose()


@pytest.fixture()
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


def _providers_wiring():  # noqa: ANN201
    """Mirrors `run_command_center.py::_providers_wiring` exactly - a real
    probe against this host's real Ollama runtime, never a fake authority."""
    authority = compose_real_capability_authority(REPO, OllamaAdapter(), "9B")

    def snapshot() -> _ProvidersSnapshotResponse:
        model_id = authority.default_capability_id
        if model_id is None:
            local_runtime = DimensionReading.not_configured("local_runtime", "n/a")
            configured_model = DimensionReading.not_configured("configured_model", "n/a")
        else:
            local_runtime = DimensionReading.real("local_runtime", 1.0, model_id)
            configured_model = DimensionReading.real("configured_model", 1.0, model_id)
        host = host_probe.probe_host()
        accelerator = (
            DimensionReading.real("accelerator", 1.0, host.accelerator_detail)
            if host.accelerator_present
            else DimensionReading.not_configured("accelerator", host.accelerator_detail)
        )
        return _ProvidersSnapshotResponse(
            local_runtime=local_runtime, configured_model=configured_model,
            accelerator=accelerator,
        )

    return snapshot


@pytest.fixture()
def app(engine, pdp: PolicyDecisionPoint) -> FastAPI:  # noqa: ANN001
    return create_app(engine, pdp, extensions=_CommandExtensions(
        providers_wiring=_providers_wiring(),
    ))


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as opened:
        yield opened


_SENSITIVE_MARKERS = (
    "api_key", "apikey", "token", "secret", "password", "credential",
    "authorization", "os.environ", "path=",
)


class TestProvidersSnapshotIsRealNotFabricated:
    def test_reachable_and_shaped_like_the_contract(self, client: TestClient) -> None:
        response = client.get("/api/providers/snapshot")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"local_runtime", "configured_model", "accelerator"}
        for reading in body.values():
            assert set(reading) == {"dimension", "state", "detail", "value"}
            assert reading["state"] in {"PASS", "NOT_CONFIGURED", "NOT_APPLICABLE", "FAIL"}

    def test_without_providers_wiring_the_route_does_not_exist(
        self, engine, pdp: PolicyDecisionPoint,  # noqa: ANN001
    ) -> None:
        plain_app = create_app(engine, pdp)
        with TestClient(plain_app) as plain_client:
            response = plain_client.get("/api/providers/snapshot")
        assert response.status_code == 404

    def test_the_route_is_never_a_trigger(self, client: TestClient) -> None:
        """A real regression control: this read-only surface never accepts a
        mutation - Wave 2 authorized read-only productization only."""
        for method in ("post", "put", "patch"):
            response = getattr(client, method)("/api/providers/snapshot", json={})
            assert response.status_code in (404, 405)
        assert client.delete("/api/providers/snapshot").status_code in (404, 405)

    def test_response_carries_no_sensitive_or_internal_material(
        self, client: TestClient,
    ) -> None:
        """Security proof (Wave 2 step 11): no secret, credential, raw
        environment or filesystem path crosses this boundary - only the
        three declared `DimensionReading` facts."""
        body = client.get("/api/providers/snapshot").text.lower()
        for marker in _SENSITIVE_MARKERS:
            assert marker.lower() not in body, f"leaked marker: {marker}"
        assert str(REPO).lower() not in body
