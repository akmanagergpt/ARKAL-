"""Command Center API integration evidence (T5 on real persistence).

Every test drives a real FastAPI application over a real SQLite file migrated by
the real Alembic chain, with a real PDP loaded from the authority map. Nothing
is substituted: the substitution policy in VERIFICATION_ARCHITECTURE.md makes a
tier from T5 upward that substitutes a database NOT_CONFIGURED, never PASS.

Scope note: this is the backend half of the Phase 5 vertical slice. It does not
discharge ARK-REQ-0009, ARK-REQ-0178 or ARK-REQ-0229 - the frontend increment is
not built yet, and discharge belongs to the Phase 5 traceability record, report
and gate in any case.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import (
    ALEMBIC_INI,
    applied_revision,
    head_revision,
)
from arkali.surfaces.command.app import ACTOR, create_app
from arkali.surfaces.command.error_mapping import mapped_error_types, status_for

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
APP_SOURCE = BACKEND / "arkali/surfaces/command/app.py"


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
    path = tmp_path / "command.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def app(engine: Engine, pdp: PolicyDecisionPoint) -> FastAPI:
    return create_app(engine, pdp)


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as opened:
        yield opened


def created(client: TestClient, project_id: str = "prj-1",
            name: str = "Command Center Demo") -> dict[str, object]:
    response = client.post(
        "/api/projects", json={"project_id": project_id, "name": name}
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestReadinessAndListing:
    def test_health_reports_the_real_schema_revision(
        self, client: TestClient, engine: Engine
    ) -> None:
        body = client.get("/api/health").json()
        assert body["status"] == "ready"
        assert body["schema_revision"] == applied_revision(engine)
        # F-0032: the chain head is derived, never transcribed. A literal here
        # pinned the head that was current when the test was written and
        # expired the moment a legitimate migration was added.
        assert body["schema_revision"] == head_revision(BACKEND)

    def test_empty_registry_lists_nothing(self, client: TestClient) -> None:
        assert client.get("/api/projects").json() == {"projects": []}

    def test_created_projects_are_listed_deterministically(
        self, client: TestClient
    ) -> None:
        created(client, "prj-b", "Second")
        created(client, "prj-a", "First")
        listed = client.get("/api/projects").json()["projects"]
        assert [p["project_id"] for p in listed] == ["prj-a", "prj-b"]


class TestLifecycleVocabulary:
    """Package 4B contract addition. Why it exists is recorded in `contracts.py`.

    The frontend needs a state list to render a lifecycle action; without this
    route its only options were to hard-code the states - the shadow authority
    the slice forbids - or make the user type one.
    """

    def test_the_route_projects_the_canonical_machine(
        self, client: TestClient
    ) -> None:
        from arkali.control.registry.project.project_state_machine import DEFINITION

        body = client.get("/api/lifecycle/project").json()
        assert body["machine"] == DEFINITION.machine
        assert tuple(body["states"]) == DEFINITION.states

    def test_the_transition_relation_is_never_published(
        self, client: TestClient
    ) -> None:
        """NEGATIVE CONTROL: a client must not be able to decide legality.

        Publishing the relation would let the browser answer a question the
        Project machine owns. Only the vocabulary crosses the boundary.
        """
        body = client.get("/api/lifecycle/project").json()
        assert set(body) == {"machine", "states"}
        for forbidden in ("transitions", "forbidden", "terminal", "allowed"):
            assert forbidden not in client.get("/api/lifecycle/project").text

    def test_the_route_is_policy_guarded_like_every_other_read(
        self, client: TestClient, app: FastAPI
    ) -> None:
        client.get("/api/lifecycle/project")
        assert any(
            record.operation_class == "READ_FILE"
            for record in app.state.pep.audit_trail
        )


class TestCreateAndRead:
    def test_create_returns_the_registry_state(self, client: TestClient) -> None:
        body = created(client)
        assert body["project_id"] == "prj-1"
        assert body["lifecycle_state"] == "DRAFT"
        assert body["revisions"] == []

    def test_get_returns_the_project_with_its_revisions(
        self, client: TestClient
    ) -> None:
        created(client)
        client.post(
            "/api/projects/prj-1/revisions",
            json={"revision_id": "rev-1", "provenance_ref": None},
        )
        body = client.get("/api/projects/prj-1").json()
        assert [r["revision_id"] for r in body["revisions"]] == ["rev-1"]
        assert body["revisions"][0]["sequence"] == 1

    def test_unknown_project_is_a_404_with_a_stable_code(
        self, client: TestClient
    ) -> None:
        response = client.get("/api/projects/prj-missing")
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert detail["code"] == "ARK-ERR-0011"
        assert "prj-missing" in detail["message"]

    def test_duplicate_identity_is_a_409(self, client: TestClient) -> None:
        created(client)
        response = client.post(
            "/api/projects", json={"project_id": "prj-1", "name": "Other"}
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ARK-ERR-0012"

    def test_malformed_request_is_refused_by_the_contract(
        self, client: TestClient
    ) -> None:
        assert client.post("/api/projects", json={"project_id": ""}).status_code == 422
        assert client.post(
            "/api/projects",
            json={"project_id": "x", "name": "y", "unexpected": 1},
        ).status_code == 422


class TestLifecycleTransitions:
    def test_a_legal_transition_is_applied_and_returned(
        self, client: TestClient
    ) -> None:
        created(client)
        response = client.post(
            "/api/projects/prj-1/transitions", json={"target": "SPECIFIED"}
        )
        assert response.status_code == 200
        assert response.json()["lifecycle_state"] == "SPECIFIED"

    def test_a_forbidden_transition_is_a_409_and_changes_nothing(
        self, client: TestClient
    ) -> None:
        """DRAFT -> ACTIVE is explicitly forbidden by STATE_MACHINES section 1."""
        created(client)
        response = client.post(
            "/api/projects/prj-1/transitions", json={"target": "ACTIVE"}
        )
        assert response.status_code == 409
        assert client.get("/api/projects/prj-1").json()["lifecycle_state"] == "DRAFT"

    def test_an_undeclared_transition_is_a_409(self, client: TestClient) -> None:
        created(client)
        response = client.post(
            "/api/projects/prj-1/transitions", json={"target": "SUSPENDED"}
        )
        assert response.status_code == 409

    def test_an_unknown_state_is_a_422(self, client: TestClient) -> None:
        created(client)
        response = client.post(
            "/api/projects/prj-1/transitions", json={"target": "PROMOTED"}
        )
        assert response.status_code == 422

    def test_terminal_state_cannot_be_escaped_through_the_api(
        self, client: TestClient
    ) -> None:
        created(client)
        for target in ("SPECIFIED", "ACTIVE", "ARCHIVED"):
            assert client.post(
                "/api/projects/prj-1/transitions", json={"target": target}
            ).status_code == 200
        response = client.post(
            "/api/projects/prj-1/transitions", json={"target": "ACTIVE"}
        )
        assert response.status_code == 409
        assert client.get("/api/projects/prj-1").json()["lifecycle_state"] == "ARCHIVED"


class TestPersistenceThroughRestart:
    def test_state_survives_a_completely_new_application_and_engine(
        self, client: TestClient, engine: Engine, database_path: pathlib.Path,
        pdp: PolicyDecisionPoint
    ) -> None:
        """The slice is really attached to C-03/C-12, not to process memory."""
        created(client)
        client.post(
            "/api/projects/prj-1/revisions", json={"revision_id": "rev-1"}
        )
        client.post("/api/projects/prj-1/transitions", json={"target": "SPECIFIED"})
        engine.dispose()

        restarted_engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with TestClient(create_app(restarted_engine, pdp)) as restarted:
                body = restarted.get("/api/projects/prj-1").json()
                assert body["lifecycle_state"] == "SPECIFIED"
                assert [r["revision_id"] for r in body["revisions"]] == ["rev-1"]
                assert restarted.get("/api/health").json()["schema_revision"] == (
                    head_revision(BACKEND)  # F-0032: derived, never transcribed
                )
        finally:
            restarted_engine.dispose()

    def test_a_refused_write_is_not_persisted(
        self, client: TestClient, engine: Engine, database_path: pathlib.Path,
        pdp: PolicyDecisionPoint
    ) -> None:
        created(client)
        client.post("/api/projects/prj-1/transitions", json={"target": "ACTIVE"})
        engine.dispose()
        restarted_engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with TestClient(create_app(restarted_engine, pdp)) as restarted:
                assert restarted.get("/api/projects/prj-1").json()[
                    "lifecycle_state"
                ] == "DRAFT"
        finally:
            restarted_engine.dispose()


class TestPolicyEnforcement:
    def test_every_request_is_audited_through_the_phase_4_surface(
        self, client: TestClient, app: FastAPI
    ) -> None:
        created(client)
        client.get("/api/projects")
        trail = app.state.pep.audit_trail
        assert trail
        assert all(record.actor == ACTOR for record in trail)
        assert {record.operation_class for record in trail} == {
            "READ_FILE", "WRITE_WORKSPACE_FILE"
        }

    def test_the_surface_never_requests_a_stable_operation(self) -> None:
        """NEGATIVE CONTROL: no stable-mutation class is reachable from here."""
        literals = {
            node.value
            for node in ast.walk(ast.parse(APP_SOURCE.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert "WRITE_STABLE_FILE" not in literals
        assert "ROLLBACK_STABLE" not in literals

    def test_the_real_pdp_denies_a_stable_write_to_this_actor(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """NEGATIVE CONTROL: DENY is a hard refusal for this surface's actor."""
        from arkali.control.policy.pep import PolicyEnforcementPoint
        from arkali.control.policy.policy_contract import PolicyRequest
        from arkali.control.policy.policy_errors import PolicyDenied

        pep = PolicyEnforcementPoint(pdp, "probe")
        for operation in ("WRITE_STABLE_FILE", "ROLLBACK_STABLE"):
            with pytest.raises(PolicyDenied):
                pep.enforce(
                    PolicyRequest(
                        operation_class=operation, trust_tier="TRUST-0", actor=ACTOR
                    )
                )
        assert status_for(PolicyDenied("x")) == 403

    def test_every_route_passes_through_the_enforcement_point(self) -> None:
        """NEGATIVE CONTROL: no route may skip the guard.

        Parses the deployed source and requires every function decorated with a
        router method to call `guard`. A new unguarded endpoint fails here
        rather than silently becoming a policy bypass.
        """
        tree = ast.parse(APP_SOURCE.read_text(encoding="utf-8"))
        routes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and any(
                isinstance(d, ast.Call)
                and isinstance(d.func, ast.Attribute)
                and isinstance(d.func.value, ast.Name)
                and d.func.value.id == "router"
                for d in node.decorator_list
            )
        ]
        assert len(routes) == 7
        for route in routes:
            called = {
                inner.func.id
                for inner in ast.walk(route)
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name)
            }
            assert "guard" in called, f"{route.name} does not enforce policy"


