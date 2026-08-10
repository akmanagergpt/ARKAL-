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
from arkali.surfaces.command.contracts import (
    BACKEND_ONLY,
    BROWSER_SLICE,
    ROUTE_AUDIENCES,
    ErrorResponse,
)
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
    if (
        kind == "object"
        and "properties" not in schema
        and schema.get("additionalProperties", True) is True
    ):
        # A field the backend declares as deliberately opaque - C-19's job
        # payload is the only one - reduces to an open record. Narrow on
        # purpose: an object that constrains its `properties` or its
        # `additionalProperties` is a real structure whose fields must be
        # compared, so it still falls through to the refusal below rather than
        # being flattened into something this control cannot protect.
        #
        # F-0044. The predecessor asked whether the KEY `additionalProperties`
        # was present, which conflated "the key exists" with "the key
        # constrains". `additionalProperties: true` is the explicit spelling of
        # *unconstrained* - exactly the case this branch exists to accept.
        # Pydantic 2.8 rendered `dict[str, object]` as `{type: object}` and
        # Pydantic 2.13 renders the identical declaration as
        # `{type: object, additionalProperties: true}`, so the control began
        # refusing a contract that had not changed. The backend field
        # (`contracts.py: payload: dict[str, object]`) and the frontend types
        # are both untouched since `975b1df`; only the serialiser's spelling
        # moved.
        #
        # STRENGTH IS UNCHANGED for every real constraint: `false` (a closed
        # object) and a schema-valued `additionalProperties` both still fall
        # through to the refusal, as does any object declaring `properties`.
        return "Record<string,unknown>"
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

    def audiences(self, app: FastAPI) -> dict[tuple[str, str], set[str]]:
        """Each published route mapped to the audience tags it declares."""
        return {
            (method.upper(), path): set(operation.get("tags", ()))
            for path, operations in app.openapi()["paths"].items()
            for method, operation in operations.items()
        }

    def test_every_route_declares_exactly_one_known_audience(
        self, app: FastAPI
    ) -> None:
        """FAILS CLOSED on a route nobody classified.

        Replaces `test_the_client_covers_every_route_the_backend_serves`, whose
        premise — every backend route is also a browser-slice route — was true
        for the Phase 5 vertical slice and expired when Package 4 added routes
        for `ARK-REQ-0027`, a requirement owned by `execution.durable` with
        `arch, integ` evidence and no `e2e`. Proven stale before replacement:
        the old assertion failed on exactly the two new routes and on nothing
        else, while every Phase 5 slice route remained covered (F-0037).

        The audience is not a list in this test. It is declared on the router
        and read back off the live document, so a route added later with no tag,
        two tags, or a tag nobody declared fails here instead of choosing its
        own exemption.
        """
        declared = self.audiences(app)
        assert declared, "no route published; this control would be vacuous"
        for route, tags in declared.items():
            known = tags & ROUTE_AUDIENCES
            assert len(known) == 1, (
                f"{route} declares audiences {sorted(tags)}; exactly one of "
                f"{sorted(ROUTE_AUDIENCES)} is required"
            )

    def test_the_client_covers_every_browser_slice_route(
        self, app: FastAPI
    ) -> None:
        """The surviving half of the old control, and still the real one.

        Within the slice an unused route is a gap, not slack. This is what the
        replaced assertion was actually protecting, now stated over the routes
        that genuinely belong to the browser.
        """
        slice_routes = {
            route for route, tags in self.audiences(app).items()
            if BROWSER_SLICE in tags
        }
        assert slice_routes, "no browser-slice route found; control is vacuous"
        assert slice_routes - self.declared_routes() == set()

    def test_the_client_calls_no_backend_only_route(self, app: FastAPI) -> None:
        """STRICTLY STRONGER than what was replaced.

        The old control could not express this at all. A frontend reaching into
        a route declared backend-only is drift in the opposite direction, and it
        would have passed the coverage assertion by making the sets match.
        """
        backend_only = {
            route for route, tags in self.audiences(app).items()
            if BACKEND_ONLY in tags
        }
        assert backend_only, "no backend-only route found; control is vacuous"
        assert backend_only & self.declared_routes() == set(), (
            "the browser client calls a route declared backend-only"
        )

    def test_a_renamed_route_would_be_detected(self, app: FastAPI) -> None:
        """NEGATIVE CONTROL: the path comparison is exact, not a prefix match."""
        published = {
            (method.upper(), path)
            for path, operations in app.openapi()["paths"].items()
            for method in operations
        }
        assert ("GET", "/api/project-registry") not in published
        assert ("GET", "/api/project-registry") not in self.declared_routes()
