"""WAL-safe backup/restore MECHANICS (kernel.persistence).

Scope note, stated so this file cannot be mistaken for more than it is: these
controls prove the byte-level mechanism is correct and WAL-safe. They do **not**
discharge ARK-REQ-0153 or ARK-REQ-0335. Those require the `lifecycle.recovery`
backup lifecycle - manifest, integrity, verification and the BackupRestore state
machine - which is Phase 5 Package 3 and is not implemented yet. Nothing here
marks a backup verified, and the A -> B -> restore -> verify proof below is
evidence for the mechanism only.

Every test uses real SQLite files in WAL mode.
"""

from __future__ import annotations

import pathlib
import sqlite3
from collections.abc import Iterator
from importlib.util import find_spec

import pytest
from sqlalchemy import Engine

from arkali.control.registry.project.registry import ProjectRegistry
from arkali.kernel.persistence.backup import (
    SQLITE_MAGIC,
    copy_database,
    file_digest,
    integrity_check,
    looks_like_sqlite,
    restore_database,
)
from arkali.kernel.persistence.engine import (
    create_persistence_engine,
    journal_mode,
    sqlite_url,
)
from arkali.kernel.persistence.session import (
    create_base_schema,
    create_session_factory,
    unit_of_work,
)


@pytest.fixture()
def live_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "live.db"


@pytest.fixture()
def engine(live_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(live_path))
    create_base_schema(built)
    yield built
    built.dispose()


def state_a(engine: Engine) -> None:
    """State A: one project and one revision."""
    with unit_of_work(create_session_factory(engine)) as session:
        registry = ProjectRegistry(session)
        registry.create_project("prj-a", "State A")
        registry.create_revision("prj-a", "rev-a")


def mutate_to_b(engine: Engine) -> None:
    """State B: observably different from A."""
    with unit_of_work(create_session_factory(engine)) as session:
        registry = ProjectRegistry(session)
        registry.transition("prj-a", "SPECIFIED")
        registry.create_project("prj-b", "Added After Backup")


