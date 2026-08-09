"""C-03 engine foundation — SQLite+WAL local-first (ARK-REQ-0011).

Owner: kernel.persistence. Implementation phase 5; the contract this satisfies
was defined at Phase 2 in `schema_contract.py`.

WHY THIS MODULE IMPORTS NO OTHER ARKALI CONTEXT. `kernel.persistence` and
`kernel.contracts` are both layer rank 0, `allow_same_layer` is false and no
sibling edge between them is declared, so the canonical error taxonomy is not
reachable from here. Configuration faults therefore raise built-in exceptions
rather than `ArkaliError` subclasses. The alternative - declaring a sibling edge
- would widen the accepted architecture to fit an implementation, which is
exactly what ERR-003 and the F-0028 repair refused to do.

WAL IS APPLIED, THEN READ BACK. `configure_sqlite_connection` issues the pragma
and `journal_mode` re-reads it from a live connection, so the phase evidence is
the database's own answer and never the fact that a statement was executed.
SQLite ignores a WAL request for an in-memory database and answers `memory`;
that is a real answer and is reported as such rather than smoothed into PASS.
"""

from __future__ import annotations

import pathlib
import sqlite3
from typing import Any, Final

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import Connection

#: Local-first default. Callers may pass any SQLAlchemy URL; only the pragmas
#: below are SQLite-specific, and they are applied only to a SQLite dialect.
SQLITE_DRIVER: Final[str] = "sqlite+pysqlite"

#: Applied on every SQLite connection, in order.
#:
#: `journal_mode=WAL` is ARK-REQ-0011. `foreign_keys=ON` is required because
#: SQLite disables constraint enforcement by default, which would make a
#: referential test pass for the wrong reason. `synchronous=FULL` is what makes
#: the close/reopen durability evidence meaningful rather than incidental.
SQLITE_PRAGMAS: Final[tuple[tuple[str, str], ...]] = (
    ("journal_mode", "WAL"),
    ("foreign_keys", "ON"),
    ("synchronous", "FULL"),
)


def sqlite_url(database_path: pathlib.Path) -> str:
    """A local-first SQLite URL for a real file. Never an in-memory database."""
    return f"{SQLITE_DRIVER}:///{database_path.as_posix()}"


def is_sqlite(engine: Engine) -> bool:
    """Dialect probe. The only place engine identity is branched on."""
    return engine.dialect.name == "sqlite"


def configure_sqlite_connection(dbapi_connection: Any, _record: Any) -> None:
    """Apply the SQLite pragmas to one raw DBAPI connection."""
    cursor = dbapi_connection.cursor()
    try:
        for pragma, value in SQLITE_PRAGMAS:
            cursor.execute(f"PRAGMA {pragma}={value}")
    finally:
        cursor.close()


def create_persistence_engine(url: str, *, echo: bool = False) -> Engine:
    """The one place an engine is constructed (ARK-REQ-0012).

    Engine-neutral by construction: a non-SQLite URL yields an ordinary engine
    with no pragma listener attached, so a PostgreSQL adapter needs no change
    here. Verified operation on PostgreSQL is deliberately not claimed - ADR-0006
    registers the abstraction, not the runtime.
    """
    if not url.strip():
        raise ValueError("database URL is empty; refusing to construct an engine")
    engine = create_engine(url, echo=echo, future=True)
    if is_sqlite(engine):
        event.listen(engine, "connect", configure_sqlite_connection)
    return engine


def journal_mode(connection: Connection) -> str:
    """The journal mode SQLite actually reports, read back from the connection.

    Evidence for ARK-REQ-0011. A caller cannot substitute the expected answer:
    the value comes from the database, and an in-memory database truthfully
    answers `memory` rather than `wal`.
    """
    result = connection.execute(text("PRAGMA journal_mode")).scalar_one()
    return str(result).lower()


def pragma_value(connection: Connection, pragma: str) -> str:
    """Read back any SQLite pragma. Used by the persistence evidence tests."""
    if pragma not in {name for name, _ in SQLITE_PRAGMAS}:
        raise ValueError(f"{pragma!r} is not a configured persistence pragma")
    result = connection.execute(text(f"PRAGMA {pragma}")).scalar_one()
    return str(result).lower()


def wal_sidecar_paths(database_path: pathlib.Path) -> tuple[pathlib.Path, ...]:
    """The files WAL creates beside the database.

    Named here so the durability evidence can assert WAL is real on disk, and so
    `.gitignore` coverage for them is checkable rather than assumed.
    """
    return (
        database_path.with_name(database_path.name + "-wal"),
        database_path.with_name(database_path.name + "-shm"),
    )


def sqlite_library_version() -> str:
    """The SQLite library actually linked, recorded rather than assumed."""
    return sqlite3.sqlite_version
