"""WAL-safe SQLite backup and restore mechanics.

Owner: kernel.persistence. Implementation phase 5.

WHY THE MECHANIC LIVES HERE AND THE LIFECYCLE DOES NOT. `ARCHITECTURE.md`
section 3 assigns "DB engine, session, migration runner" to this context, and
ADR-0006 confines engine-specific code to it. Taking a transactionally coherent
image of a SQLite database is engine-specific by nature. The *lifecycle* -
manifest, integrity, verification and the BackupRestore state machine - is owned
by `lifecycle.recovery` and is deliberately absent from this module. Nothing
here decides whether a backup is verified; this module only moves bytes
correctly.

NOT A FILE COPY. `sqlite3.Connection.backup` uses SQLite's online backup API,
which reads through the WAL and produces a consistent image of a database that
may be open and mid-transaction. Copying the `.db` file while WAL is enabled can
capture a torn image whose committed data lives in an uncopied `-wal` sidecar.
WAL is therefore never disabled to make backup work - the mechanism is chosen to
work with it.

VERIFICATION IS NOT CLAIMED HERE. `ARK-REQ-0335` requires a backup to be proven
by an actual restore. This module provides the two halves; proving them is
`lifecycle.recovery`'s obligation and is not discharged by anything in this file.
"""

from __future__ import annotations

import hashlib
import pathlib
import sqlite3
from typing import Final

from sqlalchemy import Engine
from sqlalchemy.pool import PoolProxiedConnection

from arkali.kernel.persistence.engine import is_sqlite

#: Read in bounded chunks so a large database does not have to fit in memory.
_DIGEST_CHUNK: Final[int] = 1 << 16

#: SQLite writes this 16-byte header at the start of every database file.
SQLITE_MAGIC: Final[bytes] = b"SQLite format 3\x00"


def _raw_sqlite_connection(
    engine: Engine,
) -> tuple[PoolProxiedConnection, sqlite3.Connection]:
    """The live DBAPI connection behind an engine, with its owning wrapper."""
    if not is_sqlite(engine):
        raise ValueError(
            f"online backup is implemented for SQLite only; this engine is "
            f"{engine.dialect.name!r}. PostgreSQL backup is not claimed."
        )
    wrapper = engine.raw_connection()
    driver = wrapper.driver_connection
    if not isinstance(driver, sqlite3.Connection):
        raise TypeError("engine does not expose a sqlite3 connection")
    return wrapper, driver


def copy_database(engine: Engine, destination: pathlib.Path) -> pathlib.Path:
    """Write a transactionally coherent image of `engine`'s database.

    Uses SQLite's online backup API, so the source may be open, in WAL mode and
    mid-transaction. The destination is created or overwritten.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    wrapper, source = _raw_sqlite_connection(engine)
    target = sqlite3.connect(str(destination))
    try:
        source.backup(target)
    finally:
        target.close()
        wrapper.close()
    return destination


def restore_database(image: pathlib.Path, engine: Engine) -> None:
    """Replace the contents of `engine`'s database with `image`.

    The inverse of `copy_database`, and equally not a file copy: the image is
    opened as a SQLite database and written through the backup API, so a
    truncated or non-SQLite file fails here instead of producing a target that
    looks restored. The caller is responsible for having quiesced the target.
    """
    if not image.is_file():
        raise FileNotFoundError(f"no backup image at {image}")
    wrapper, target = _raw_sqlite_connection(engine)
    source = sqlite3.connect(f"file:{image.as_posix()}?mode=ro", uri=True)
    try:
        source.backup(target)
    finally:
        source.close()
        wrapper.close()


def file_digest(path: pathlib.Path) -> str:
    """SHA-256 of a file, for integrity comparison. Streamed, not buffered whole."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_DIGEST_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def looks_like_sqlite(path: pathlib.Path) -> bool:
    """Whether a file carries the SQLite header.

    A cheap structural check only. It is NOT an integrity check and NOT proof
    that a backup is restorable - only an actual restore proves that.
    """
    if not path.is_file() or path.stat().st_size < len(SQLITE_MAGIC):
        return False
    with path.open("rb") as handle:
        return handle.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC


def integrity_check(engine: Engine) -> str:
    """SQLite's own `PRAGMA integrity_check`, read back as its raw answer.

    Returns `ok` for a sound database. The value is the database's answer, not a
    boolean this module computed, so a caller cannot mistake "the call
    succeeded" for "the database is sound".
    """
    wrapper, connection = _raw_sqlite_connection(engine)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    finally:
        wrapper.close()
    return str(row[0]).lower() if row else "unknown"
