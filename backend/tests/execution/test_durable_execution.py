"""C-19 heartbeat, execution ownership and bounded retries. Phase 7 Package 2.

Real SQLite migrated by the real Alembic chain, a real PDP, a real PEP. The
clock is advanced explicitly by the test; nothing sleeps.

Timeout, cancellation, dead-lettering, idempotent execution and policy live in
`test_durable_execution_lifecycle.py` over the same harness — two modules
because `module <= 400 logical lines` is a real budget and ADR-0008 makes
decomposition the answer.

Scope note: no Phase 7 requirement is discharged. Pause/resume, the
`supports_pause` registry and the crash-recovery sweep are Package 3 and are
deliberately absent.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from arkali.execution.durable.errors import (
    NoOpenAttempt,
    RetryBudgetExhausted,
    StaleExecutionOwnership,
)
from arkali.execution.durable.records import JobExecutionAttempt
from tests.execution.durable_harness import (
    OWNER,
    START,
    MovableClock,
    Reopener,
    set_bound,
    submit,
)
from tests.execution.durable_harness import (  # noqa: F401 - fixtures by import
    clock,
    database_path,
    pdp,
    pep,
    reopen,
)


class TestHeartbeatAndOwnership:
    def test_an_attempt_persists_ownership_heartbeat_and_deadline(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            attempt = execution.begin_attempt("JOB-0001", OWNER)
            assert attempt.attempt == 1
            assert attempt.owner == OWNER
            assert attempt.started_at == START
            assert attempt.heartbeat_at == START
            assert attempt.deadline_at == START + dt.timedelta(seconds=300)
            assert attempt.is_open

        with reopen.session() as (execution, _):
            stored = execution.current_attempt("JOB-0001")
            assert stored is not None
            assert (stored.owner, stored.attempt) == (OWNER, 1)
            assert execution.jobs.require("JOB-0001").lifecycle_state == "RUNNING"

    def test_the_deadline_is_computed_from_the_injected_clock(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """`timed_out` measures ELAPSED WORK against `deadline_at`.

        Renamed from `heartbeat_expired` by the F-0036 repair: the function
        never consulted `heartbeat_at` and never did measure the heartbeat.
        Whether an execution has stopped reporting is `JobRecovery`.
        """
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            assert execution.timed_out("JOB-0001") is False
            clock.advance(299)
            assert execution.timed_out("JOB-0001") is False
            clock.advance(1)
            assert execution.timed_out("JOB-0001") is True

    def test_a_fresh_heartbeat_does_not_postpone_the_deadline(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """The F-0036 defect, stated as a permanent control.

        A worker that has heartbeated this very instant is still timed out once
        its deadline passes. If `timed_out` were measuring the heartbeat - as
        the name it shipped under promised - this would be False.
        """
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            clock.advance(300)
            execution.heartbeat("JOB-0001", OWNER)
            assert execution.timed_out("JOB-0001") is True

    def test_a_heartbeat_is_recorded_and_survives_reopen(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
        clock.advance(60)
        with reopen.session() as (execution, _):
            beat = execution.heartbeat("JOB-0001", OWNER)
            assert beat.heartbeat_at == START + dt.timedelta(seconds=60)
        with reopen.session() as (execution, _):
            stored = execution.current_attempt("JOB-0001")
            assert stored is not None
            assert stored.heartbeat_at.replace(tzinfo=dt.timezone.utc) == (
                START + dt.timedelta(seconds=60)
            )

    def test_a_stale_owner_cannot_heartbeat_or_close_the_attempt(
        self, reopen: Reopener
    ) -> None:
        """NEGATIVE CONTROL: a superseded execution cannot assert liveness."""
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            for call in ("heartbeat", "complete_attempt", "fail_attempt"):
                with pytest.raises(StaleExecutionOwnership):
                    getattr(execution, call)("JOB-0001", "worker-b")

    def test_a_closed_attempt_cannot_be_written_again(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.complete_attempt("JOB-0001", OWNER)
            with pytest.raises(NoOpenAttempt):
                execution.heartbeat("JOB-0001", OWNER)

    def test_a_second_attempt_cannot_open_while_one_is_open(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            with pytest.raises(StaleExecutionOwnership):
                execution.begin_attempt("JOB-0001", "worker-b")

    def test_an_owner_must_be_named(self, reopen: Reopener) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            with pytest.raises(StaleExecutionOwnership):
                execution.begin_attempt("JOB-0001", "   ")

    def test_reopen_preserves_the_facts_recovery_reads(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """Package 2 records the facts; acting on them is the sweep.

        The execution service still does not recover: opening a fresh engine
        over a job whose deadline passed long ago leaves it RUNNING with its
        attempt open. Only `JobRecovery` moves it.
        """
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
        clock.advance(1_000)
        with reopen.session() as (execution, _):
            assert execution.jobs.require("JOB-0001").lifecycle_state == "RUNNING"
            assert execution.timed_out("JOB-0001") is True
            attempt = execution.current_attempt("JOB-0001")
            assert attempt is not None and attempt.is_open


class TestBoundedRetries:
    def test_a_failure_with_budget_left_disposes_to_recoverable(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER, "boom")
            assert execution.jobs.require("JOB-0001").lifecycle_state == "RECOVERABLE"
            assert execution.retry_permitted("JOB-0001") is True

    def test_attempt_count_and_bound_survive_reopen(self, reopen: Reopener) -> None:
        with reopen.session() as (execution, session):
            submit(execution)
            set_bound(session, "JOB-0001", attempts=2, timeout=300)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)

        with reopen.session() as (execution, _):
            assert execution.attempt_count("JOB-0001") == 1
            assert execution.jobs.require("JOB-0001").max_attempts == 2
            assert execution.retry_permitted("JOB-0001") is True

    def test_retries_do_not_reset_by_restarting_the_process(
        self, reopen: Reopener
    ) -> None:
        """The count is rows. Nothing in memory carries it across a reopen."""
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)

        for _ in range(3):
            with reopen.session() as (execution, _):
                assert execution.attempt_count("JOB-0001") == 1
        assert reopen.opens == 4

    def test_exhausting_the_bound_dead_letters_through_the_machine(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, session):
            submit(execution)
            set_bound(session, "JOB-0001", attempts=2, timeout=300)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)
            # Package 3 owns RECOVERABLE -> RESUMING. The canonical machine
            # performs it here so a second attempt can be exercised at all;
            # Package 2's own code never asks for RESUMING.
            execution.jobs.transition("JOB-0001", "RESUMING")
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)
            assert execution.jobs.require("JOB-0001").lifecycle_state == "DEAD_LETTER"

        with reopen.session() as (execution, _):
            assert execution.jobs.require("JOB-0001").lifecycle_state == "DEAD_LETTER"
            assert execution.attempt_count("JOB-0001") == 2
            assert execution.retry_permitted("JOB-0001") is False

    def test_an_attempt_beyond_the_bound_is_refused(self, reopen: Reopener) -> None:
        with reopen.session() as (execution, session):
            submit(execution)
            set_bound(session, "JOB-0001", attempts=1, timeout=300)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)
            assert execution.jobs.require("JOB-0001").lifecycle_state == "DEAD_LETTER"
            with pytest.raises(RetryBudgetExhausted):
                execution.begin_attempt("JOB-0001", OWNER)

    def test_a_failed_transaction_consumes_no_attempt(self, reopen: Reopener) -> None:
        with pytest.raises(RuntimeError):
            with reopen.session() as (execution, _):
                submit(execution)
                execution.begin_attempt("JOB-0001", OWNER)
                raise RuntimeError("the caller failed after opening an attempt")

        with reopen.session() as (execution, session):
            assert execution.jobs.get("JOB-0001") is None
            assert session.execute(  # type: ignore[attr-defined]
                select(JobExecutionAttempt)
            ).scalars().all() == []

    def test_a_rolled_back_second_attempt_leaves_the_first_count(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)

        with pytest.raises(RuntimeError):
            with reopen.session() as (execution, _):
                execution.jobs.transition("JOB-0001", "RESUMING")
                execution.begin_attempt("JOB-0001", OWNER)
                raise RuntimeError("failed mid-attempt")

        with reopen.session() as (execution, _):
            assert execution.attempt_count("JOB-0001") == 1
            assert execution.jobs.require("JOB-0001").lifecycle_state == "RECOVERABLE"
