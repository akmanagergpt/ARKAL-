"""C-19 job-type contract registry — the `ARK-REQ-0060` applicability data.

Real SQLite migrated by the real Alembic chain, a real PDP, a real PEP, an
injected clock. `reopen.recovery()` builds a NEW engine each time, so a value
read in one block and written in another came off the disk.

The requirement under test is not "a table exists". It is that the pause
applicability rule has exactly ONE mechanically evaluable answer, that the
answer is persisted, and that an absent declaration fails closed rather than
defaulting.
"""

from __future__ import annotations

import ast
import pathlib

import pytest
from sqlalchemy.exc import IntegrityError

from arkali.execution.durable.errors import (
    DuplicateJobType,
    InvalidJobIdentity,
    PauseNotSupported,
    UnknownJobType,
)
from arkali.execution.durable.records import JobTypeRecord
from arkali.execution.durable.recovery import JobRecovery
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from tests.execution.durable_harness import (  # noqa: F401 - fixtures
    JOB_TYPE,
    Reopener,
    clock,
    database_path,
    declare,
    denying_pep,
    pdp,
    pep,
    reopen,
    run,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
REGISTRY_SOURCE = REPO / "backend" / "arkali" / "execution" / "durable" / "job_type.py"


class TestJobTypeIdentity:
    def test_a_declared_type_is_persisted_and_survives_reopen(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
        with reopen.recovery() as (recovery, _):
            record = recovery.job_types.require(JOB_TYPE)
            assert record.job_type == JOB_TYPE
            assert record.supports_pause is True
        assert reopen.opens >= 2, "the two blocks did not use separate engines"

    def test_the_job_type_is_the_primary_key(self) -> None:
        primary = {c.name for c in JobTypeRecord.__table__.primary_key.columns}
        assert primary == {"job_type"}

    def test_a_duplicate_declaration_is_refused(self, reopen: Reopener) -> None:
        """NEGATIVE CONTROL. A second declaration would change the capability a
        job already in flight was admitted under."""
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            with pytest.raises(DuplicateJobType):
                declare(recovery, supports_pause=False)

    def test_the_duplicate_refusal_is_the_database_not_only_the_service(
        self, database_path: pathlib.Path, pep, clock  # noqa: ANN001
    ) -> None:
        """The guarantee is the primary key, not the service's lookup.

        Written past the service, straight through the mapped row, so what
        refuses is the constraint itself.
        """
        from arkali.kernel.persistence.engine import (
            create_persistence_engine,
            sqlite_url,
        )

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                JobRecovery(session, pep, clock).job_types.declare(
                    JOB_TYPE, supports_pause=True
                )
            with pytest.raises(IntegrityError):
                with unit_of_work(create_session_factory(engine)) as session:
                    session.add(
                        JobTypeRecord(
                            job_type=JOB_TYPE,
                            supports_pause=False,
                            registered_at=clock(),
                        )
                    )
        finally:
            engine.dispose()

    def test_an_empty_job_type_is_refused(self, reopen: Reopener) -> None:
        with reopen.recovery() as (recovery, _):
            with pytest.raises(InvalidJobIdentity):
                recovery.job_types.declare("   ", supports_pause=True)

    def test_a_declaration_does_not_leak_into_other_types(
        self, reopen: Reopener
    ) -> None:
        """Capability is per type. Declaring one must not answer for another."""
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            with pytest.raises(UnknownJobType):
                recovery.job_types.supports_pause("arkali.test.other")


class TestTheAnswerIsPersistedAndFailsClosed:
    def test_pause_support_is_read_from_the_stored_row(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=False)
        with reopen.recovery() as (recovery, _):
            assert recovery.job_types.supports_pause(JOB_TYPE) is False

    def test_an_undeclared_type_raises_rather_than_defaulting(
        self, reopen: Reopener
    ) -> None:
        """NEGATIVE CONTROL, and the fail-closed edge.

        An absent row is an unanswered question. Returning `False` would be a
        declaration nobody made, and returning `True` would grant a capability
        nobody declared - so neither is returned.
        """
        with reopen.recovery() as (recovery, _):
            with pytest.raises(UnknownJobType):
                recovery.job_types.supports_pause("arkali.test.never-declared")

    def test_a_job_of_an_undeclared_type_cannot_be_paused(
        self, reopen: Reopener
    ) -> None:
        """The fail-closed path reaching the operation it protects."""
        with reopen.recovery() as (recovery, _):
            run(recovery)
            with pytest.raises(UnknownJobType):
                recovery.pause("JOB-0001")
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "RUNNING"
            ), "a refused pause must leave the job exactly where it was"

    def test_the_answer_is_not_inferred_from_the_request_or_the_state(
        self,
    ) -> None:
        """STRUCTURAL. The registry reads its own row and nothing else.

        NEGATIVE CONTROL for the shape the defect would take: the capability
        being derived from a caller-supplied value, from the job's payload or
        from its lifecycle state. `supports_pause` must resolve through
        `require`, which queries the registry table.
        """
        tree = ast.parse(REGISTRY_SOURCE.read_text(encoding="utf-8"))
        method = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "supports_pause"
        )
        calls = {
            n.func.attr for n in ast.walk(method)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        }
        assert "require" in calls
        reads = {n.attr for n in ast.walk(method) if isinstance(n, ast.Attribute)}
        for forbidden in ("payload", "lifecycle_state", "request", "actor"):
            assert forbidden not in reads, (
                f"supports_pause reads {forbidden!r}; the answer must come "
                "from the persisted declaration alone"
            )

    def test_the_registry_declares_no_scheduling_capability(self) -> None:
        """It is a durability capability registry, not a worker registry."""
        columns = {c.name for c in JobTypeRecord.__table__.columns}
        assert columns == {"job_type", "supports_pause", "registered_at"}


class TestTheRegistryIsGoverned:
    def test_a_denied_policy_prevents_the_declaration(
        self, tmp_path: pathlib.Path, database_path: pathlib.Path, clock  # noqa: ANN001
    ) -> None:
        """A REAL PDP over a denying authority map. Nothing is written."""
        from arkali.kernel.persistence.engine import (
            create_persistence_engine,
            sqlite_url,
        )

        denied = denying_pep(tmp_path / "denied")
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with pytest.raises(Exception) as refusal:
                with unit_of_work(create_session_factory(engine)) as session:
                    JobRecovery(session, denied, clock).job_types.declare(
                        JOB_TYPE, supports_pause=True
                    )
            assert "WRITE_WORKSPACE_FILE" in str(refusal.value)
            with unit_of_work(create_session_factory(engine)) as session:
                assert (
                    session.get(JobTypeRecord, JOB_TYPE) is None
                ), "a denied declaration left a row behind"
        finally:
            engine.dispose()

    def test_pause_is_refused_for_a_type_that_declares_no_support(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=False)
            run(recovery)
            with pytest.raises(PauseNotSupported):
                recovery.pause("JOB-0001")
