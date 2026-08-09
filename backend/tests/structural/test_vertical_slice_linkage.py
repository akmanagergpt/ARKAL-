"""ARK-REQ-0229 — the vertical slice is linked, not merely populated.

WHAT THE REQUIREMENT SAYS. `REQUIREMENT_REGISTER.md` row ARK-REQ-0229, sourced
to the Build Protocol section "Vertical slices": for every capability with a
production-visible state, complete it end to end - *data + domain + service +
API + frontend + policy/security + audit + tests + evidence*. Owner:
`control.architecture`. Verified by `arch` and `e2e`.

WHY THE OBVIOUS CONTROL IS WORTHLESS. Nine assertions that nine files exist is a
control that passes on nine empty files, and keeps passing after the API stops
calling the registry, after the registry grows its own transition table, after
the persistence layer is swapped for a dictionary. Every one of those is exactly
the defect the requirement exists to prevent, and file presence detects none of
them.

WHAT IS PROVEN HERE INSTEAD. Two chains, each link asserted against the thing it
links to:

    frontend entry -> typed API client -> surfaces.command routes ->
    ProjectRegistry -> Project state machine -> persistence session ->
    a real database file

    an API operation -> PEP -> PDP -> audit trail

Structural links are read from source with `ast` and the TypeScript reader; the
runtime links are proven by driving a real request through a real application
onto a real SQLite file and then reading the row back through a *separate*
engine, which no in-memory stand-in can survive.

WHAT THIS DOES NOT CLAIM. The `e2e` tier for this requirement is a real browser
journey. There is no browser runtime here; T10 is NOT_CONFIGURED and the
component tests under `frontend/tests` are not a substitute for it. This module
proves the `arch` obligation and the linkage; the browser journey is owed
separately, and the requirement is not discharged by this package in any case -
discharge belongs to the Phase 5 traceability record and gate.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator
from typing import Final

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.registry.project.project_state_machine import DEFINITION
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.surfaces.command.app import ACTOR, create_app
from tests.structural.typescript_reader import (
    FRONTEND_SRC,
    FRONTEND_TESTS,
    REPO,
    imports_of,
    read,
    reachable_from,
    resolve,
    strip_comments,
)

BACKEND: Final[pathlib.Path] = REPO / "backend"
APP_SOURCE: Final[pathlib.Path] = BACKEND / "arkali/surfaces/command/app.py"
REGISTRY_SOURCE: Final[pathlib.Path] = (
    BACKEND / "arkali/control/registry/project/registry.py"
)

ENTRY: Final[pathlib.Path] = FRONTEND_SRC / "main.tsx"
API_CLIENT: Final[pathlib.Path] = FRONTEND_SRC / "api" / "client.ts"
REGISTRY_PAGE: Final[pathlib.Path] = (
    FRONTEND_SRC / "features" / "projects" / "ProjectRegistryPage.tsx"
)

#: The operations the slice must actually drive, not merely be able to.
SLICE_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"listProjects", "createProject", "getProject", "transitionProject", "createRevision"}
)


def module_of(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def called_names(tree: ast.AST) -> set[str]:
    """Every plain and attribute call target in a tree."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def imported_modules(tree: ast.AST) -> set[str]:
    return {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }


# ---------------------------------------------------------------------------
# Chain 1, links 1-2: frontend -> typed API client -> surfaces.command routes
# ---------------------------------------------------------------------------