class TestBackupIsWalSafeAndNotAFileCopy:
    def test_source_is_in_wal_mode_when_backed_up(self, engine: Engine) -> None:
        """Precondition: the mechanism must be exercised against real WAL."""
        state_a(engine)
        with engine.connect() as connection:
            assert journal_mode(connection) == "wal"

    def test_backup_of_an_open_wal_database_is_a_sqlite_image(
        self, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        state_a(engine)
        image = copy_database(engine, tmp_path / "backup" / "image.db")
        assert image.is_file()
        assert looks_like_sqlite(image)
        assert image.read_bytes()[: len(SQLITE_MAGIC)] == SQLITE_MAGIC

    def test_backup_image_opens_and_is_internally_sound(
        self, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        state_a(engine)
        image = copy_database(engine, tmp_path / "image.db")
        reopened = create_persistence_engine(sqlite_url(image))
        try:
            assert integrity_check(reopened) == "ok"
        finally:
            reopened.dispose()

    def test_backup_captures_data_still_held_in_the_wal(
        self, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """The point of not copying the file.

        A committed row may still live in the `-wal` sidecar. Copying `live.db`
        alone can miss it; the online backup API reads through the WAL.
        """
        state_a(engine)
        image = copy_database(engine, tmp_path / "image.db")
        reopened = create_persistence_engine(sqlite_url(image))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                assert ProjectRegistry(session).get("prj-a") is not None
        finally:
            reopened.dispose()

    def test_wal_is_not_disabled_to_make_backup_work(self, engine: Engine,
                                                     tmp_path: pathlib.Path) -> None:
        state_a(engine)
        copy_database(engine, tmp_path / "image.db")
        with engine.connect() as connection:
            assert journal_mode(connection) == "wal"

    def test_digest_is_stable_and_distinguishes_content(
        self, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        state_a(engine)
        first = copy_database(engine, tmp_path / "one.db")
        assert file_digest(first) == file_digest(first)
        mutate_to_b(engine)
        second = copy_database(engine, tmp_path / "two.db")
        assert file_digest(first) != file_digest(second)


class TestRestoreMechanism:
    def test_a_then_b_then_restore_recovers_a(
        self, engine: Engine, live_path: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        """A -> backup -> B -> restore -> verify, at the mechanism level."""
        state_a(engine)
        image = copy_database(engine, tmp_path / "image.db")
        mutate_to_b(engine)

        with unit_of_work(create_session_factory(engine)) as session:
            registry = ProjectRegistry(session)
            assert registry.require("prj-a").lifecycle_state == "SPECIFIED"
            assert registry.get("prj-b") is not None

        restore_database(image, engine)
        engine.dispose()

        reopened = create_persistence_engine(sqlite_url(live_path))
        try:
            assert integrity_check(reopened) == "ok"
            with unit_of_work(create_session_factory(reopened)) as session:
                registry = ProjectRegistry(session)
                restored = registry.require("prj-a")
                assert restored.lifecycle_state == "DRAFT"
                assert registry.revision("rev-a") is not None
                assert registry.get("prj-b") is None
        finally:
            reopened.dispose()

    def test_restored_database_is_writable_and_still_wal(
        self, engine: Engine, live_path: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        state_a(engine)
        image = copy_database(engine, tmp_path / "image.db")
        restore_database(image, engine)
        engine.dispose()
        reopened = create_persistence_engine(sqlite_url(live_path))
        try:
            with reopened.connect() as connection:
                assert journal_mode(connection) == "wal"
            with unit_of_work(create_session_factory(reopened)) as session:
                ProjectRegistry(session).transition("prj-a", "SPECIFIED")
        finally:
            reopened.dispose()

    def test_constraints_survive_restore(
        self, engine: Engine, live_path: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        """Identity integrity must still be enforced after a restore."""
        from arkali.control.registry.project.errors import DuplicateIdentity

        state_a(engine)
        image = copy_database(engine, tmp_path / "image.db")
        restore_database(image, engine)
        engine.dispose()
        reopened = create_persistence_engine(sqlite_url(live_path))
        try:
            with unit_of_work(create_session_factory(reopened)) as session:
                with pytest.raises(DuplicateIdentity):
                    ProjectRegistry(session).create_project("prj-a", "Clash")
        finally:
            reopened.dispose()


class TestNegativeControls:
    def test_a_missing_image_is_refused(self, engine: Engine,
                                        tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileNotFoundError):
            restore_database(tmp_path / "absent.db", engine)

    def test_a_corrupt_image_is_refused_and_named_as_such(
        self, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: corrupt bytes must not restore."""
        state_a(engine)
        image = copy_database(engine, tmp_path / "image.db")
        raw = bytearray(image.read_bytes())
        raw[len(SQLITE_MAGIC) : len(SQLITE_MAGIC) + 512] = b"\x00" * 512
        image.write_bytes(bytes(raw))
        with pytest.raises(sqlite3.DatabaseError):
            restore_database(image, engine)

    def test_a_non_sqlite_file_is_refused(self, engine: Engine,
                                          tmp_path: pathlib.Path) -> None:
        bogus = tmp_path / "not-a-database.db"
        bogus.write_bytes(b"this is plainly not a database")
        assert not looks_like_sqlite(bogus)
        with pytest.raises(sqlite3.DatabaseError):
            restore_database(bogus, engine)

    def test_a_truncated_image_is_refused(self, engine: Engine,
                                          tmp_path: pathlib.Path) -> None:
        state_a(engine)
        image = copy_database(engine, tmp_path / "image.db")
        image.write_bytes(image.read_bytes()[:8])
        assert not looks_like_sqlite(image)
        with pytest.raises(sqlite3.DatabaseError):
            restore_database(image, engine)

    def test_a_failed_restore_leaves_the_source_usable(
        self, engine: Engine, live_path: pathlib.Path, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: a refused restore must not destroy the target."""
        state_a(engine)
        bogus = tmp_path / "bogus.db"
        bogus.write_bytes(b"not a database at all")
        with pytest.raises(sqlite3.DatabaseError):
            restore_database(bogus, engine)
        engine.dispose()
        reopened = create_persistence_engine(sqlite_url(live_path))
        try:
            assert integrity_check(reopened) == "ok"
            with unit_of_work(create_session_factory(reopened)) as session:
                assert ProjectRegistry(session).get("prj-a") is not None
        finally:
            reopened.dispose()

    def test_a_structural_check_is_not_an_integrity_claim(
        self, engine: Engine, tmp_path: pathlib.Path
    ) -> None:
        """NEGATIVE CONTROL: `looks_like_sqlite` must not be read as proof.

        A file carrying the SQLite header can still be unrestorable. If the
        header check were treated as validation, a corrupt backup would pass.
        """
        state_a(engine)
        image = copy_database(engine, tmp_path / "image.db")
        raw = bytearray(image.read_bytes())
        raw[len(SQLITE_MAGIC) : len(SQLITE_MAGIC) + 512] = b"\xff" * 512
        image.write_bytes(bytes(raw))
        assert looks_like_sqlite(image)
        with pytest.raises(sqlite3.DatabaseError):
            restore_database(image, engine)

    @pytest.mark.skipif(
        find_spec("psycopg") is None,
        reason="NOT_CONFIGURED: no PostgreSQL driver on this host, so a "
        "PostgreSQL engine cannot be constructed to refuse. The refusal path is "
        "reported rather than substituted; PostgreSQL backup is not claimed.",
    )
    def test_backup_of_a_non_sqlite_engine_is_refused_not_attempted(self) -> None:
        built = create_persistence_engine("postgresql+psycopg://a@localhost/b")
        try:
            with pytest.raises(ValueError, match="SQLite only"):
                copy_database(built, pathlib.Path("unused.db"))
        finally:
            built.dispose()

    def test_the_sqlite_only_guard_is_reachable(self, engine: Engine) -> None:
        """The guard exists and keys on dialect, provable without a driver."""
        from arkali.kernel.persistence import backup as backup_module

        assert engine.dialect.name == "sqlite"
        assert "is_sqlite" in backup_module._raw_sqlite_connection.__code__.co_names
