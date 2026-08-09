"""T11 persistence evidence for the C-03 foundation (ARK-REQ-0011, ARK-REQ-0012).

Every test here runs against a REAL SQLite file on disk. Nothing is substituted:
the substitution policy in VERIFICATION_ARCHITECTURE.md states that any tier
from T5 upward which substitutes a database produces NOT_CONFIGURED, never PASS,
so a substituted database would make this evidence worthless, not convenient.

In-memory databases are used in exactly one place - the negative control that
proves the WAL probe reports what SQLite actually says rather than what the
caller hoped for.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from importlib.util import find_spec

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.engine import make_url

#: A PostgreSQL URL used only to prove the abstraction is not SQLite-bound.
POSTGRESQL_URL = "postgresql+psycopg://arkali@localhost/arkali"

from arkali.kernel.persistence.base import (
    ENTITY_CONTRACT_TABLE,
    PersistedEntityRow,
    contract_field_names,
    row_from_contract,
    stored_column_names,
)
from arkali.kernel.persistence.engine import (
    SQLITE_PRAGMAS,
    create_persistence_engine,
    is_sqlite,
    journal_mode,
    pragma_value,
    sqlite_library_version,
    sqlite_url,
    wal_sidecar_paths,
)
from arkali.kernel.persistence.repository import SqlRepository
from arkali.kernel.persistence.schema_contract import (
    PersistedEntityContract,
    SupportsRepository,
)
from arkali.kernel.persistence.session import (
    create_base_schema,
    create_session_factory,
    unit_of_work,
)

CONTRACT = PersistedEntityContract(
    entity="Project",
    owning_context="control.registry.project",
    primary_key="project_id",
    immutable_fields=("project_id", "created_at"),
    content_hashed=True,
)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "arkali_control.db"


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    create_base_schema(built)
    yield built
    built.dispose()


class TestSqliteEngine:
    def test_engine_is_sqlite_and_the_file_is_real(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        assert is_sqlite(engine)
        assert database_path.is_file()
        assert database_path.stat().st_size > 0

    def test_library_version_is_recorded_not_assumed(self) -> None:
        assert sqlite_library_version().count(".") >= 2

    def test_empty_url_is_refused(self) -> None:
        with pytest.raises(ValueError):
            create_persistence_engine("   ")

    def test_a_postgresql_url_resolves_to_a_non_sqlite_dialect(self) -> None:
        """Engine neutrality, provable without a PostgreSQL driver installed.

        `get_dialect()` resolves the dialect class without importing its DBAPI,
        so this asserts the property ADR-0006 actually registers - that the URL
        is not tied to SQLite - on a host where no PostgreSQL driver exists.
        """
        assert make_url(POSTGRESQL_URL).get_dialect().name == "postgresql"
        assert make_url(sqlite_url(pathlib.Path("a.db"))).get_dialect().name == "sqlite"

    @pytest.mark.skipif(
        find_spec("psycopg") is None,
        reason="NOT_CONFIGURED: no PostgreSQL driver on this host. ADR-0006 "
        "registers the abstraction as MANDATORY and verified PostgreSQL "
        "operation as NOT a canonical requirement, so this is reported rather "
        "than substituted.",
    )
    def test_a_non_sqlite_engine_builds_without_sqlite_pragmas(self) -> None:
        built = create_persistence_engine(POSTGRESQL_URL)
        try:
            assert not is_sqlite(built)
            assert built.dialect.name == "postgresql"
        finally:
            built.dispose()


class TestWalIsEnabledAndVerified:
    def test_journal_mode_read_back_from_a_live_connection_is_wal(
        self, engine: Engine
    ) -> None:
        """ARK-REQ-0011. The database's own answer, not the fact a pragma ran."""
        with engine.connect() as connection:
            assert journal_mode(connection) == "wal"

    def test_wal_sidecar_files_exist_on_disk(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        with engine.connect() as connection:
            assert journal_mode(connection) == "wal"
            sidecars = wal_sidecar_paths(database_path)
            assert any(path.exists() for path in sidecars)

    def test_every_declared_pragma_is_actually_applied(self, engine: Engine) -> None:
        expected = {"journal_mode": "wal", "foreign_keys": "1", "synchronous": "2"}
        with engine.connect() as connection:
            for pragma, _ in SQLITE_PRAGMAS:
                assert pragma_value(connection, pragma) == expected[pragma]

    def test_wal_survives_reopening_the_same_file(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        engine.dispose()
        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with reopened.connect() as connection:
                assert journal_mode(connection) == "wal"
        finally:
            reopened.dispose()

    def test_probe_reports_memory_for_an_in_memory_database(self) -> None:
        """NEGATIVE CONTROL: the probe cannot report `wal` for a database that
        has no journal file. If this ever returned `wal`, every WAL assertion
        above would be worthless."""
        built = create_persistence_engine("sqlite+pysqlite:///:memory:")
        try:
            with built.connect() as connection:
                assert journal_mode(connection) == "memory"
        finally:
            built.dispose()

    def test_unknown_pragma_is_refused(self, engine: Engine) -> None:
        with engine.connect() as connection:
            with pytest.raises(ValueError):
                pragma_value(connection, "page_size")


class TestBaseSchemaMatchesItsContract:
    def test_table_exists_after_creation(self, engine: Engine) -> None:
        assert ENTITY_CONTRACT_TABLE in inspect(engine).get_table_names()

    def test_columns_are_exactly_the_contract_fields(self) -> None:
        """Reconciliation: the stored form cannot drift from the Phase 2 contract."""
        assert set(stored_column_names()) == set(contract_field_names())

    def test_a_row_round_trips_through_its_contract(self) -> None:
        restored = row_from_contract(CONTRACT).to_contract()
        assert restored == CONTRACT


class TestRepositoryIsEngineNeutral:
    def test_concrete_repository_satisfies_the_phase_2_protocol(
        self, engine: Engine
    ) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            repository = SqlRepository(session, PersistedEntityRow, "entity")
            assert isinstance(repository, SupportsRepository)

    def test_put_then_get_returns_the_stored_entity(self, engine: Engine) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            repository = SqlRepository(session, PersistedEntityRow, "entity")
            repository.put(CONTRACT.entity, row_from_contract(CONTRACT))
        with unit_of_work(factory) as session:
            repository = SqlRepository(session, PersistedEntityRow, "entity")
            found = repository.get(CONTRACT.entity)
            assert found is not None
            assert isinstance(found, PersistedEntityRow)
            assert found.to_contract() == CONTRACT

    def test_get_returns_none_for_an_absent_key(self, engine: Engine) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            repository = SqlRepository(session, PersistedEntityRow, "entity")
            assert repository.get("NoSuchEntity") is None

    def test_delete_reports_whether_a_row_was_removed(self, engine: Engine) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            repository = SqlRepository(session, PersistedEntityRow, "entity")
            repository.put(CONTRACT.entity, row_from_contract(CONTRACT))
        with unit_of_work(factory) as session:
            repository = SqlRepository(session, PersistedEntityRow, "entity")
            assert repository.delete(CONTRACT.entity) is True
            assert repository.delete(CONTRACT.entity) is False

    def test_key_mismatch_is_refused(self, engine: Engine) -> None:
        """NEGATIVE CONTROL: storing under a key the entity does not carry."""
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            repository = SqlRepository(session, PersistedEntityRow, "entity")
            with pytest.raises(ValueError):
                repository.put("SomeOtherKey", row_from_contract(CONTRACT))

    def test_wrong_model_is_refused(self, engine: Engine) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            repository = SqlRepository(session, PersistedEntityRow, "entity")
            with pytest.raises(TypeError):
                repository.put(CONTRACT.entity, "not an entity")

    def test_unknown_key_attribute_is_refused(self, engine: Engine) -> None:
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            with pytest.raises(ValueError):
                SqlRepository(session, PersistedEntityRow, "no_such_column")


class TestDurabilityAcrossCloseAndReopen:
    def test_committed_data_survives_disposing_and_rebuilding_the_engine(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        """The core persistence claim: the data is in the file, not in a process."""
        factory = create_session_factory(engine)
        with unit_of_work(factory) as session:
            SqlRepository(session, PersistedEntityRow, "entity").put(
                CONTRACT.entity, row_from_contract(CONTRACT)
            )
        engine.dispose()

        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                found = SqlRepository(session, PersistedEntityRow, "entity").get(
                    CONTRACT.entity
                )
                assert found is not None
                assert isinstance(found, PersistedEntityRow)
                assert found.to_contract() == CONTRACT
        finally:
            reopened.dispose()

    def test_a_rolled_back_unit_of_work_persists_nothing(
        self, engine: Engine, database_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: a failed transaction must not leave data behind.

        Without this, the durability test above would pass even if every write
        committed unconditionally.
        """
        factory = create_session_factory(engine)
        with pytest.raises(RuntimeError):
            with unit_of_work(factory) as session:
                SqlRepository(session, PersistedEntityRow, "entity").put(
                    CONTRACT.entity, row_from_contract(CONTRACT)
                )
                raise RuntimeError("the caller failed after writing")
        engine.dispose()

        reopened = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                repository = SqlRepository(session, PersistedEntityRow, "entity")
                assert repository.get(CONTRACT.entity) is None
                assert repository.count() == 0
        finally:
            reopened.dispose()