class TestFrontendReachesTheApiClient:
    def test_the_application_entry_reaches_the_typed_client(self) -> None:
        reachable = reachable_from(ENTRY)
        assert API_CLIENT in reachable, (
            "the frontend entry point does not transitively import the API client: "
            "a frontend that never calls the API is not a slice."
        )

    def test_every_import_in_the_reachable_graph_resolves(self) -> None:
        """A specifier that resolves to nothing means the graph above is partial."""
        for module in reachable_from(ENTRY):
            for specifier in imports_of(module):
                if specifier.startswith(("@/", ".")):
                    assert resolve(specifier, module) is not None, (
                        f"{module.name} imports {specifier!r}, which resolves to no file"
                    )

    def test_the_page_actually_drives_the_slice_operations(self) -> None:
        """Reachability is not use. Each operation must really be invoked.

        THE CLIENT ITSELF IS EXCLUDED. Its own method declarations read exactly
        like calls to them, so searching the whole graph would find every
        operation in the module that defines them and pass no matter what the
        interface does. That is the vacuous version of this check, and it was
        the first thing written here; a mutation that removed the transition
        call from the page did not fail it. The client is skipped so a call must
        come from a consumer.

        Which consumer does not matter - the calls live in the page's state hook
        rather than in the components - so the rest of the graph is searched.
        """
        consumers = reachable_from(ENTRY) - {API_CLIENT}
        assert consumers, "the frontend graph is empty"
        text = "\n".join(strip_comments(read(module)) for module in consumers)
        for operation in SLICE_OPERATIONS:
            assert f".{operation}(" in text, (
                f"no production module calls client.{operation}(); the interface "
                "cannot be exercising the API it declares."
            )

    def test_the_registry_page_holds_no_transport_of_its_own(self) -> None:
        """The client is the boundary; the page consumes it."""
        assert "fetch(" not in strip_comments(read(REGISTRY_PAGE))
        assert any(
            specifier.endswith("api/client") for specifier in imports_of(REGISTRY_PAGE)
        ) or any(
            "useProjectRegistry" in specifier for specifier in imports_of(REGISTRY_PAGE)
        )


# ---------------------------------------------------------------------------
# Chain 1, links 3-5: API -> ProjectRegistry -> state machine -> persistence
# ---------------------------------------------------------------------------


class TestApiDelegatesToTheRegistry:
    def test_the_surface_constructs_the_registry_and_nothing_else(self) -> None:
        tree = module_of(APP_SOURCE)
        assert "ProjectRegistry" in called_names(tree), (
            "surfaces.command does not construct ProjectRegistry: the API would be "
            "reaching past the registry to the data."
        )
        assert "select" not in called_names(tree)
        assert "create_engine" not in called_names(tree)

    def test_every_mutating_route_delegates_to_a_registry_method(self) -> None:
        tree = module_of(APP_SOURCE)
        routes = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "router"
                for decorator in node.decorator_list
            )
        }
        expected = {
            "create_project": "create_project",
            "transition": "transition",
            "create_revision": "create_revision",
        }
        for route, delegate in expected.items():
            assert route in routes, f"the slice lost its {route} route"
            assert delegate in called_names(routes[route]), (
                f"{route} does not call ProjectRegistry.{delegate}"
            )


