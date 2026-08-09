"""C-19 pause and resume — `PAUSED -> RESUMING -> RUNNING`.

Real SQLite, real Alembic chain, real PDP, real PEP, injected clock. Nothing
sleeps.

The paths asserted here are read off the canonical `Job` relation in
`TestThePathsComeFromTheCanonicalRelation` before any behaviour is exercised, so
these are not four tests agreeing with each other about an arrangement this
package invented.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from arkali.execution.durable.errors import PauseNotSupported
from arkali.execution.durable.job_state_machine import DEFINITION
from arkali.execution.durable.records import DurableJobRecord
from arkali.execution.durable.recovery import JobRecovery
from arkali.kernel.contracts.state_machine import IllegalTransition
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from tests.execution.durable_harness import (  # noqa: F401 - fixtures
    OWNER,
    START,
    MovableClock,
    Reopener,
    clock,
    database_path,
    declare,
    denying_pep,
    pdp,
    pep,
    reopen,
    run,
    set_bound,
    submit,
)


class TestThePathsComeFromTheCanonicalRelation:
    """Derived first. Everything below depends on these being what they are."""

    def test_pause_and_resume_are_declared_edges(self) -> None:
        declared = DEFINITION.transition_set
        assert ("RUNNING", "PAUSED") in declared
        assert ("PAUSED", "RESUMING") in declared
        assert ("RESUMING", "RUNNING") in declared

    def test_pause_is_reachable_only_from_running(self) -> None:
        sources = {s for s, t in DEFINITION.transitions if t == "PAUSED"}
        assert sources == {"RUNNING"}

    def test_a_paused_job_can_only_go_to_resuming(self) -> None:
        assert {t for s, t in DEFINITION.transitions if s == "PAUSED"} == {"RESUMING"}

    def test_resuming_cannot_be_skipped(self) -> None:
        """NEGATIVE: `PAUSED -> RUNNING` is not an edge, so resume cannot be
        one move however it is implemented."""
        assert ("PAUSED", "RUNNING") not in DEFINITION.transition_set


class TestPause:
    def test_a_pausable_job_enters_paused_through_the_machine(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            record = recovery.pause("JOB-0001")
            assert record.lifecycle_state == "PAUSED"

    def test_paused_state_survives_engine_disposal_and_reopen(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            recovery.pause("JOB-0001")
        with reopen.recovery() as (recovery, _):
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "PAUSED"
            )

    def test_a_type_that_does_not_declare_support_is_refused(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=False)
            run(recovery)
            with pytest.raises(PauseNotSupported):
                recovery.pause("JOB-0001")

    def test_a_refused_pause_changes_nothing_durable(
        self, reopen: Reopener
    ) -> None:
        """NEGATIVE CONTROL over every durable fact, not just the state."""
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=False)
            run(recovery)
            recovery.execution.jobs.checkpoint("JOB-0001", {"at": 1})
            with pytest.raises(PauseNotSupported):
                recovery.pause("JOB-0001")
        with reopen.recovery() as (recovery, _):
            job = recovery.execution.jobs.require("JOB-0001")
            assert job.lifecycle_state == "RUNNING"
            assert recovery.execution.attempt_count("JOB-0001") == 1
            attempt = recovery.execution.current_attempt("JOB-0001")
            assert attempt is not None and attempt.is_open
            assert attempt.owner == OWNER
            assert len(recovery.execution.jobs.checkpoints("JOB-0001")) == 1

    def test_pause_from_an_illegal_source_state_is_refused(
        self, reopen: Reopener
    ) -> None:
        """A QUEUED job has never run; `RUNNING -> PAUSED` is the only edge."""
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            submit(recovery.execution)
            with pytest.raises(IllegalTransition):
                recovery.pause("JOB-0001")
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "QUEUED"
            )

    def test_a_terminal_job_cannot_escape_through_pause(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            recovery.execution.complete_attempt("JOB-0001", OWNER)
            with pytest.raises(Exception) as refusal:
                recovery.pause("JOB-0001")
            assert type(refusal.value).__name__ in {
                "TerminalStateEscape", "IllegalTransition"
            }
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "SUCCEEDED"
            )

    def test_pause_leaves_the_attempt_open_under_the_same_owner(
        self, reopen: Reopener
    ) -> None:
        """The deliberate design: suspended is not lost.

        Closing the attempt would consume a retry, and pausing is not failing.
        """
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            before = recovery.execution.current_attempt("JOB-0001")
            assert before is not None
            deadline, owner = before.deadline_at, before.owner
            recovery.pause("JOB-0001")
        with reopen.recovery() as (recovery, _):
            after = recovery.execution.current_attempt("JOB-0001")
            assert after is not None and after.is_open
            assert (after.owner, after.deadline_at) == (owner, deadline)
            assert recovery.execution.attempt_count("JOB-0001") == 1

    def test_a_denied_policy_prevents_the_pause(
        self, tmp_path: pathlib.Path, database_path: pathlib.Path, pep, clock  # noqa: ANN001
    ) -> None:
        from arkali.kernel.persistence.engine import (
            create_persistence_engine,
            sqlite_url,
        )

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                allowed = JobRecovery(session, pep, clock)
                declare(allowed, supports_pause=True)
                run(allowed)
            denied = denying_pep(tmp_path / "denied")
            with pytest.raises(Exception) as refusal:
                with unit_of_work(create_session_factory(engine)) as session:
                    JobRecovery(session, denied, clock).pause("JOB-0001")
            assert "WRITE_WORKSPACE_FILE" in str(refusal.value)
            with unit_of_work(create_session_factory(engine)) as session:
                stored = session.get(DurableJobRecord, "JOB-0001")
                assert stored is not None
                assert stored.lifecycle_state == "RUNNING"
        finally:
            engine.dispose()


class TestResume:
    def test_resume_passes_through_resuming_and_returns_to_running(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            recovery.pause("JOB-0001")
            record = recovery.resume("JOB-0001")
            assert record.lifecycle_state == "RUNNING"

    def test_resume_is_two_machine_evaluated_moves_not_one(
        self, reopen: Reopener
    ) -> None:
        """`RESUMING` is a real state the job passes through.

        Proven by the relation rather than by observation: `PAUSED -> RUNNING`
        is not declared, so a resume that ended in RUNNING must have gone
        through the only declared route.
        """
        assert ("PAUSED", "RUNNING") not in DEFINITION.transition_set
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            recovery.pause("JOB-0001")
            recovery.resume("JOB-0001")
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "RUNNING"
            )

    def test_resume_without_pause_is_refused(self, reopen: Reopener) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            with pytest.raises(IllegalTransition):
                recovery.resume("JOB-0001")
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "RUNNING"
            )

    def test_a_non_pausable_type_cannot_use_the_resume_path(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=False)
            run(recovery)
            with pytest.raises(PauseNotSupported):
                recovery.resume("JOB-0001")

    def test_resume_preserves_every_durable_fact(
        self, reopen: Reopener
    ) -> None:
        """The whole regression surface in one journey, across four engines."""
        with reopen.recovery() as (recovery, session):
            declare(recovery, supports_pause=True)
            run(recovery)
            set_bound(session, "JOB-0001", attempts=5, timeout=900)
            recovery.execution.jobs.checkpoint("JOB-0001", {"step": 1})
            recovery.execution.jobs.checkpoint("JOB-0001", {"step": 2})
            before = recovery.execution.current_attempt("JOB-0001")
            assert before is not None
            snapshot = (before.attempt, before.owner, before.started_at,
                        before.deadline_at)
        with reopen.recovery() as (recovery, _):
            recovery.pause("JOB-0001")
        with reopen.recovery() as (recovery, _):
            recovery.resume("JOB-0001")
        with reopen.recovery() as (recovery, _):
            job = recovery.execution.jobs.require("JOB-0001")
            after = recovery.execution.current_attempt("JOB-0001")
            assert after is not None
            assert (after.attempt, after.owner) == snapshot[:2]
            assert after.started_at == snapshot[2]
            assert after.deadline_at == snapshot[3], (
                "resume reset the timeout basis the job was admitted under"
            )
            assert recovery.execution.attempt_count("JOB-0001") == 1
            assert job.max_attempts == 5
            assert job.attempt_timeout_seconds == 900
            assert job.idempotency_key == "key-1"
            assert job.job_id == "JOB-0001"
            assert [c.sequence for c in recovery.execution.jobs.checkpoints(
                "JOB-0001"
            )] == [1, 2]

    def test_repeated_pause_resume_creates_no_duplicate_attempt_identity(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            for _cycle in range(3):
                recovery.pause("JOB-0001")
                recovery.resume("JOB-0001")
            attempts = recovery.execution.attempts("JOB-0001")
            assert [a.attempt for a in attempts] == [1]
            assert recovery.execution.attempt_count("JOB-0001") == 1

    def test_a_stale_owner_cannot_act_on_the_resumed_attempt(
        self, reopen: Reopener
    ) -> None:
        """NEGATIVE CONTROL: resume does not hand the attempt to whoever asks."""
        from arkali.execution.durable.errors import StaleExecutionOwnership

        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            recovery.pause("JOB-0001")
            recovery.resume("JOB-0001")
            for call in ("heartbeat", "complete_attempt", "fail_attempt"):
                with pytest.raises(StaleExecutionOwnership):
                    getattr(recovery.execution, call)("JOB-0001", "worker-b")

    def test_a_long_pause_does_not_extend_the_deadline(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """The timeout basis is absolute and pause does not move it.

        A job paused past its attempt timeout is timed out on resume by the
        ordinary Package 2 rule - not given a fresh window.
        """
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            recovery.pause("JOB-0001")
        clock.advance(10_000)
        with reopen.recovery() as (recovery, _):
            recovery.resume("JOB-0001")
            assert recovery.execution.timed_out("JOB-0001") is True
            attempt = recovery.execution.current_attempt("JOB-0001")
            assert attempt is not None
            assert attempt.deadline_at.replace(tzinfo=dt.timezone.utc) == (
                START + dt.timedelta(seconds=300)
            )

    def test_a_denied_policy_prevents_the_resume(
        self, tmp_path: pathlib.Path, database_path: pathlib.Path, pep, clock  # noqa: ANN001
    ) -> None:
        from arkali.kernel.persistence.engine import (
            create_persistence_engine,
            sqlite_url,
        )

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                allowed = JobRecovery(session, pep, clock)
                declare(allowed, supports_pause=True)
                run(allowed)
                allowed.pause("JOB-0001")
            denied = denying_pep(tmp_path / "denied")
            with pytest.raises(Exception) as refusal:
                with unit_of_work(create_session_factory(engine)) as session:
                    JobRecovery(session, denied, clock).resume("JOB-0001")
            assert "WRITE_WORKSPACE_FILE" in str(refusal.value)
            with unit_of_work(create_session_factory(engine)) as session:
                stored = session.get(DurableJobRecord, "JOB-0001")
                assert stored is not None
                assert stored.lifecycle_state == "PAUSED", (
                    "a denied resume left the job somewhere in between"
                )
        finally:
            engine.dispose()
