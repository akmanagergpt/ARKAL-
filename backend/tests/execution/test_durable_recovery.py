"""C-19 crash recovery — a lost execution resolves, and never silently.

`STATE_MACHINES.md` §3 invariant: an interrupted job resolves to `RESUMING` or
`RECOVERABLE`, and silent disappearance is a verification FAIL.
`EXECUTION_AND_CAPABILITY.md` §3: every `RUNNING` job without a live heartbeat
transitions to `RECOVERABLE`, then `RESUMING`.

Real SQLite migrated by the real Alembic chain, a real PDP, a real PEP. The
clock is advanced explicitly; nothing sleeps and no control can flake on timing.

WHETHER THE SWEEP DECIDES CORRECTLY IS HERE. Whether that decision survives a
restart, and whether Package 2 still holds, is `test_durable_recovery_restart.py`
— split under ADR-0008 when this module reached the 400 logical-line budget.
"""

from __future__ import annotations

import pytest

from arkali.execution.durable.errors import NoOpenAttempt
from arkali.execution.durable.job_state_machine import DEFINITION
from tests.execution.durable_harness import (  # noqa: F401 - fixtures
    OWNER,
    MovableClock,
    Reopener,
    clock,
    database_path,
    declare,
    pdp,
    pep,
    reopen,
    run,
    set_bound,
    submit,
)

#: Longer than the default heartbeat bound of 60s, shorter than the default
#: attempt deadline of 300s - so every assertion below distinguishes heartbeat
#: staleness from the deadline rather than conflating them.
SILENCE = 61
#: Just inside the bound. The comparison is `elapsed >= bound`, so 60 is already
#: stale and 59 is the last live instant; `TestTheLivenessBoundaryIsExact` pins
#: both sides rather than leaving the edge to whichever value a test picked.
LIVE = 59


class TestTheRecoveryPathComesFromTheCanonicalRelation:
    def test_running_cannot_reach_recoverable_directly(self) -> None:
        """The route is not chosen by this package; it is the only one declared.

        `EXECUTION_AND_CAPABILITY.md` §3 names the states a crashed job
        resolves TO. `STATE_MACHINES.md` §3 owns the edges, and this is not one
        of them - so recovery travels `RUNNING -> FAILED -> RECOVERABLE`, which
        is the disposition Package 2 already owns.
        """
        assert ("RUNNING", "RECOVERABLE") not in DEFINITION.transition_set
        assert {s for s, t in DEFINITION.transitions if t == "RECOVERABLE"} == {
            "FAILED"
        }

    def test_recoverable_leads_only_to_resuming(self) -> None:
        assert {t for s, t in DEFINITION.transitions if s == "RECOVERABLE"} == {
            "RESUMING"
        }

    def test_dead_letter_is_terminal_so_recovery_cannot_revive_it(self) -> None:
        assert {t for s, t in DEFINITION.transitions if s == "DEAD_LETTER"} == set()


class TestALiveHeartbeatIsNotRecovered:
    def test_a_running_job_reporting_normally_is_left_alone(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            clock.advance(LIVE)
            assert recovery.heartbeat_stale("JOB-0001") is False
            assert recovery.recover_lost_executions() == ()
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "RUNNING"
            )

    def test_heartbeating_keeps_a_long_running_job_out_of_recovery(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """Liveness is derived from `heartbeat_at`, so reporting resets it."""
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            for _beat in range(5):
                clock.advance(LIVE)
                recovery.execution.heartbeat("JOB-0001", OWNER)
                assert recovery.recover_lost_executions() == ()
            job = recovery.execution.jobs.require("JOB-0001")
            assert job.lifecycle_state == "RUNNING"
            attempt = recovery.execution.current_attempt("JOB-0001")
            assert attempt is not None and attempt.owner == OWNER

    def test_a_paused_job_is_never_swept_however_silent(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """NEGATIVE CONTROL, and the reason the sweep filters on RUNNING.

        A paused job holds an open attempt and is deliberately not reporting.
        Selecting by open-attempt staleness alone would "recover" every paused
        job, which is why the state filter is load-bearing rather than tidy.
        """
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=True)
            run(recovery)
            recovery.pause("JOB-0001")
            clock.advance(100_000)
            assert recovery.heartbeat_stale("JOB-0001") is True
            assert recovery.recover_lost_executions() == ()
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "PAUSED"
            )

    def test_a_job_with_no_open_attempt_is_not_stale(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, _):
            submit(recovery.execution)
            clock.advance(100_000)
            assert recovery.heartbeat_stale("JOB-0001") is False


