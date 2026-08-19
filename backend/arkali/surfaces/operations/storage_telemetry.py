"""C-34 durable-store telemetry: DB/storage (MANDATORY, part of ARK-REQ-0168's
named dimensions).

Owner: `surfaces.operations`.

COMPOSES `kernel.persistence`, NEVER RE-IMPLEMENTS THE CHECK. `integrity_check`
already runs SQLite's own `PRAGMA integrity_check` and returns its raw answer
(Phase 5/20); this module reads that answer back rather than inventing a
second reachability probe. `is_sqlite` is the same reused, unmodified guard
`backup.py` itself uses before touching engine internals - imported from its
real home (`engine.py`) rather than through `backup.py`'s own unexported
transitive import, which mypy strict mode correctly refuses to re-export.
"""

from __future__ import annotations

import pathlib

from sqlalchemy import Engine

from arkali.kernel.persistence.backup import integrity_check
from arkali.kernel.persistence.engine import is_sqlite
from arkali.surfaces.operations.contracts import DimensionReading, StorageSnapshot

_OK = "ok"


def observe_storage(engine: Engine) -> StorageSnapshot:
    """The real, live durable-store dimensions, re-derived on every call."""
    if not is_sqlite(engine):
        detail = f"non-SQLite backend {engine.url.get_backend_name()!r}; PostgreSQL-specific storage telemetry is NOT_CONFIGURED on this host"
        return StorageSnapshot(
            database_reachable=DimensionReading.not_configured("database_reachable", detail),
            database_size_bytes=DimensionReading.not_configured("database_size_bytes", detail),
        )

    answer = integrity_check(engine)
    reachable = (
        DimensionReading.real("database_reachable", 1.0, f"PRAGMA integrity_check -> {answer!r}")
        if answer == _OK
        else DimensionReading.not_configured(
            "database_reachable", f"PRAGMA integrity_check -> {answer!r}, not {_OK!r}"
        )
    )

    database_path = engine.url.database
    if not database_path or database_path == ":memory:":
        size = DimensionReading.not_applicable(
            "database_size_bytes", "in-memory SQLite database has no file size"
        )
    else:
        path = pathlib.Path(database_path)
        size = (
            DimensionReading.real(
                "database_size_bytes", float(path.stat().st_size), f"real file size of {path}"
            )
            if path.is_file()
            else DimensionReading.not_configured(
                "database_size_bytes", f"database file {path} does not exist on disk"
            )
        )

    return StorageSnapshot(database_reachable=reachable, database_size_bytes=size)


__all__ = ["observe_storage"]
