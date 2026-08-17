"""C-03 migration evidence. Alembic runs against a REAL SQLite file.

The migration is not asserted to exist; it is applied, and the resulting schema
is compared against the ORM metadata. A migration that creates a table the ORM
does not map, or omits one it does, is caught here rather than at first use.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import re

import pytest
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
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
    run_upgrade,
)
from arkali.kernel.persistence.schema_contract import MigrationDirection

BACKEND = pathlib.Path(__file__).resolve().parents[2]


PACKAGE = BACKEND / "arkali"
ENV_PY = BACKEND / "alembic" / "env.py"
BASE_CLASS = "PersistenceBase"


def alembic_config(database_path: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database_path))
    return config


def modules_declaring_mapped_classes() -> frozenset[str]:
    """Every shipping module that declares a `PersistenceBase` subclass.

    Derived from the source tree by AST, not listed. F-0033: the metadata object
    is populated by import side effect, so any answer that depends on which
    modules a given test run happened to import is an answer that changes with
    the collection order. This derivation does not.
    """
    found: set[str] = set()
    for path in PACKAGE.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        declares = any(
            isinstance(node, ast.ClassDef)
            and any(
                isinstance(base, ast.Name) and base.id == BASE_CLASS
                for base in node.bases
            )
            for node in ast.walk(tree)
        )
        if declares:
            relative = path.relative_to(BACKEND).with_suffix("")
            found.add(".".join(relative.parts))
    return frozenset(found)


def load_complete_metadata() -> None:
    """Import every mapped module so the metadata is the whole registry."""
    for name in sorted(modules_declaring_mapped_classes()):
        importlib.import_module(name)


def env_declared_modules() -> frozenset[str]:
    """`MAPPED_RECORD_MODULES` as written in `env.py`, read as text.

    `env.py` runs migrations when imported, so it is parsed rather than
    imported. Parsing is also the honest thing to check: the question is what
    the migration composition root declares, not what some other import made
    true.
    """
    source = ENV_PY.read_text(encoding="utf-8")
    block = re.search(
        r"MAPPED_RECORD_MODULES\s*=\s*\((?P<body>[^)]*)\)", source, re.S
    )
    assert block is not None, "env.py declares no MAPPED_RECORD_MODULES"
    return frozenset(re.findall(r'"([^"]+)"', block.group("body")))


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


class TestAutogenerateTargetIsComplete:
    """F-0033. The migration tool's target metadata must be the whole registry.

    Autogenerate compares the live database against `target_metadata`. A target
    missing a table does not under-report it - it proposes DROPping it. So the
    completeness of that object is a correctness property of the migration
    tooling, not a test convenience.
    """

    def test_the_source_tree_really_declares_mapped_classes(self) -> None:
        """The derivation is not vacuous: it finds the modules that exist."""
        derived = modules_declaring_mapped_classes()
        assert len(derived) >= 3
        assert "arkali.kernel.persistence.base" in derived

    def test_env_py_declares_every_module_that_maps_a_table(self) -> None:
        """A new mapped module that env.py does not import fails here."""
        derived = modules_declaring_mapped_classes()
        declared = env_declared_modules()
        # The base declares the contract table and is imported by env.py
        # directly, so it is legitimately absent from the record-module list.
        owed = derived - {"arkali.kernel.persistence.base"}
        assert owed - declared == frozenset(), (
            "env.py's MAPPED_RECORD_MODULES omits a module that declares a "
            f"mapped class: {sorted(owed - declared)}"
        )
        assert declared - owed == frozenset(), (
            f"env.py declares a module that maps nothing: {sorted(declared - owed)}"
        )

    def test_env_py_imports_each_module_it_declares(self) -> None:
        """Declaring the list is not enough; the import is what registers."""
        source = ENV_PY.read_text(encoding="utf-8")
        for module in sorted(env_declared_modules()):
            assert f"import {module}" in source, f"{module} declared but not imported"

    def test_the_loaded_registry_is_larger_than_the_base_alone(self) -> None:
        """Proof the import side effect is what populates the metadata.

        Without this the completeness controls above could be satisfied by an
        empty registry. `test_migrated_schema_matches_the_orm_metadata` is the
        control that actually compares the two descriptions of the schema; this
        one only shows there is something to compare.
        """
        load_complete_metadata()
        assert len(PersistenceBase.metadata.tables) > 1
        assert ENTITY_CONTRACT_TABLE in PersistenceBase.metadata.tables


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
        """The migration and the mapped model must describe one table.

        The registry is loaded from the derived module set first (F-0033).
        Before that, this comparison silently measured whichever mapped modules
        the surrounding test session happened to have imported, so it passed in
        a full run and failed when `tests/persistence` ran alone.
        """
        load_complete_metadata()
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

class TestRunUpgradeMechanic:
    """Phase 20: the production `run_upgrade` mechanic `lifecycle.recovery`'s
    Apply step drives, proven against a real SQLite target - not a second
    duplicate of `TestMigrationRunsAgainstRealSqlite`, but the same result
    obtained through the shipped function rather than a test-local rebuild of
    the Alembic Config."""

    def test_run_upgrade_reaches_head_against_a_real_target(
        self, tmp_path: pathlib.Path
    ) -> None:
        database_path = tmp_path / "run_upgrade.db"
        run_upgrade(sqlite_url(database_path), BACKEND, "head")
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            assert applied_revision(engine) == head_revision(BACKEND)
            assert ENTITY_CONTRACT_TABLE in set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

    def test_run_upgrade_can_target_an_intermediate_revision(
        self, tmp_path: pathlib.Path
    ) -> None:
        chain = declared_migrations(BACKEND)
        assert len(chain) >= 2
        first = chain[0].revision
        database_path = tmp_path / "partial.db"
        run_upgrade(sqlite_url(database_path), BACKEND, first)
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            assert applied_revision(engine) == first
        finally:
            engine.dispose()


class TestMigrationTargetRefusals:
    def test_migration_target_without_a_url_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: a migration run must know its target."""
        config = Config(str(BACKEND / ALEMBIC_INI))
        config.set_main_option("script_location", str(BACKEND / "alembic"))
        with pytest.raises(ValueError, match="no database URL"):
            command.upgrade(config, "head")
