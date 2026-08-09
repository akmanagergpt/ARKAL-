"""Backend/frontend contract-drift control.

THE PROBLEM THIS SOLVES. The frontend declares the shape of every message it
exchanges with `surfaces.command`. Nothing in either toolchain connects those
declarations to the backend's actual contract: rename `lifecycle_state` to
`state` in a Pydantic model and Python stays green, TypeScript stays green, the
Vite build stays green, and the interface silently renders `undefined` in a
browser nobody is watching.

HOW IT IS DETECTED. The expected shapes are derived from the *running
application* - the OpenAPI document a real `create_app` produces, and the
Pydantic model the refusal path actually serialises - and compared field by
field, and type by type, against the interfaces declared in
`frontend/src/api/contracts.ts`. Route templates are compared the same way,
against the paths FastAPI registered.

WHY NOT A NAME OR STRING CHECK. Asserting that a file mentions `project_id`
proves nothing: it stays true after the backend stops sending it. The comparison
is against generated truth, so it cannot survive a rename on either side.
"""

from __future__ import annotations

import pathlib
import re
from typing import Any, Final

import pytest
from fastapi import FastAPI
from pydantic import BaseModel

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.surfaces.command import contracts
from arkali.surfaces.command.contracts import ErrorResponse
from arkali.surfaces.command.app import create_app
from tests.structural.typescript_reader import (
    FRONTEND_SRC,
    REPO,
    interfaces_of,
    read,
    strip_comments,
)

CONTRACTS_TS: Final[pathlib.Path] = FRONTEND_SRC / "api" / "contracts.ts"
CLIENT_TS: Final[pathlib.Path] = FRONTEND_SRC / "api" / "client.ts"

#: `{ method: 'GET', path: '/api/health' }` in the client's ENDPOINTS table.
_ENDPOINT = re.compile(r"method:\s*'(?P<method>\w+)',\s*path:\s*'(?P<path>[^']+)'")


@pytest.fixture(scope="module")
def app(tmp_path_factory: pytest.TempPathFactory) -> FastAPI:
    """A real application, so the contract is generated and never transcribed."""
    database = tmp_path_factory.mktemp("contract") / "drift.db"
    engine = create_persistence_engine(sqlite_url(database))
    return create_app(engine, PolicyDecisionPoint.load(REPO))


def canonical(schema: dict[str, Any]) -> str:
    """Reduce a JSON-Schema fragment to the TypeScript type it implies.

    Deliberately narrow. Anything this cannot reduce raises, because a contract
    the control cannot compare is a contract it cannot protect, and reporting
    success in that case would be the failure mode the module exists to prevent.
    """
    if "$ref" in schema:
        return str(schema["$ref"]).rsplit("/", 1)[-1]
    if "anyOf" in schema:
        options = [option for option in schema["anyOf"] if option.get("type") != "null"]
        nullable = len(options) != len(schema["anyOf"])
        if len(options) != 1:
            raise AssertionError(f"unsupported union in contract schema: {schema}")
        return canonical(options[0]) + ("|null" if nullable else "")
    kind = schema.get("type")
    if kind == "array":
        return canonical(schema["items"]) + "[]"
    if kind == "string":
        return "string"
    if kind in {"integer", "number"}:
        return "number"
    if kind == "boolean":
        return "boolean"
    raise AssertionError(f"unsupported contract schema fragment: {schema}")


def surface_contract_names() -> frozenset[str]:
    """The models `surfaces.command` declares, so framework schemas are excluded.

    FastAPI publishes `HTTPValidationError` and `ValidationError` of its own.
    They are the framework's contract, not this surface's, and the frontend does
    not declare them.
    """
    return frozenset(
        name
        for name, value in vars(contracts).items()
        if isinstance(value, type) and issubclass(value, BaseModel)
        and value.__module__ == contracts.__name__
    )


