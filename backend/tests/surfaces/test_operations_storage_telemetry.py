"""C-34 storage telemetry (ARK-REQ-0168): real SQLite integrity/size, composed
from `kernel.persistence.backup` unmodified.
"""

from __future__ import annotations

import pathlib

from arkali.kernel.contracts.honest_state import HonestState
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.surfaces.operations.storage_telemetry import observe_storage
from tests.surfaces.operations_harness import database_path  # noqa: F401


class TestStorageTelemetryIsReal:
    def test_a_real_migrated_database_is_reachable_with_a_real_size(
        self, database_path: pathlib.Path,
    ) -> None:
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            snapshot = observe_storage(engine)
        finally:
            engine.dispose()
        assert snapshot.database_reachable.state is HonestState.PASS
        assert snapshot.database_size_bytes.state is HonestState.PASS
        assert snapshot.database_size_bytes.value is not None
        assert snapshot.database_size_bytes.value > 0

    def test_an_in_memory_database_reports_size_as_not_applicable(self) -> None:
        engine = create_persistence_engine("sqlite:///:memory:")
        try:
            snapshot = observe_storage(engine)
        finally:
            engine.dispose()
        assert snapshot.database_size_bytes.state is HonestState.NOT_APPLICABLE