class TestAnExpiredHeartbeatIsRecovered:
    def test_the_sweep_resolves_a_silent_execution_to_resuming(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, _):
            declare(recovery, supports_pause=False)
            run(recovery)
            clock.advance(SILENCE)
            assert recovery.heartbeat_stale("JOB-0001") is True
            assert recovery.recover_lost_executions() == ("JOB-0001",)
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "RESUMING"
            )

    def test_recovery_does_not_require_pause_capability(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """Crash recovery is not the pause path. A type that declares no pause
        support is still recovered - and is not even required to be declared,
        because the applicability rule governs pause, not durability."""
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            assert recovery.recover_lost_executions() == ("JOB-0001",)

    def test_the_lost_attempt_is_closed_and_recorded(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            recovery.recover_lost_executions()
            attempts = recovery.execution.attempts("JOB-0001")
            assert len(attempts) == 1
            assert attempts[0].is_open is False
            assert attempts[0].outcome == "RECOVERABLE"
            assert attempts[0].owner == OWNER
            assert recovery.execution.current_attempt("JOB-0001") is None

    def test_the_departed_owner_cannot_touch_the_recovered_execution(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """NEGATIVE CONTROL: a zombie worker returning after recovery.

        This is what closing the attempt buys. A worker that was cut off, and
        comes back believing it still holds the job, must not be able to
        heartbeat it, complete it or fail it.
        """
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            recovery.recover_lost_executions()
            for call in ("heartbeat", "complete_attempt", "fail_attempt"):
                with pytest.raises(NoOpenAttempt):
                    getattr(recovery.execution, call)("JOB-0001", OWNER)

    def test_recovery_cannot_skip_recoverable(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """The attempt records the disposition it actually passed through.

        `RESUMING` has exactly two predecessors and `PAUSED` is not reachable
        from `RUNNING` without a pause, so a job that arrived at `RESUMING` from
        a sweep can only have come through `RECOVERABLE` - and the closed
        attempt records that state as its outcome.
        """
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            recovery.recover_lost_executions()
            assert recovery.execution.attempts("JOB-0001")[0].outcome == (
                "RECOVERABLE"
            )
            assert {s for s, t in DEFINITION.transitions if t == "RESUMING"} == {
                "PAUSED", "RECOVERABLE"
            }

    def test_recovery_stops_at_resuming_and_starts_nothing(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """The durability/scheduling boundary, asserted.

        A recovered job waits in `RESUMING` for someone to pick it up. The
        sweep does not open the next attempt, because choosing who runs it is
        `execution.scheduler` at Phase 8.
        """
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            recovery.recover_lost_executions()
            assert recovery.execution.current_attempt("JOB-0001") is None
            assert recovery.execution.attempt_count("JOB-0001") == 1

    def test_a_recovered_job_can_be_picked_up_again(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """`RESUMING -> RUNNING` through the ordinary attempt path."""
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            recovery.recover_lost_executions()
            attempt = recovery.execution.begin_attempt("JOB-0001", "worker-b")
            assert attempt.attempt == 2
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "RUNNING"
            )

    def test_the_sweep_is_idempotent(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, _):
            run(recovery)
            clock.advance(SILENCE)
            assert recovery.recover_lost_executions() == ("JOB-0001",)
            for _again in range(4):
                assert recovery.recover_lost_executions() == ()
            assert recovery.execution.attempt_count("JOB-0001") == 1
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "RESUMING"
            )

    def test_an_exhausted_budget_dead_letters_instead_of_resuming(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        """Recovery does not widen the bound the job was admitted under."""
        with reopen.recovery() as (recovery, session):
            run(recovery)
            set_bound(session, "JOB-0001", attempts=1, timeout=300, heartbeat=60)
            clock.advance(SILENCE)
            assert recovery.recover_lost_executions() == ("JOB-0001",)
            assert (
                recovery.execution.jobs.require("JOB-0001").lifecycle_state
                == "DEAD_LETTER"
            )
            assert recovery.execution.attempts("JOB-0001")[0].outcome == (
                "DEAD_LETTER"
            )

    def test_the_sweep_resolves_several_jobs_and_leaves_live_ones(
        self, reopen: Reopener, clock: MovableClock
    ) -> None:
        with reopen.recovery() as (recovery, _):
            for index in (1, 2, 3):
                run(
                    recovery,
                    job_id=f"JOB-000{index}",
                    idempotency_key=f"key-{index}",
                )
            clock.advance(SILENCE)
            recovery.execution.heartbeat("JOB-0002", OWNER)
            assert recovery.recover_lost_executions() == ("JOB-0001", "JOB-0003")
            assert (
                recovery.execution.jobs.require("JOB-0002").lifecycle_state
                == "RUNNING"
            )