class TestRegistryDelegatesToTheStateMachine:
    def test_the_registry_builds_and_consults_the_canonical_machine(self) -> None:
        tree = module_of(REGISTRY_SOURCE)
        assert (
            "arkali.control.registry.project.project_state_machine"
            in imported_modules(tree)
        )
        called = called_names(tree)
        assert "build" in called
        assert "evaluate" in called, (
            "the registry does not ask the machine to evaluate a move; a transition "
            "decided anywhere else is a second authority."
        )

    def test_the_registry_declares_no_state_of_its_own(self) -> None:
        """NEGATIVE CONTROL: no transition table may reappear below the surface."""
        literals = {
            node.value
            for node in ast.walk(module_of(REGISTRY_SOURCE))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert literals & set(DEFINITION.states) == set()


class TestApiReachesPersistence:
    def test_the_surface_obtains_its_session_from_kernel_persistence(self) -> None:
        tree = module_of(APP_SOURCE)
        assert "arkali.kernel.persistence.session" in imported_modules(tree)
        called = called_names(tree)
        assert {"create_session_factory", "unit_of_work"} <= called, (
            "the surface does not open a real unit of work; without one there is "
            "no transaction boundary and no persistence."
        )


# ---------------------------------------------------------------------------
# Chain 1, link 6 and chain 2: the runtime proof
# ---------------------------------------------------------------------------


@pytest.fixture()
def database(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "slice.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def engine(database: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database))
    yield built
    built.dispose()


class TestTheSliceIsLinkedAtRuntime:
    def test_an_api_request_reaches_a_real_database_file(
        self, engine: Engine, database: pathlib.Path
    ) -> None:
        """The link no structural check can prove: the byte reached the disk.

        A request goes in through the HTTP surface. The application and its
        engine are then discarded, a completely separate engine is opened on the
        same file, and the record is read back through the registry. An
        in-memory registry, a disconnected repository or a faked write fails
        here and cannot be made to pass.
        """
        pdp = PolicyDecisionPoint.load(REPO)
        with TestClient(create_app(engine, pdp)) as client:
            assert client.post(
                "/api/projects", json={"project_id": "prj-slice", "name": "Slice"}
            ).status_code == 201
            assert client.post(
                "/api/projects/prj-slice/transitions", json={"target": "SPECIFIED"}
            ).status_code == 200
        engine.dispose()

        separate = create_persistence_engine(sqlite_url(database))
        try:
            with unit_of_work(create_session_factory(separate)) as session:
                record = ProjectRegistry(session).require("prj-slice")
                assert record.name == "Slice"
                assert record.lifecycle_state == "SPECIFIED"
        finally:
            separate.dispose()

    def test_the_state_the_api_reports_is_the_state_the_machine_recorded(
        self, engine: Engine
    ) -> None:
        """A refused move leaves the stored state untouched, end to end."""
        pdp = PolicyDecisionPoint.load(REPO)
        with TestClient(create_app(engine, pdp)) as client:
            client.post("/api/projects", json={"project_id": "prj-x", "name": "X"})
            refused = client.post(
                "/api/projects/prj-x/transitions", json={"target": "ACTIVE"}
            )
            assert refused.status_code == 409
            assert refused.json()["detail"]["code"]
            assert client.get("/api/projects/prj-x").json()["lifecycle_state"] == (
                DEFINITION.states[0]
            )

    def test_every_operation_lands_on_the_policy_audit_trail(
        self, engine: Engine
    ) -> None:
        """Chain 2: operation -> PEP -> PDP -> audit, proven at runtime."""
        pdp = PolicyDecisionPoint.load(REPO)
        app = create_app(engine, pdp)
        with TestClient(app) as client:
            client.get("/api/projects")
            client.post("/api/projects", json={"project_id": "prj-a", "name": "A"})
            client.get("/api/lifecycle/project")

        trail = app.state.pep.audit_trail
        assert len(trail) >= 3, "operations reached the registry without an audit record"
        assert {record.actor for record in trail} == {ACTOR}
        assert {record.operation_class for record in trail} == {
            "READ_FILE",
            "WRITE_WORKSPACE_FILE",
        }
        assert all(record.authoritative_source for record in trail), (
            "an audit record cites no authority"
        )


# ---------------------------------------------------------------------------
# The last two members of the requirement's list: tests and evidence
# ---------------------------------------------------------------------------


class TestTheSliceIsTestedAtEveryLayer:
    def test_the_frontend_tests_exercise_the_production_modules(self) -> None:
        """Presence proves nothing; the tests must import what they claim to test."""
        suites = sorted(FRONTEND_TESTS.rglob("*.test.ts*"))
        assert suites, "the frontend increment ships no tests"
        imported = {
            specifier
            for suite in suites
            for specifier in imports_of(suite)
        }
        assert "@/app/App" in imported, "no test mounts the real application"
        assert "@/api/client" in imported, "no test drives the real API client"

    def test_the_backend_integration_tests_drive_the_real_application(self) -> None:
        suite = BACKEND / "tests/surfaces/test_command_api.py"
        assert suite.is_file()
        tree = module_of(suite)
        assert "arkali.surfaces.command.app" in imported_modules(tree)
        assert "create_app" in called_names(tree)
        assert "TestClient" in called_names(tree)

    def test_the_contract_between_the_halves_is_itself_controlled(self) -> None:
        """The slice's two halves are joined by a control, not by an assumption."""
        drift = pathlib.Path(__file__).with_name("test_contract_drift.py")
        boundaries = pathlib.Path(__file__).with_name("test_frontend_boundaries.py")
        for control in (drift, boundaries):
            assert control.is_file(), f"{control.name} is missing"
            tree = module_of(control)
            assert any(
                module.startswith("arkali.") for module in imported_modules(tree)
            ), (
                f"{control.name} does not read backend authority, so it cannot be "
                "comparing the frontend against anything real"
            )