def backend_shapes(app: FastAPI) -> dict[str, dict[str, str]]:
    """Every schema this surface declares, plus the refusal envelope.

    Read from the live OpenAPI document, so the comparison is against what the
    application actually publishes. `ErrorResponse` is not a declared response
    model - it is dumped into an `HTTPException` detail - so it comes from the
    Pydantic model the refusal path actually serialises.
    """
    published = dict(app.openapi()["components"]["schemas"])
    declared = surface_contract_names()
    schemas = {name: published[name] for name in published if name in declared}
    schemas["ErrorResponse"] = ErrorResponse.model_json_schema()
    return {
        name: {
            field: canonical(fragment)
            for field, fragment in schema.get("properties", {}).items()
        }
        for name, schema in schemas.items()
    }


class TestTransportTypesMatchTheBackend:
    def test_every_declared_interface_names_a_real_backend_schema(
        self, app: FastAPI
    ) -> None:
        unknown = set(interfaces_of(CONTRACTS_TS)) - set(backend_shapes(app))
        assert unknown == set(), (
            f"the frontend declares transport types the backend does not publish: "
            f"{sorted(unknown)}. A removed or renamed schema must not survive here."
        )

    def test_field_names_and_types_agree_field_by_field(self, app: FastAPI) -> None:
        """The control: a rename or a type change on either side fails here."""
        expected = backend_shapes(app)
        for name, declared in interfaces_of(CONTRACTS_TS).items():
            assert declared == expected[name], (
                f"{name} has drifted. backend={expected[name]} frontend={declared}"
            )

    def test_the_slice_covers_every_shape_it_exchanges(self, app: FastAPI) -> None:
        """Nothing the UI actually sends or receives may go undeclared."""
        declared = set(interfaces_of(CONTRACTS_TS))
        exchanged = {
            "CreateProjectRequest",
            "CreateRevisionRequest",
            "TransitionRequest",
            "ProjectResponse",
            "ProjectDetailResponse",
            "ProjectListResponse",
            "RevisionResponse",
            "HealthResponse",
            "LifecycleMachineResponse",
            "ErrorResponse",
        }
        assert exchanged <= declared

    def test_a_renamed_backend_field_would_be_detected(self, app: FastAPI) -> None:
        """NEGATIVE CONTROL: prove the comparison is not vacuous.

        Rename a field in a copy of the derived truth and require the same
        comparison to reject it. Without this, a control that silently compared
        two empty dictionaries would pass forever.
        """
        expected = backend_shapes(app)
        mutated = dict(expected["ProjectResponse"])
        mutated["state"] = mutated.pop("lifecycle_state")
        assert mutated != interfaces_of(CONTRACTS_TS)["ProjectResponse"]

    def test_a_changed_backend_type_would_be_detected(self, app: FastAPI) -> None:
        """NEGATIVE CONTROL: nullability is part of the contract, not a detail."""
        expected = dict(backend_shapes(app)["RevisionResponse"])
        expected["provenance_ref"] = "string"
        assert expected != interfaces_of(CONTRACTS_TS)["RevisionResponse"]


class TestRoutesMatchTheBackend:
    def declared_routes(self) -> set[tuple[str, str]]:
        found = {
            (match.group("method"), match.group("path"))
            for match in _ENDPOINT.finditer(strip_comments(read(CLIENT_TS)))
        }
        assert found, "the client declares no endpoint table to compare"
        return found

    def test_every_route_the_client_calls_exists_on_the_backend(
        self, app: FastAPI
    ) -> None:
        published = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
        }
        missing = self.declared_routes() - published
        assert missing == set(), (
            f"the frontend calls routes the backend does not serve: {sorted(missing)}"
        )

    def test_the_client_covers_every_route_the_backend_serves(
        self, app: FastAPI
    ) -> None:
        """The slice is meant to be complete: an unused route is a gap, not slack."""
        published = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
        }
        assert published - self.declared_routes() == set()

    def test_a_renamed_route_would_be_detected(self, app: FastAPI) -> None:
        """NEGATIVE CONTROL: the path comparison is exact, not a prefix match."""
        published = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
        }
        assert ("GET", "/api/project-registry") not in published
        assert ("GET", "/api/project-registry") not in self.declared_routes()
