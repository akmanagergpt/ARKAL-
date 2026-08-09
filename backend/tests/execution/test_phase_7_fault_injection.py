"""Phase 7 fault-injection evidence — ARK-REQ-0059 and ARK-REQ-0061.

WHAT IS AND IS NOT CLAIMED, STATED FIRST.

    T12 formal chaos corpus = NOT CLAIMED
    ARK-REQ-0327            = NOT CLAIMED
    Phase 31                = NOT CLAIMED

The formal chaos tier begins at Phase 31 and `ARK-REQ-0327` is the durable
restart chaos proof that belongs to it. What this module produces is **real
fault injection at the tier currently available** — the accepted Phase 4
`ARK-REQ-0121` precedent, where real faults were injected without claiming a
corpus that does not exist yet. Nothing here is simulated, stubbed or mocked.

WHAT A FAULT MEANS HERE. Each test destroys something a durable runtime is
supposed to survive — the process, the writer's liveness, the transaction, the
attempt budget, the clock — and then asserts that the DURABILITY SEMANTICS held,
not merely that an exception was raised. An exception path proves an error was
detected; these prove the job is still correctly accounted for afterwards.

DETERMINISTIC. Every time-dependent fault is driven by the injected clock, so no
assertion depends on wall-clock timing and nothing sleeps.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from arkali.execution.durable.errors import (
    NoOpenAttempt,
    RetryBudgetExhausted,
    StaleExecutionOwnership,
)
from arkali.execution.durable.records import DurableJobRecord, JobExecutionAttempt
from tests.execution.phase_7_harness import (  # noqa: F401 - fixtures
    JOB_ID,
    JOB_TYPE,
    OWNER,
    MovableClock,
    Runtime,
    as_utc,
    clock,
    database,
    enqueue_body,
    pdp,
    runtime,
)

SILENCE = 61


def prepared(runtime: Runtime, *, supports_pause: bool = True) -> None:
    """A declared type and one enqueued job, through the real HTTP surface."""
    with runtime.durable() as (recovery, _execution, _session):
        recovery.job_types.declare(JOB_TYPE, supports_pause=supports_pause)
    with runtime.app() as client:
        assert client.post("/api/jobs", json=enqueue_body()).status_code == 202


class TestFaultProcessLossWithPersistedRunningState:
    """The fault durability exists for: the process disappears mid-execution."""

    def test_a_running_job_comes_back_running_and_is_then_recovered(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
            execution.jobs.checkpoint(JOB_ID, {"stage": "before the crash"})
        # The engine is disposed with the attempt still open and the owner still
        # recorded. That is exactly what a killed worker leaves behind.
        clock.advance(SILENCE)
        with runtime.durable() as (recovery, execution, _session):
            assert execution.jobs.require(JOB_ID).lifecycle_state == "RUNNING", (
                "the interrupted job did not come back RUNNING from disk"
            )
            assert recovery.heartbeat_stale(JOB_ID) is True
            assert recovery.recover_lost_executions() == (JOB_ID,)
        with runtime.durable() as (_recovery, execution, _session):
            assert execution.jobs.require(JOB_ID).lifecycle_state == "RESUMING"
            assert [c.payload["stage"] for c in execution.jobs.checkpoints(
                JOB_ID
            )] == ["before the crash"], "the checkpoint did not survive the crash"

    def test_the_job_never_silently_disappears(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """`STATE_MACHINES.md` section 3: silent disappearance is a FAIL.

        The invariant is that an interrupted job resolves to RESUMING or
        RECOVERABLE. Asserted against the canonical relation's own vocabulary
        rather than against a transcribed pair.
        """
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        clock.advance(SILENCE)
        with runtime.durable() as (recovery, execution, _session):
            recovery.recover_lost_executions()
            state = execution.jobs.require(JOB_ID).lifecycle_state
            assert state in {"RESUMING", "RECOVERABLE"}, (
                f"an interrupted job resolved to {state}"
            )


class TestFaultHeartbeatExpiry:
    def test_expiry_is_derived_from_persisted_facts_not_process_memory(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """The recovering process never saw the job start."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        clock.advance(SILENCE)
        # A completely separate runtime, holding no memory of the execution.
        with runtime.durable() as (recovery, _execution, _session):
            assert recovery.heartbeat_stale(JOB_ID) is True
            assert recovery.recover_lost_executions() == (JOB_ID,)

    def test_a_live_heartbeat_across_restarts_is_never_recovered(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """NEGATIVE CONTROL: durability must not steal a live execution."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        for _beat in range(5):
            clock.advance(SILENCE - 2)
            with runtime.durable() as (recovery, execution, _session):
                execution.heartbeat(JOB_ID, OWNER)
                assert recovery.recover_lost_executions() == ()
        with runtime.durable() as (_recovery, execution, _session):
            assert execution.jobs.require(JOB_ID).lifecycle_state == "RUNNING"


class TestFaultStaleOwnerReturns:
    def test_a_zombie_worker_cannot_touch_the_recovered_execution(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """The worker was cut off, recovery happened, and it comes back."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        clock.advance(SILENCE)
        with runtime.durable() as (recovery, _execution, _session):
            recovery.recover_lost_executions()
        with runtime.durable() as (_recovery, execution, _session):
            for call in ("heartbeat", "complete_attempt", "fail_attempt"):
                with pytest.raises(NoOpenAttempt):
                    getattr(execution, call)(JOB_ID, OWNER)
            assert execution.jobs.require(JOB_ID).lifecycle_state == "RESUMING", (
                "the zombie's refused calls moved the job anyway"
            )

    def test_a_second_worker_cannot_seize_a_live_execution(
        self, runtime: Runtime
    ) -> None:
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        with runtime.durable() as (_recovery, execution, _session):
            for call in ("heartbeat", "complete_attempt", "fail_attempt"):
                with pytest.raises(StaleExecutionOwnership):
                    getattr(execution, call)(JOB_ID, "worker-intruder")


class TestFaultFailedTransaction:
    def test_a_unit_of_work_that_raises_leaves_no_partial_state(
        self, runtime: Runtime
    ) -> None:
        """The durable services never commit; the caller's boundary decides.

        A checkpoint written in a unit of work that then fails must not be
        visible to the next runtime — a half-written durability record is worse
        than none, because a restart would resume from it.
        """
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
            execution.jobs.checkpoint(JOB_ID, {"stage": "committed"})

        class Injected(RuntimeError):
            pass

        with pytest.raises(Injected):
            with runtime.durable() as (_recovery, execution, _session):
                execution.jobs.checkpoint(JOB_ID, {"stage": "rolled back"})
                raise Injected("fault injected inside the unit of work")

        with runtime.durable() as (_recovery, execution, _session):
            stages = [c.payload["stage"] for c in execution.jobs.checkpoints(JOB_ID)]
            assert stages == ["committed"], (
                f"the rolled-back checkpoint survived: {stages}"
            )

    def test_the_database_refuses_a_duplicate_attempt_written_past_the_service(
        self, runtime: Runtime
    ) -> None:
        """The concurrency backstop is the primary key, not a service check."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        with pytest.raises(IntegrityError):
            with runtime.durable() as (_recovery, execution, session):
                current = execution.current_attempt(JOB_ID)
                assert current is not None
                session.add(  # type: ignore[attr-defined]
                    JobExecutionAttempt(
                        job_id=JOB_ID,
                        attempt=current.attempt,
                        owner="racing-worker",
                        started_at=current.started_at,
                        heartbeat_at=current.heartbeat_at,
                        deadline_at=current.deadline_at,
                    )
                )
        with runtime.durable() as (_recovery, execution, _session):
            assert execution.attempt_count(JOB_ID) == 1


class TestFaultRetryExhaustion:
    def test_repeated_crashes_dead_letter_rather_than_retrying_forever(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """The bound the job was admitted under survives every restart."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, session):
            record = execution.jobs.require(JOB_ID)
            record.max_attempts = 2
        outcomes = []
        for _crash in range(2):
            with runtime.durable() as (_recovery, execution, _session):
                job = execution.jobs.require(JOB_ID)
                if job.lifecycle_state in {"RECOVERABLE", "RESUMING", "QUEUED"}:
                    execution.begin_attempt(JOB_ID, OWNER)
            clock.advance(SILENCE)
            with runtime.durable() as (recovery, execution, _session):
                recovery.recover_lost_executions()
                outcomes.append(execution.jobs.require(JOB_ID).lifecycle_state)
        assert outcomes[-1] == "DEAD_LETTER", f"states were {outcomes}"
        with runtime.durable() as (_recovery, execution, _session):
            assert execution.attempt_count(JOB_ID) == 2
            with pytest.raises(RetryBudgetExhausted):
                execution.begin_attempt(JOB_ID, OWNER)

    def test_a_dead_lettered_job_is_never_revived_by_a_later_sweep(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """`DEAD_LETTER` has no outgoing transition; the sweep cannot invent one."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            record = execution.jobs.require(JOB_ID)
            record.max_attempts = 1
            execution.begin_attempt(JOB_ID, OWNER)
        clock.advance(SILENCE)
        with runtime.durable() as (recovery, execution, _session):
            recovery.recover_lost_executions()
            assert execution.jobs.require(JOB_ID).lifecycle_state == "DEAD_LETTER"
        for _sweep in range(3):
            clock.advance(100_000)
            with runtime.durable() as (recovery, execution, _session):
                assert recovery.recover_lost_executions() == ()
                assert execution.jobs.require(
                    JOB_ID
                ).lifecycle_state == "DEAD_LETTER"


class TestFaultTimeout:
    def test_an_attempt_that_overruns_its_deadline_is_disposed(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """A worker heartbeating forever still cannot exceed its admission terms."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        for _beat in range(6):
            clock.advance(SILENCE - 2)
            with runtime.durable() as (_recovery, execution, _session):
                execution.heartbeat(JOB_ID, OWNER)
        with runtime.durable() as (recovery, execution, _session):
            assert execution.timed_out(JOB_ID) is True
            assert recovery.heartbeat_stale(JOB_ID) is False, (
                "the worker is reporting; only its deadline has passed"
            )
            execution.time_out(JOB_ID)
            assert execution.jobs.require(JOB_ID).lifecycle_state == "RECOVERABLE"

    def test_the_deadline_basis_survives_a_restart(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """An absolute instant cannot be reset by restarting the process."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            opened = execution.begin_attempt(JOB_ID, OWNER)
            deadline = as_utc(opened.deadline_at)
            started = as_utc(opened.started_at)
        for _restart in range(3):
            with runtime.durable() as (_recovery, execution, _session):
                current = execution.current_attempt(JOB_ID)
                assert current is not None
                assert as_utc(current.deadline_at) == deadline, (
                    "a restart moved the timeout basis"
                )
                assert as_utc(current.started_at) == started

    def test_timing_out_twice_is_idempotent(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        clock.advance(400)
        with runtime.durable() as (_recovery, execution, _session):
            first = execution.time_out(JOB_ID)
            again = execution.time_out(JOB_ID)
            assert (first.job_id, first.attempt) == (again.job_id, again.attempt)
            assert execution.attempt_count(JOB_ID) == 1


class TestFaultInterruptedPersistenceBoundary:
    def test_every_durable_fact_is_readable_after_repeated_reopen(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """Ten separate engines over one file; nothing drifts."""
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
            execution.jobs.checkpoint(JOB_ID, {"n": 1})
        for _reopen in range(10):
            with runtime.durable() as (_recovery, execution, _session):
                job = execution.jobs.require(JOB_ID)
                assert job.job_id == JOB_ID
                assert job.max_attempts >= 1
                assert execution.attempt_count(JOB_ID) == 1
                assert len(execution.jobs.checkpoints(JOB_ID)) == 1

    def test_the_recovery_sweep_is_idempotent_across_restarts(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        prepared(runtime)
        with runtime.durable() as (_recovery, execution, _session):
            execution.begin_attempt(JOB_ID, OWNER)
        clock.advance(SILENCE)
        resolved = []
        for _sweep in range(5):
            with runtime.durable() as (recovery, _execution, _session):
                resolved.append(recovery.recover_lost_executions())
        assert resolved[0] == (JOB_ID,)
        assert all(result == () for result in resolved[1:]), (
            f"a later sweep resolved the job again: {resolved}"
        )
        with runtime.durable() as (_recovery, execution, session):
            assert execution.attempt_count(JOB_ID) == 1
            rows = session.query(DurableJobRecord).all()  # type: ignore[attr-defined]
            assert len(rows) == 1


class TestWhatThisEvidenceDoesNotClaim:
    """Stated as an executable assertion, not only as prose.

    A future reader must not be able to mistake this module for the Phase 31
    corpus, and a later phase must not quietly satisfy `ARK-REQ-0327` by
    pointing at it.
    """

    def test_this_module_claims_no_phase_31_obligation(self) -> None:
        import pathlib

        source = pathlib.Path(__file__).read_text(encoding="utf-8")
        for claim in ("ARK-REQ-0327", "T12"):
            assert "NOT CLAIMED" in source
            assert claim in source, (
                f"{claim} must be named as explicitly not claimed"
            )

    def test_the_register_still_places_the_chaos_corpus_later(self) -> None:
        """Derived: `ARK-REQ-0327` is not a Phase 7 requirement."""
        import pathlib

        register = (
            pathlib.Path(__file__).resolve().parents[3]
            / "docs/canonical/REQUIREMENT_REGISTER.md"
        ).read_text(encoding="utf-8")
        row = next(
            line for line in register.splitlines()
            if line.startswith("| ARK-REQ-0327 |")
        )
        phase = [c.strip() for c in row.strip("|").split("|")][4]
        assert phase != "7", (
            f"ARK-REQ-0327 is assigned to phase {phase}; it is not Phase 7's "
            "to discharge"
        )