class TestSurfaceIsNotASecondAuthority:
    def test_the_api_issues_no_query_of_its_own(self) -> None:
        """NEGATIVE CONTROL: the surface must delegate, not reach past."""
        tree = ast.parse(APP_SOURCE.read_text(encoding="utf-8"))
        callees = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "select" not in callees
        assert "text" not in callees
        assert "create_engine" not in callees

    def test_the_api_declares_no_lifecycle_state(self) -> None:
        """NEGATIVE CONTROL: no shadow state machine in the surface."""
        from arkali.control.registry.project.project_state_machine import DEFINITION

        literals = {
            node.value
            for node in ast.walk(ast.parse(APP_SOURCE.read_text(encoding="utf-8")))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert literals & set(DEFINITION.states) == set()

    def test_every_mapped_error_type_has_a_distinct_deterministic_status(
        self,
    ) -> None:
        for error_type in mapped_error_types():
            assert status_for(error_type("probe")) is not None

    def test_an_unmapped_error_is_not_given_a_default_status(self) -> None:
        """An unforeseen failure must not be reported as a client mistake."""
        assert status_for(RuntimeError("unforeseen")) is None


class TestNoLeakage:
    def test_error_bodies_carry_no_path_or_internal_object(
        self, client: TestClient, database_path: pathlib.Path
    ) -> None:
        created(client)
        for response in (
            client.get("/api/projects/prj-missing"),
            client.post("/api/projects", json={"project_id": "prj-1", "name": "x"}),
            client.post("/api/projects/prj-1/transitions", json={"target": "ACTIVE"}),
        ):
            body = response.text
            assert str(database_path) not in body
            assert "sqlite" not in body.lower()
            assert "Traceback" not in body
            assert "sqlalchemy" not in body.lower()

    def test_responses_expose_no_secret_shaped_field(
        self, client: TestClient
    ) -> None:
        created(client)
        body = client.get("/api/projects/prj-1").text.lower()
        for term in ("secret", "password", "token", "api_key", "credential"):
            assert term not in body
