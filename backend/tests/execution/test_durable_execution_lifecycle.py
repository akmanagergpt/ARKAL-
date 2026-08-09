"""C-19 timeout, cancellation, dead-letter, idempotent execution and policy.

Phase 7 Package 2, second half, over the same harness as
`test_durable_execution.py`. The clock is advanced explicitly; nothing sleeps.

Scope note: no Phase 7 requirement is discharged.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from sqlalchemy import select

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.execution.durable.errors import (
    DeadlineNotReached,
    RetryBudgetExhausted,
    UnknownJob,
)
from arkali.execution.durable.execution import JobExecution
from arkali.execution.durable.job_state_machine import DEFINITION
from arkali.execution.durable.job_store import ACTOR
from arkali.execution.durable.records import DurableJobRecord, JobExecutionAttempt
from arkali.kernel.contracts.state_machine_errors import (
    IllegalTransition,
    TerminalStateEscape,
)
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from tests.execution.durable_harness import (
    OWNER,
    START,
    MovableClock,
    Reopener,
    denying_pep,
    set_bound,
    submission,
    submit,
)
from tests.execution.durable_harness import (  # noqa: F401 - fixtures by import
    clock,
    database_path,
    pdp,
    pep,
    reopen,
)


class TestTimeout:
    def test_an_unexpired_attempt_cannot_be_timed_out(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            clock.advance(10)
            assert execution.timed_out("JOB-0001") is False
            with pytest.raises(DeadlineNotReached):
                execution.time_out("JOB-0001")
            assert execution.jobs.require("JOB-0001").lifecycle_state == "RUNNING"

    def test_an_expired_attempt_times_out_through_canonical_transitions(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            clock.advance(301)
            attempt = execution.time_out("JOB-0001")
            assert attempt.outcome == "RECOVERABLE"
            assert execution.jobs.require("JOB-0001").lifecycle_state == "RECOVERABLE"

    def test_the_deadline_basis_is_not_reset_by_a_restart(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """An absolute instant survives; a remaining-duration counter would not."""
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
        clock.advance(299)
        with reopen.session() as (execution, _):
            assert execution.timed_out("JOB-0001") is False
        clock.advance(2)
        with reopen.session() as (execution, _):
            assert execution.timed_out("JOB-0001") is True
            stored = execution.current_attempt("JOB-0001")
            assert stored is not None
            assert stored.deadline_at.replace(tzinfo=dt.timezone.utc) == (
                START + dt.timedelta(seconds=300)
            )

    def test_timing_out_twice_is_idempotent(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            clock.advance(301)
            first = execution.time_out("JOB-0001")
            again = execution.time_out("JOB-0001")
            assert (again.attempt, again.outcome) == (first.attempt, first.outcome)
            assert execution.attempt_count("JOB-0001") == 1
            assert execution.jobs.require("JOB-0001").lifecycle_state == "RECOVERABLE"

    def test_a_recorded_timeout_bound_is_honoured(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, session):
            submit(execution)
            set_bound(session, "JOB-0001", attempts=3, timeout=30)
            attempt = execution.begin_attempt("JOB-0001", OWNER)
            assert attempt.deadline_at == START + dt.timedelta(seconds=30)


class TestCancellation:
    def test_a_running_job_can_be_cancelled_and_the_attempt_closes(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.cancel("JOB-0001", "operator asked")

        with reopen.session() as (execution, _):
            assert execution.jobs.require("JOB-0001").lifecycle_state == "CANCELLED"
            assert execution.current_attempt("JOB-0001") is None
            (attempt,) = execution.attempts("JOB-0001")
            assert attempt.outcome == "CANCELLED"
            assert attempt.detail == "operator asked"

    def test_a_queued_job_cannot_be_cancelled(self, reopen: Reopener) -> None:
        """NEGATIVE CONTROL: the machine declares no QUEUED -> CANCELLED edge."""
        assert ("QUEUED", "CANCELLED") not in DEFINITION.transition_set
        with reopen.session() as (execution, _):
            submit(execution)
            with pytest.raises(IllegalTransition):
                execution.cancel("JOB-0001")

    def test_a_cancelled_job_cannot_be_cancelled_again(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.cancel("JOB-0001")
            with pytest.raises(TerminalStateEscape):
                execution.cancel("JOB-0001")

    def test_a_refused_cancellation_mutates_no_attempt_state(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.complete_attempt("JOB-0001", OWNER)

        with pytest.raises(TerminalStateEscape):
            with reopen.session() as (execution, _):
                execution.cancel("JOB-0001")

        with reopen.session() as (execution, _):
            (attempt,) = execution.attempts("JOB-0001")
            assert attempt.outcome == "SUCCEEDED"
            assert execution.jobs.require("JOB-0001").lifecycle_state == "SUCCEEDED"


class TestDeadLetter:
    def test_dead_letter_has_no_outgoing_transition(self) -> None:
        """Structural: a dead-lettered job cannot be retried at all."""
        assert [t for s, t in DEFINITION.transitions if s == "DEAD_LETTER"] == []
        assert "DEAD_LETTER" in DEFINITION.terminal

    def test_dead_letter_survives_reopen_and_refuses_further_execution(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, session):
            submit(execution)
            set_bound(session, "JOB-0001", attempts=1, timeout=300)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)

        with reopen.session() as (execution, _):
            assert execution.jobs.require("JOB-0001").lifecycle_state == "DEAD_LETTER"
            with pytest.raises(RetryBudgetExhausted):
                execution.begin_attempt("JOB-0001", OWNER)

    def test_retry_exhaustion_cannot_bypass_the_machine(
        self, reopen: Reopener
    ) -> None:
        """Dead-lettering is reached only via FAILED, never written directly."""
        with reopen.session() as (execution, session):
            submit(execution)
            set_bound(session, "JOB-0001", attempts=1, timeout=300)
            with pytest.raises(IllegalTransition):
                execution.jobs.transition("JOB-0001", "DEAD_LETTER")
            assert execution.jobs.require("JOB-0001").lifecycle_state == "QUEUED"


class TestIdempotentExecution:
    def test_a_repeated_submission_continues_one_attempt_history(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)

        with reopen.session() as (execution, session):
            again = submit(execution, job_id="JOB-OTHER")
            assert again.job_id == "JOB-0001"
            assert execution.attempt_count("JOB-0001") == 1
            rows = session.execute(  # type: ignore[attr-defined]
                select(DurableJobRecord)
            ).scalars().all()
            assert len(rows) == 1

    def test_the_primary_key_is_the_concurrency_backstop(
        self, reopen: Reopener
    ) -> None:
        """Bypassing the service still cannot produce two rows for one attempt."""
        from sqlalchemy.exc import IntegrityError

        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)

        with pytest.raises(IntegrityError):
            with reopen.session() as (_execution, session):
                session.add(  # type: ignore[attr-defined]
                    JobExecutionAttempt(
                        job_id="JOB-0001", attempt=1, owner="worker-b",
                        started_at=START, heartbeat_at=START,
                        deadline_at=START + dt.timedelta(seconds=1),
                    )
                )
                session.flush()  # type: ignore[attr-defined]

        with reopen.session() as (execution, _):
            (attempt,) = execution.attempts("JOB-0001")
            assert attempt.owner == OWNER

    def test_an_attempt_cannot_reference_a_job_that_does_not_exist(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            with pytest.raises(UnknownJob):
                execution.begin_attempt("JOB-absent", OWNER)

    def test_reopening_does_not_create_a_second_execution_identity(
        self, reopen: Reopener
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
        for _ in range(3):
            with reopen.session() as (execution, _):
                current = execution.current_attempt("JOB-0001")
                assert current is not None
                assert (current.job_id, current.attempt) == ("JOB-0001", 1)
        with reopen.session() as (execution, _):
            assert execution.attempt_count("JOB-0001") == 1


class TestPolicyEnforcement:
    def test_every_execution_operation_is_audited(
        self, reopen: Reopener, pep: PolicyEnforcementPoint
    ) -> None:
        with reopen.session() as (execution, _):
            submit(execution)
            execution.begin_attempt("JOB-0001", OWNER)
            execution.heartbeat("JOB-0001", OWNER)
            execution.fail_attempt("JOB-0001", OWNER)

        trail = pep.audit_trail
        assert trail
        assert {record.actor for record in trail} == {ACTOR}
        assert {record.operation_class for record in trail} == {
            "READ_FILE", "WRITE_WORKSPACE_FILE"
        }

    def test_a_denied_decision_leaves_durable_state_unchanged(
        self, tmp_path: pathlib.Path, database_path: pathlib.Path,
        pep: PolicyEnforcementPoint, clock: MovableClock
    ) -> None:
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                JobExecution(session, pep, clock).jobs.submit(submission())
        finally:
            engine.dispose()

        denying = denying_pep(tmp_path / "denying_repo")
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with pytest.raises(PolicyDenied):
                with unit_of_work(create_session_factory(engine)) as session:
                    JobExecution(session, denying, clock).begin_attempt(
                        "JOB-0001", OWNER
                    )
        finally:
            engine.dispose()

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                execution = JobExecution(session, pep, clock)
                assert execution.attempt_count("JOB-0001") == 0
                assert execution.jobs.require("JOB-0001").lifecycle_state == "QUEUED"
        finally:
            engine.dispose()
