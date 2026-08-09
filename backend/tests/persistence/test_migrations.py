"""C-03 migration evidence. Alembic runs against a REAL SQLite file.

The migration is not asserted to exist; it is applied, and the resulting schema
is compared against the ORM metadata. A migration that creates a table the ORM
does not map, or omits one it does, is caught here rather than at first use.
"""

from __future__ import annotations

import pathlib

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from arkali.kernel.persistence.base import ENTITY_CONTRACT_TABLE, PersistenceBase
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import (
    ALEMBIC_INI,
    ALEMBIC_VERSION_TABLE,
    VERSIONS_DIR,
    applied_revision,
    contract_of,
    declared_migrations,
    head_revision,
    is_forward_only,
)
from arkali.kernel.persistence.schema_contract import MigrationDirection

BACKEND = pathlib.Path(__file__).resolve().parents[2]


def alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


class TestDeclaredChain:
    def test_alembic_foundation_files_exist(self) -> None:
        assert (BACKEND / ALEMBIC_INI).is_file()
        assert (BACKEND / "alembic" / "env.py").is_file()
        assert (BACKEND / VERSIONS_DIR).is_dir()

    def test_chain_is_linear_with_one_root(self) -> None:
        chain = declared_migrations(BACKEND)
        assert len(chain) >= 1
        assert chain[0].down_revision is None
        for parent, child in zip(chain, chain[1:]):
            assert child.down_revision == parent.revision

    def test_chain_is_forward_only(self) -> None:
        """ARCHITECTURE.md section 10."""
        assert is_forward_only(declared_migrations(BACKEND))

    def test_every_revision_uses_the_phase_2_contract(self) -> None:
        """The contract is instantiated, never redefined."""
        for contract in declared_migrations(BACKEND):
            assert contract.direction is MigrationDirection.FORWARD
            assert contract.requires_backup is True
            assert contract.requires_human_gate_6_on_real_data is True

    def test_head_is_the_last_revision(self) -> None:
        assert head_revision(BACKEND) == declared_migrations(BACKEND)[-1].revision


class TestMalformedRevisionsAreRefused:
    """NEGATIVE CONTROLS: the runner must refuse what it cannot identify."""

    def test_revision_disagreeing_with_its_filename_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        path = tmp_path / "0007_named_one_thing.py"
        path.write_text(
            'revision = "0007_named_another"\ndown_revision = None\n'
            'direction = "FORWARD"\n',
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="filename and revision"):
            contract_of(path)

    def test_revision_without_a_direction_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        path = tmp_path / "0008_no_direction.py"
        path.write_text(
            'revision = "0008_no_direction"\ndown_revision = None\n', encoding="utf-8"
        )
        with pytest.raises(ValueError, match="direction"):
            contract_of(path)

    def test_a_branched_chain_is_refused(self, tmp_path: pathlib.Path) -> None:
        versions = tmp_path / VERSIONS_DIR
        versions.mkdir(parents=True)
        for name, down in (("0001_root", None), ("0002_a", "0001_root"),
                           ("0003_b", "0001_root")):
            (versions / f"{name}.py").write_text(
                f'revision = "{name}"\ndown_revision = {down!r}\n'
                'direction = "FORWARD"\n',
                encoding="utf-8",
            )
        with pytest.raises(ValueError, match="successors"):
            declared_migrations(tmp_path)

    def test_two_roots_are_refused(self, tmp_path: pathlib.Path) -> None:
        versions = tmp_path / VERSIONS_DIR
        versions.mkdir(parents=True)
        for name in ("0001_root_one", "0002_root_two"):
            (versions / f"{name}.py").write_text(
                f'revision = "{name}"\ndown_revision = None\n'
                'direction = "FORWARD"\n',
                encoding="utf-8",
            )
        with pytest.raises(ValueError, match="exactly one root"):
            declared_migrations(tmp_path)

    def test_a_missing_versions_directory_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            declared_migrations(tmp_path / "nowhere")


class TestMigrationRunsAgainstRealSqlite:
    def test_upgrade_creates_the_base_schema_and_records_the_revision(
        self, tmp_path: pathlib.Path
    ) -> None:
        database_path = tmp_path / "migrated.db"
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            assert applied_revision(engine) is None
            command.upgrade(alembic_config(database_path), "head")

            tables = set(inspect(engine).get_table_names())
            assert ENTITY_CONTRACT_TABLE in tables
            assert ALEMBIC_VERSION_TABLE in tables
            assert applied_revision(engine) == head_revision(BACKEND)
        finally:
            engine.dispose()

    def test_migrated_schema_matches_the_orm_metadata(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The migration and the mapped model must describe one table."""
        database_path = tmp_path / "compare.db"
        command.upgrade(alembic_config(database_path), "head")
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            inspector = inspect(engine)
            migrated = {
                name: {c["name"] for c in inspector.get_columns(name)}
                for name in inspector.get_table_names()
                if name != ALEMBIC_VERSION_TABLE
            }
            mapped = {
                name: {c.name for c in table.columns}
                for name, table in PersistenceBase.metadata.tables.items()
            }
            assert migrated == mapped
        finally:
            engine.dispose()

    def test_downgrade_removes_the_base_schema(
        self, tmp_path: pathlib.Path
    ) -> None:
        database_path = tmp_path / "reversible.db"
        config = alembic_config(database_path)
        command.upgrade(config, "head")
        command.downgrade(config, "base")
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            assert ENTITY_CONTRACT_TABLE not in inspect(engine).get_table_names()
            assert applied_revision(engine) is None
        finally:
            engine.dispose()

    def test_migration_target_without_a_url_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: a migration run must know its target."""
        config = Config(str(BACKEND / ALEMBIC_INI))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        with pytest.raises(ValueError, match="no database URL"):
            command.upgrade(config, "head")
