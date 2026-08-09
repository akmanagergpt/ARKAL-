"""C-12 registry integrity: revision immutability and transactional behaviour.

Split from `test_project_registry.py`, which reached 401 logical lines against a
400-line budget. ADR-0008 makes decomposition the response to a budget; an
exception would require HUMAN GATE 8 and could not rest on a justification
authored by the implementing actor in any case.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, inspect, select

from arkali.control.registry.project.errors import (
    ImmutableRevisionViolation,
    UnknownProject,
)
from arkali.control.registry.project.records import (
    PROJECT_TABLE,
    REVISION_TABLE,
    ProjectRecord,
)
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.session import (
    create_base_schema,
    create_session_factory,
    unit_of_work,
)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "integrity.db"


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


class TestRevisionImmutability:
    def test_a_persisted_revision_cannot_be_updated(self, engine: Engine) -> None:
        """NEGATIVE CONTROL: SQL UPDATE being available must not make it mutable."""
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            ProjectRegistry(session).create_revision("prj-1", "rev-1")
        with pytest.raises(ImmutableRevisionViolation):
            with unit_of_work(create_session_factory(engine)) as session:
                found = ProjectRegistry(session).revision("rev-1")
                assert found is not None
                found.provenance_ref = "artifact://rewritten"

    def test_the_refused_mutation_did_not_persist(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            ProjectRegistry(session).create_revision(
                "prj-1", "rev-1", provenance_ref="artifact://original"
            )
        with pytest.raises(ImmutableRevisionViolation):
            with unit_of_work(create_session_factory(engine)) as session:
                found = ProjectRegistry(session).revision("rev-1")
                assert found is not None
                found.sequence = 99
                found.provenance_ref = "artifact://rewritten"
        engine.dispose()

        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                stored = ProjectRegistry(session).revision("rev-1")
                assert stored is not None
                assert stored.sequence == 1
                assert stored.provenance_ref == "artifact://original"
        finally:
            reopened.dispose()

    def test_the_project_record_remains_mutable(self, engine: Engine) -> None:
        """The canonical distinction: mutable project, immutable revision."""
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            ProjectRegistry(session).transition("prj-1", "SPECIFIED")
        with unit_of_work(create_session_factory(engine)) as session:
            record = ProjectRegistry(session).require("prj-1")
            assert record.lifecycle_state == "SPECIFIED"


class TestTransactionalIntegrity:
    def test_project_and_revision_creation_commit(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            ProjectRegistry(session).create_revision("prj-1", "rev-1")
        engine.dispose()
        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                registry = ProjectRegistry(session)
                assert registry.require("prj-1").lifecycle_state == "DRAFT"
                assert registry.revision("rev-1") is not None
        finally:
            reopened.dispose()

    def test_failure_rolls_the_whole_unit_of_work_back(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: partial transaction failure persists nothing."""
        with pytest.raises(RuntimeError):
            with unit_of_work(create_session_factory(engine)) as session:
                registry = ProjectRegistry(session)
                registry.create_project("prj-9", "Rolled Back")
                registry.create_revision("prj-9", "rev-9")
                raise RuntimeError("the caller failed after two writes")
        engine.dispose()
        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                registry = ProjectRegistry(session)
                assert registry.get("prj-9") is None
                assert registry.revision("rev-9") is None
        finally:
            reopened.dispose()

    def test_a_failed_second_write_does_not_leave_the_first_committed(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        registered(engine)
        with pytest.raises(UnknownProject):
            with unit_of_work(create_session_factory(engine)) as session:
                registry = ProjectRegistry(session)
                registry.create_revision("prj-1", "rev-ok")
                registry.create_revision("prj-absent", "rev-bad")
        engine.dispose()
        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                assert ProjectRegistry(session).revision("rev-ok") is None
        finally:
            reopened.dispose()

    def test_reopen_preserves_lifecycle_state(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            registry = ProjectRegistry(session)
            registry.transition("prj-1", "SPECIFIED")
            registry.transition("prj-1", "ACTIVE")
            registry.transition("prj-1", "SUSPENDED")
        engine.dispose()
        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                record = ProjectRegistry(session).require("prj-1")
                assert record.lifecycle_state == "SUSPENDED"
            with unit_of_work(create_session_factory(reopened)) as session:
                ProjectRegistry(session).transition("prj-1", "ACTIVE")
        finally:
            reopened.dispose()

    def test_no_secret_shaped_column_exists(self, engine: Engine) -> None:
        """No secret material may be persisted in project/revision records."""
        inspector = inspect(engine)
        forbidden = ("secret", "password", "token", "api_key", "credential")
        for table in (PROJECT_TABLE, REVISION_TABLE):
            names = [c["name"].lower() for c in inspector.get_columns(table)]
            assert not [n for n in names if any(f in n for f in forbidden)]

    def test_registry_reads_use_the_neutral_expression_language(
        self, engine: Engine
    ) -> None:
        """Sanity: the ORM path returns the same rows as a neutral select."""
        registered(engine)
        with unit_of_work(create_session_factory(engine)) as session:
            direct = session.execute(select(ProjectRecord)).scalars().all()
            assert [r.project_id for r in direct] == ["prj-1"]
