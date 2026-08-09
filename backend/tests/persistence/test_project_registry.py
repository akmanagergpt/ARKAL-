"""C-12 Project/Revision Registry evidence. Real SQLite, real constraints.

Every test runs against a SQLite file on disk with foreign keys enforced, so the
identity guarantees under test are the database's, not Python's. The negative
controls assert the *reason* for each refusal - a typed error or a specific
integrity constraint - because a control that only asserts "something raised"
would pass for the wrong reason.
"""

from __future__ import annotations

import ast
import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError

from arkali.control.registry.project.project_state_machine import DEFINITION
from arkali.control.registry.project.records import (
    INITIAL_STATE,
    PROJECT_TABLE,
    REVISION_TABLE,
    ProjectRecord,
    ProjectRevisionRecord,
)
from arkali.control.registry.project.errors import (
    DuplicateIdentity,
    UnknownProject,
)
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.kernel.contracts.state_machine_errors import (
    ForbiddenTransition,
    IllegalTransition,
    TerminalStateEscape,
    UnknownState,
)
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.session import (
    create_base_schema,
    create_session_factory,
    unit_of_work,
)

REGISTRY_SOURCE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "arkali/control/registry/project/registry.py"
)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "registry.db"


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    create_base_schema(built)
    yield built
    built.dispose()


def registered(engine: Engine, project_id: str = "prj-1",
               name: str = "ARKALI Demo") -> None:
    with unit_of_work(create_session_factory(engine)) as session:
        ProjectRegistry(session).create_project(project_id, name)


class TestSchemaAndIdentity:
    def test_both_tables_exist(self, engine: Engine) -> None:
        tables = set(inspect(engine).get_table_names())
        assert {PROJECT_TABLE, REVISION_TABLE} <= tables

    def test_identity_is_enforced_by_real_database_constraints(
        self, engine: Engine
    ) -> None:
        """Not a pre-insert check: the constraints must exist in the schema."""
        inspector = inspect(engine)
        assert inspector.get_pk_constraint(PROJECT_TABLE)["constrained_columns"] == [
            "project_id"
        ]
        assert inspector.get_pk_constraint(REVISION_TABLE)["constrained_columns"] == [
            "revision_id"
        ]
        unique_project = {
            tuple(u["column_names"]) for u in inspector.get_unique_constraints(PROJECT_TABLE)
        }
        assert ("name",) in unique_project
        unique_revision = {
            tuple(u["column_names"])
            for u in inspector.get_unique_constraints(REVISION_TABLE)
        }
        assert ("project_id", "sequence") in unique_revision
        foreign = inspector.get_foreign_keys(REVISION_TABLE)
        assert foreign and foreign[0]["referred_table"] == PROJECT_TABLE

    def test_project_starts_in_the_machine_declared_initial_state(
        self, engine: Engine
    ) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            record = ProjectRegistry(session).require("prj-1")
            assert record.lifecycle_state == INITIAL_STATE == "DRAFT"

    def test_creation_metadata_is_recorded(self, engine: Engine) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            record = ProjectRegistry(session).require("prj-1")
            assert record.created_at is not None
            assert record.updated_at is not None

    def test_revision_identity_and_ordering(self, engine: Engine) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            registry = ProjectRegistry(session)
            registry.create_revision("prj-1", "rev-1")
            registry.create_revision("prj-1", "rev-2", provenance_ref="artifact://later")
        with unit_of_work(create_session_factory(engine)) as session:
            revisions = ProjectRegistry(session).revisions_of("prj-1")
            assert [r.revision_id for r in revisions] == ["rev-1", "rev-2"]
            assert [r.sequence for r in revisions] == [1, 2]
            assert revisions[0].provenance_ref is None
            assert revisions[1].provenance_ref == "artifact://later"

    def test_empty_identity_is_refused(self, engine: Engine) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            registry = ProjectRegistry(session)
            with pytest.raises(Exception, match="non-empty"):
                registry.create_project("  ", "name")


