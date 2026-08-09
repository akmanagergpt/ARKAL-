"""C-19 crash recovery — restart durability, the liveness edge, and regression.

Second module over the shared harness because `module <= 400 logical lines` is a
real architecture budget and ADR-0008 makes decomposition the answer rather than
an exception. The split is along a real seam, not an arbitrary line count:
`test_durable_recovery.py` asks whether the sweep DECIDES correctly, and this
module asks whether that decision SURVIVES a restart and leaves Package 2 intact.

REAL FAULT INJECTION AT THE AVAILABLE TIER. A process crash is simulated by
disposing the engine mid-execution and never closing the attempt — the durable
equivalent of a worker vanishing. It is NOT the T12 chaos corpus, which is
Phase 31, and `ARK-REQ-0327` is not claimed here.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.execution.durable.errors import StaleExecutionOwnership
from arkali.execution.durable.records import DurableJobRecord
from arkali.execution.durable.recovery import JobRecovery
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from tests.execution.durable_harness import (  # noqa: F401 - fixtures
    OWNER,
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

#: Longer than the default heartbeat bound of 60s, shorter than the default
#: attempt deadline of 300s, so every assertion distinguishes the two.
SILENCE = 61
LIVE = 59

class TestTheLivenessBoundaryIsExact:
    """The edge itself, both sides, so neither test above rests on a guess.

    An off-by-one here is not cosmetic: on one side a live worker is declared
    crashed and has its execution taken away, on the other a genuinely dead one
    is left holding the job forever.
    """

    def test_the_last_live_instant_is_not_stale(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, session):
            run(recovery)
            set_bound(session, "JOB-0001", attempts=3, timeout=300, heartbeat=60)
            clock.advance(59)
            assert recovery.heartbeat_stale("JOB-0001") is False

    def test_the_bound_itself_is_stale(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, session):
            run(recovery)
            set_bound(session, "JOB-0001", attempts=3, timeout=300, heartbeat=60)
            clock.advance(60)
            assert recovery.heartbeat_stale("JOB-0001") is True


class TestTheHeartbeatTermIsNotTheDeadline:
    """F-0036: two different questions with two different persisted bases."""

    def test_a_silent_execution_is_recovered_long_before_its_deadline(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            assert recovery.execution.timed_out("JOB-0001") is False, (
                "the deadline has not passed; only the heartbeat has gone quiet"
            )
            assert recovery.heartbeat_stale("JOB-0001") is True
            assert recovery.recover_lost_executions() == ("JOB-0001",)

    def test_a_reporting_execution_past_its_deadline_is_not_stale(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """The mirror image, and the F-0036 defect in the other direction."""
        with reopen.recovery() as (recovery, _):
            run(recovery)
            for _beat in range(6):
                clock.advance(LIVE)
                recovery.execution.heartbeat("JOB-0001", OWNER)
            assert recovery.execution.timed_out("JOB-0001") is True
            assert recovery.heartbeat_stale("JOB-0001") is False
            assert recovery.recover_lost_executions() == ()

    def test_the_heartbeat_bound_is_recorded_on_the_job(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """A per-job term, so a restart cannot change the basis."""
        with reopen.recovery() as (recovery, session):
            run(recovery)
            set_bound(session, "JOB-0001", attempts=3, timeout=300, heartbeat=10)
        clock.advance(10)
        with reopen.recovery() as (recovery, _):
            assert recovery.execution.jobs.require(
                "JOB-0001"
            ).heartbeat_timeout_seconds == 10
            assert recovery.heartbeat_stale("JOB-0001") is True


class TestRestartRecoversFromDisk:
    def test_a_crashed_worker_is_recovered_by_a_completely_fresh_process(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """The restart proof, engine by engine.

        1-3 create the job, establish RUNNING and persist ownership/heartbeat.
        4   dispose the engine WITHOUT closing the attempt - the crash.
        5   advance the injected clock past the liveness bound.
        6-8 a brand new engine, service and sweep resolve the same identity.
        9-11 the durable facts survive and nothing was duplicated.
        """
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            recovery.execution.jobs.checkpoint("JOB-0001", {"step": "half"})
            first = recovery.execution.current_attempt("JOB-0001")
            assert first is not None
            started, deadline = first.started_at, first.deadline_at
        # The engine is disposed by the context manager. The attempt is still
        # open, its owner still recorded: exactly what a crash leaves behind.
        opens_before = reopen.opens
        clock.advance(SILENCE)

        with reopen.recovery() as (recovery, _):
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "RUNNING"
            ), "the crashed job did not come back RUNNING from disk"
            assert recovery.heartbeat_stale("JOB-0001") is True
            assert recovery.recover_lost_executions() == ("JOB-0001",)

        with reopen.recovery() as (recovery, _):
            job = recovery.execution.jobs.require("JOB-0001")
            assert job.lifecycle_state == "RESUMING"
            assert job.job_id == "JOB-0001"
            assert job.idempotency_key == "key-1"
            attempts = recovery.execution.attempts("JOB-0001")
            assert [a.attempt for a in attempts] == [1]
            assert attempts[0].outcome == "RECOVERABLE"
            assert attempts[0].started_at == started
            assert attempts[0].deadline_at == deadline
            assert [c.sequence for c in recovery.execution.jobs.checkpoints(
                "JOB-0001"
            )] == [1]
            assert recovery.execution.jobs.checkpoints("JOB-0001")[0].payload == {
                "step": "half"
            }
        assert reopen.opens > opens_before + 1, "the sweep reused an engine"

    def test_recovery_across_restart_creates_no_duplicate_identity(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """Silent duplication is the other way a durable job can be lost."""
        with reopen.recovery() as (recovery, _):
            run(recovery)
        for _restart in range(3):
            clock.advance(SILENCE)
            with reopen.recovery() as (recovery, _):
                recovery.recover_lost_executions()
        with reopen.recovery() as (recovery, session):
            assert (
                len(session.query(DurableJobRecord).all())
                if hasattr(session, "query") else 1
            ) == 1
            resubmitted = submit(recovery.execution)
            assert resubmitted.job_id == "JOB-0001"
            assert recovery.execution.attempt_count("JOB-0001") == 1

    def test_the_sweep_is_governed_and_a_denial_changes_nothing(
        self, tmp_path: pathlib.Path, database_path: pathlib.Path, pep,  # noqa: ANN001
        clock: MovableClock,
    ) -> None:
        from arkali.kernel.persistence.engine import (
            create_persistence_engine,
            sqlite_url,
        )

        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                run(JobRecovery(session, pep, clock))
            clock.advance(SILENCE)
            denied = denying_pep(tmp_path / "denied")
            with pytest.raises(Exception) as refusal:
                with unit_of_work(create_session_factory(engine)) as session:
                    JobRecovery(session, denied, clock).recover_lost_executions()
            assert "WRITE_WORKSPACE_FILE" in str(refusal.value)
            with unit_of_work(create_session_factory(engine)) as session:
                stored = session.get(DurableJobRecord, "JOB-0001")
                assert stored is not None
                assert stored.lifecycle_state == "RUNNING", (
                    "a denied sweep moved the job anyway"
                )
        finally:
            engine.dispose()


class TestRecoveryDoesNotRegressPackageTwo:
    def test_cancellation_still_reaches_only_running_jobs(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            recovery.recover_lost_executions()
            with pytest.raises(Exception) as refusal:
                recovery.execution.cancel("JOB-0001")
            assert type(refusal.value).__name__ == "IllegalTransition"

    def test_a_dead_lettered_job_is_never_swept_again(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, session):
            run(recovery)
            set_bound(session, "JOB-0001", attempts=1, timeout=300, heartbeat=60)
            clock.advance(SILENCE)
            recovery.recover_lost_executions()
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "DEAD_LETTER"
            )
            clock.advance(100_000)
            assert recovery.recover_lost_executions() == ()

    def test_the_stale_owner_rule_still_holds_during_a_live_execution(
        self, reopen: Reopener
    ) -> None:
        with reopen.recovery() as (recovery, _):
            run(recovery)
            with pytest.raises(StaleExecutionOwnership):
                recovery.execution.heartbeat("JOB-0001", "worker-b")

