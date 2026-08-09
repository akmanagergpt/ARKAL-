"""C-19 pause, resume and crash recovery.

Owner: `execution.durable`. Phase 7 Atomic Package 3.

THE PATHS ARE DERIVED FROM THE CANONICAL MACHINE, NOT CHOSEN HERE. Read off the
Phase 3 `Job` relation before this module was written:

* `RESUMING` has exactly two predecessors, `PAUSED` and `RECOVERABLE`. Pause and
  crash recovery therefore *share* one lifecycle meaning because the canonical
  relation says so, not because this module arranges it.
* `RUNNING -> RECOVERABLE` is **not declared** and `evaluate` refuses it. The
  only route from a running job to `RECOVERABLE` is `RUNNING -> FAILED ->
  RECOVERABLE`, which is precisely the disposition Package 2 already owns.
  `EXECUTION_AND_CAPABILITY.md` section 3 names the states a crashed job
  resolves *to*; `STATE_MACHINES.md` section 3 owns the edges it travels, and
  the two agree once the route is read from the relation rather than assumed.

So this module adds no transition, holds no relation and compares no state to
decide legality. Every move is `JobStore.transition`, which is `evaluate`.

PAUSE LEAVES THE ATTEMPT ALONE. A paused execution is suspended, not lost: its
attempt stays open under the same owner, with the same absolute deadline and the
same position in the retry budget. Closing it would consume an attempt - and
pausing is not failing - while extending its deadline would reset the timeout
basis the job was admitted under. Both are forbidden by the durability terms, so
resume returns to exactly the attempt that was interrupted.

CRASH RECOVERY CLOSES IT, AND MUST. A crashed execution is gone, so its attempt
is closed through Package 2's own failure path. That is what makes the departed
owner unable to act: a closed attempt refuses every write, so a zombie worker
cannot heartbeat, complete or fail the execution it lost. The consumed attempt
is honest accounting - the attempt really did happen and really did stop.

THE HEARTBEAT IS THE RECOVERY TRIGGER, NOT THE DEADLINE. `heartbeat_stale` reads
`heartbeat_at` against the job's recorded `heartbeat_timeout_seconds`. These are
different questions from `JobExecution.timed_out`, which reads `deadline_at`: a
worker can fall silent long before its deadline, and a worker that is very much
alive can pass one. Conflating them was F-0036.

NOTHING HERE SCHEDULES. The sweep decides that an execution is *gone*; it does
not decide who should run the job next, in what order, with what priority or on
what resources. It leaves a recovered job in `RESUMING` for someone to pick up,
and picking up is `execution.scheduler` / C-21 at **Phase 8**.

NOTHING HERE SLEEPS. Staleness is a comparison against the injected clock.

TRANSACTION BOUNDARIES BELONG TO THE CALLER.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.execution.durable.errors import PauseNotSupported
from arkali.execution.durable.execution import JobExecution
from arkali.execution.durable.job_state_machine import (
    PAUSED,
    RECOVERABLE,
    RESUMING,
    RUNNING,
)
from arkali.execution.durable.job_store import ACTOR, READ, TRUST_TIER, Clock
from arkali.execution.durable.job_type import JobTypeRegistry
from arkali.execution.durable.records import (
    DurableJobRecord,
    JobExecutionAttempt,
    utc_now,
)

#: What the sweep records against the attempt it closes, so a later reader can
#: tell a crash-recovered attempt from one its own owner failed.
RECOVERY_DETAIL = "heartbeat expired; execution presumed lost"


class JobRecovery:
    """Pause, resume and the crash-recovery sweep over one session.

    Composes `JobExecution` and `JobTypeRegistry` rather than extending either:
    identity and checkpoints are one responsibility, execution semantics
    another, applicability data a third, and ADR-0008 makes decomposition the
    answer before a module grows past its budget.
    """

    def __init__(
        self,
        session: Session,
        pep: PolicyEnforcementPoint,
        clock: Clock = utc_now,
    ) -> None:
        self._session = session
        self._pep = pep
        self._clock = clock
        self._execution = JobExecution(session, pep, clock)
        self._types = JobTypeRegistry(session, pep, clock)

    @property
    def execution(self) -> JobExecution:
        """The Package 2 execution service this one defers to."""
        return self._execution

    @property
    def job_types(self) -> JobTypeRegistry:
        """The registry that answers the pause applicability rule."""
        return self._types

    def _guard(self, operation: str) -> None:
        self._pep.require_auto(
            PolicyRequest(
                operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
            )
        )

    # -- pause / resume ------------------------------------------------------

    def pause(self, job_id: str) -> DurableJobRecord:
        """Suspend a job whose type declares pause support.

        BOTH conditions are required and neither substitutes for the other: the
        persisted declaration must say the type supports pause, and the
        canonical machine must permit the move from wherever the job is. The
        capability is checked first so that an unsupported type is refused
        before any state is touched; the machine is then the only thing that
        decides whether `PAUSED` is reachable at all.

        The open attempt is deliberately untouched - see the module docstring.
        """
        record = self._execution.jobs.require(job_id)
        self._require_pausable(record)
        self._execution.jobs.transition(job_id, PAUSED)
        return self._execution.jobs.require(job_id)

    def resume(self, job_id: str) -> DurableJobRecord:
        """Return a paused job to `RUNNING` through `RESUMING`.

        Two machine-evaluated moves, not one: `RESUMING` is a real state a
        resumed job passes through, and skipping it would be a transition the
        canonical relation does not declare. The attempt, its owner, its
        deadline and the retry budget are all exactly as they were.

        Pause capability is required here too. A job only reaches `PAUSED`
        through `pause`, so this is defence in depth rather than the primary
        check - but it means the pause path cannot be entered by a type that
        does not declare it, however the job got there.
        """
        record = self._execution.jobs.require(job_id)
        self._require_pausable(record)
        self._execution.jobs.transition(job_id, RESUMING)
        self._execution.jobs.transition(job_id, RUNNING)
        return self._execution.jobs.require(job_id)

    def _require_pausable(self, record: DurableJobRecord) -> None:
        """The applicability rule, read from the registry and nowhere else."""
        if not self._types.supports_pause(record.job_type):
            raise PauseNotSupported(
                f"job type {record.job_type!r} does not declare supports_pause; "
                "pause capability is read from the job-type registry, never "
                "from the request or the job's state"
            )

    # -- crash recovery ------------------------------------------------------

    def heartbeat_stale(self, job_id: str) -> bool:
        """Whether the open attempt has gone silent for longer than permitted.

        Reads `heartbeat_at` against the job's recorded heartbeat timeout. A job
        with no open attempt has nothing to be silent about and is not stale.
        """
        attempt = self._execution.current_attempt(job_id)
        if attempt is None:
            return False
        return self._stale(self._execution.jobs.require(job_id), attempt)

    def _stale(self, record: DurableJobRecord, attempt: JobExecutionAttempt) -> bool:
        limit = _as_utc(attempt.heartbeat_at) + dt.timedelta(
            seconds=record.heartbeat_timeout_seconds
        )
        return _as_utc(self._clock()) >= limit

    def _stale_running(self) -> tuple[tuple[DurableJobRecord, JobExecutionAttempt], ...]:
        """Every running job whose open attempt has stopped reporting.

        `RUNNING` is a filter over rows to consider, not a judgement about a
        move: the machine still decides every transition below. The filter is
        load-bearing rather than decorative - a PAUSED job also holds an open
        attempt and is deliberately silent, so recovering by open-attempt
        staleness alone would "recover" every paused job.
        """
        self._guard(READ)
        rows = self._session.execute(
            select(DurableJobRecord, JobExecutionAttempt)
            .join(
                JobExecutionAttempt,
                JobExecutionAttempt.job_id == DurableJobRecord.job_id,
            )
            .where(
                DurableJobRecord.lifecycle_state == RUNNING,
                JobExecutionAttempt.ended_at.is_(None),
            )
            .order_by(DurableJobRecord.job_id)
        ).all()
        return tuple(
            (record, attempt)
            for record, attempt in rows
            if self._stale(record, attempt)
        )

    def recover_lost_executions(self) -> tuple[str, ...]:
        """Resolve every running job whose execution has stopped reporting.

        Per job, and every move through `evaluate`:

        1. Package 2's failure path closes the attempt and disposes the job -
           `RUNNING -> FAILED`, then `RECOVERABLE` while the recorded bound
           leaves an attempt and `DEAD_LETTER` when it does not. The
           disposition is not re-decided here; this reads what it chose.
        2. A recoverable job then moves `RECOVERABLE -> RESUMING`, which is
           where recovery stops. Nothing here starts the next attempt: a
           resumable job waiting for someone to pick it up is the boundary
           between durability and scheduling.

        IDEMPOTENT BY CONSTRUCTION, not by a guard. A recovered job is no longer
        `RUNNING` and no longer has an open attempt, so it cannot match the
        selection twice. Returns the ids it resolved, so a second sweep
        returning empty is observable.
        """
        recovered: list[str] = []
        for record, attempt in self._stale_running():
            job_id = record.job_id
            closed = self._execution.fail_attempt(
                job_id, attempt.owner, RECOVERY_DETAIL
            )
            if closed.outcome == RECOVERABLE:
                self._execution.jobs.transition(job_id, RESUMING)
            recovered.append(job_id)
        return tuple(recovered)


def _as_utc(moment: dt.datetime) -> dt.datetime:
    """SQLite returns naive values for UTC columns; compare like with like."""
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)