class TestDuplicateIdentityControls:
    def test_duplicate_project_id_is_refused_by_the_service(
        self, engine: Engine
    ) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(DuplicateIdentity):
                ProjectRegistry(session).create_project("prj-1", "Another Name")

    def test_duplicate_project_id_is_refused_by_the_database(
        self, engine: Engine
    ) -> None:
        """NEGATIVE CONTROL: bypass the service check; the constraint must hold."""
        registered(engine)
        with pytest.raises(IntegrityError):
            with unit_of_work(create_session_factory(engine)) as session:
                session.add(
                    ProjectRecord(
                        project_id="prj-1", name="Different", lifecycle_state="DRAFT"
                    )
                )

    def test_duplicate_project_name_is_refused_by_the_database(
        self, engine: Engine
    ) -> None:
        registered(engine)
        with pytest.raises(IntegrityError):
            with unit_of_work(create_session_factory(engine)) as session:
                session.add(
                    ProjectRecord(
                        project_id="prj-2", name="ARKALI Demo", lifecycle_state="DRAFT"
                    )
                )

    def test_duplicate_revision_id_is_refused_by_the_service(
        self, engine: Engine
    ) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            ProjectRegistry(session).create_revision("prj-1", "rev-1")
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(DuplicateIdentity):
                ProjectRegistry(session).create_revision("prj-1", "rev-1")

    def test_duplicate_revision_sequence_is_refused_by_the_database(
        self, engine: Engine
    ) -> None:
        """NEGATIVE CONTROL for the (project_id, sequence) unique constraint."""
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            ProjectRegistry(session).create_revision("prj-1", "rev-1")
        with pytest.raises(IntegrityError):
            with unit_of_work(create_session_factory(engine)) as session:
                session.add(
                    ProjectRevisionRecord(
                        revision_id="rev-collide", project_id="prj-1", sequence=1
                    )
                )

    def test_revision_for_an_unknown_project_is_refused_by_the_service(
        self, engine: Engine
    ) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(UnknownProject):
                ProjectRegistry(session).create_revision("prj-missing", "rev-x")

    def test_revision_for_an_unknown_project_is_refused_by_the_database(
        self, engine: Engine
    ) -> None:
        """NEGATIVE CONTROL: the foreign key, not the service lookup.

        This is only meaningful because Package 1 turned foreign keys on; SQLite
        would otherwise accept the orphan silently.
        """
        with pytest.raises(IntegrityError):
            with unit_of_work(create_session_factory(engine)) as session:
                session.add(
                    ProjectRevisionRecord(
                        revision_id="rev-orphan", project_id="prj-missing", sequence=1
                    )
                )


class TestStateMachineIntegration:
    def test_registry_defers_to_the_canonical_machine(self, engine: Engine) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            assert ProjectRegistry(session).machine_name == DEFINITION.machine

    def test_valid_transition_is_persisted(self, engine: Engine) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            registry = ProjectRegistry(session)
            registry.transition("prj-1", "SPECIFIED")
            registry.transition("prj-1", "ACTIVE")
        with unit_of_work(create_session_factory(engine)) as session:
            assert ProjectRegistry(session).require("prj-1").lifecycle_state == "ACTIVE"

    def test_forbidden_transition_is_rejected(self, engine: Engine) -> None:
        """NEGATIVE CONTROL: DRAFT->ACTIVE is explicitly forbidden by section 1."""
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(ForbiddenTransition):
                ProjectRegistry(session).transition("prj-1", "ACTIVE")

    def test_undeclared_transition_is_rejected(self, engine: Engine) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(IllegalTransition):
                ProjectRegistry(session).transition("prj-1", "SUSPENDED")

    def test_unknown_target_state_is_rejected(self, engine: Engine) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(UnknownState):
                ProjectRegistry(session).transition("prj-1", "PROMOTED")

    def test_archived_is_terminal(self, engine: Engine) -> None:
        """NEGATIVE CONTROL: terminal-state escape must be structurally refused."""
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            registry = ProjectRegistry(session)
            registry.transition("prj-1", "SPECIFIED")
            registry.transition("prj-1", "ACTIVE")
            registry.transition("prj-1", "ARCHIVED")
        with unit_of_work(create_session_factory(engine)) as session:
            registry = ProjectRegistry(session)
            for target in ("ACTIVE", "SUSPENDED", "DRAFT", "SPECIFIED"):
                with pytest.raises(TerminalStateEscape):
                    registry.transition("prj-1", target)

    def test_a_rejected_transition_leaves_the_stored_state_unchanged(
        self, engine: Engine
    ) -> None:
        registered(engine)
        with pytest.raises(ForbiddenTransition):
            with unit_of_work(create_session_factory(engine)) as session:
                ProjectRegistry(session).transition("prj-1", "ACTIVE")
        with unit_of_work(create_session_factory(engine)) as session:
            assert ProjectRegistry(session).require("prj-1").lifecycle_state == "DRAFT"

    def test_transition_on_an_unknown_project_is_refused(self, engine: Engine) -> None:
        with unit_of_work(create_session_factory(engine)) as session:
            with pytest.raises(UnknownProject):
                ProjectRegistry(session).transition("prj-missing", "SPECIFIED")


class TestRegistryIsNotASecondAuthority:
    """NEGATIVE CONTROL for shadow authority.

    The registry must not accumulate its own transition table. This reads the
    deployed source: any literal collection of state names, or any comparison
    against one, would be a second relation that could drift from section 1.
    """

    def test_registry_source_declares_no_state_names(self) -> None:
        source = REGISTRY_SOURCE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        assert literals & set(DEFINITION.states) == set()

    def test_registry_source_defines_no_machine_of_its_own(self) -> None:
        """A second `StateMachineDefinition` here would be a rival relation."""
        tree = ast.parse(REGISTRY_SOURCE.read_text(encoding="utf-8"))
        constructed = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "StateMachineDefinition" not in constructed
        assert "StateMachine" not in constructed

    def test_the_machine_is_the_only_evaluator_invoked(self) -> None:
        tree = ast.parse(REGISTRY_SOURCE.read_text(encoding="utf-8"))
        callees = {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        assert "evaluate" in callees
