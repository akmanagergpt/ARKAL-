"""C-19 durable execution semantics: attempts, heartbeat, retries, timeout.

Owner: `execution.durable`. Phase 7 Atomic Package 2.

WHAT THIS ANSWERS. What execution attempt currently represents a job, whether
its heartbeat is live, how many attempts have occurred, whether another is
permitted, and how an attempt ends. Every one of those is a durability question.

WHAT THIS DOES NOT ANSWER, AND MUST NOT. Which owner *should* receive a job,
resource allocation, admission, priority, capacity, worker pools, queues or
provider dispatch. `owner` is recorded, never chosen: the caller says who is
running, and this module's only interest is refusing a *stale* one. Allocation
is `execution.scheduler` / C-21 at **Phase 8**, and a structural control fails
on the vocabulary.

THE CANONICAL MACHINE DECIDES EVERY MOVE. This module names no state and holds
no transition table; it calls `JobStore.transition`, which calls the Phase 3
`Job` machine's `evaluate`. Where a *disposition* must be chosen - retry or
dead-letter after a failure - the choice is between two transitions the machine
already declares, and the machine still refuses either if the job is not in a
state that permits it.

RETRY ACCOUNTING IS ROWS, NOT A COUNTER. The attempt count is
`count(job_execution_attempt)`, so it cannot be reset by restarting a process,
cannot drift from what happened, and cannot be set by a caller. The primary key
(`job_id`, `attempt`) is the concurrency backstop: two writers opening the same
next attempt cannot both succeed.

THE DEADLINE IS ABSOLUTE. It is computed once, when the attempt opens, from the
injected clock and the bound recorded on the job. A remaining-duration counter
would silently restart with the process; an absolute instant does not.

NOTHING HERE SLEEPS. Liveness and expiry are comparisons against the injected
clock, so every control is deterministic.

TIMEOUT IS NOT HEARTBEAT STALENESS. `timed_out` reads `deadline_at`: it measures
elapsed work. Whether an execution has stopped *reporting* reads `heartbeat_at`
against a separate recorded bound and belongs to `recovery.py`. Package 2 shipped
the first question under a name that promised the second - F-0036 - and the name
is gone rather than reinterpreted.

PAUSE, RESUME AND RECOVERY ARE NOT HERE. This module enters neither `PAUSED` nor
`RESUMING` and runs no sweep. A failure with budget remaining is disposed to
`RECOVERABLE`, and `recovery.py` composes that disposition rather than repeating
it.

TRANSACTION BOUNDARIES BELONG TO THE CALLER. Like every sibling service, this
one never commits.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.execution.durable.errors import (
    DeadlineNotReached,
    NoOpenAttempt,
    RetryBudgetExhausted,
    StaleExecutionOwnership,
)
from arkali.execution.durable.job_state_machine import (
    CANCELLED,
    DEAD_LETTER,
    FAILED,
    RECOVERABLE,
    RUNNING,
    SUCCEEDED,
)
from arkali.execution.durable.job_store import (
    ACTOR,
    READ,
    TRUST_TIER,
    WRITE,
    Clock,
    JobStore,
)
from arkali.execution.durable.records import (
    DurableJobRecord,
    JobExecutionAttempt,
    utc_now,
)

#: Targets are IMPORTED from the authority, never written here. Selecting which
#: declared move to ask for is legitimate; keeping a second copy of the
#: vocabulary in this module is how a shadow authority starts, and a structural
#: control forbids it. The machine still refuses any of these from a state that
#: does not permit it, so importing a name grants nothing.


class JobExecution:
    """Attempt, heartbeat, retry, timeout and cancellation over one session.

    Composes `JobStore` rather than extending it: identity and checkpoints are
    one responsibility, execution semantics another, and ADR-0008 makes
    decomposition the answer before a module grows past its budget.
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
        self._jobs = JobStore(session, pep, clock)

    @property
    def jobs(self) -> JobStore:
        """The identity/state store this execution service defers to."""
        return self._jobs

    def _guard(self, operation: str) -> None:
        """The same injected PEP, the same two operation classes, no new ones."""
        self._pep.require_auto(
            PolicyRequest(
                operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
            )
        )

    # -- reads ---------------------------------------------------------------

    def attempts(self, job_id: str) -> tuple[JobExecutionAttempt, ...]:
        """Every attempt for a job, oldest first. This is the retry history."""
        self._guard(READ)
        rows = self._session.execute(
            select(JobExecutionAttempt)
            .where(JobExecutionAttempt.job_id == job_id)
            .order_by(JobExecutionAttempt.attempt)
        ).scalars()
        return tuple(rows)

    def attempt_count(self, job_id: str) -> int:
        """How many attempts have occurred, counted from the rows themselves."""
        self._guard(READ)
        return int(
            self._session.execute(
                select(func.count()).select_from(JobExecutionAttempt).where(
                    JobExecutionAttempt.job_id == job_id
                )
            ).scalar_one()
        )

    def current_attempt(self, job_id: str) -> JobExecutionAttempt | None:
        """The open attempt, or None. At most one can be open at a time."""
        self._guard(READ)
        return self._session.execute(
            select(JobExecutionAttempt).where(
                JobExecutionAttempt.job_id == job_id,
                JobExecutionAttempt.ended_at.is_(None),
            )
        ).scalar_one_or_none()

    def retry_permitted(self, job_id: str) -> bool:
        """Whether the bound recorded on the job leaves another attempt."""
        record = self._jobs.require(job_id)
        return self.attempt_count(job_id) < record.max_attempts

    def timed_out(self, job_id: str) -> bool:
        """Whether the open attempt has passed its absolute deadline.

        A pure comparison against the injected clock. This measures ELAPSED
        WORK, not silence: a job that has heartbeated a moment ago is timed out
        once its deadline passes, and one that has not heartbeated in a week is
        not. Whether an execution has stopped REPORTING is a different question
        with a different persisted basis, answered by
        `JobRecovery.heartbeat_stale` (F-0036).
        """
        attempt = self.current_attempt(job_id)
        if attempt is None:
            return False
        return self._expired(attempt)

    def _expired(self, attempt: JobExecutionAttempt) -> bool:
        return _as_utc(self._clock()) >= _as_utc(attempt.deadline_at)

    # -- writes --------------------------------------------------------------

    def begin_attempt(self, job_id: str, owner: str) -> JobExecutionAttempt:
        """Open the next attempt and move the job to RUNNING.

        The machine decides whether the job may enter RUNNING at all, so an
        attempt cannot be opened on a job that is terminal, paused or already
        running. The retry bound is checked first, so an attempt beyond it is
        refused rather than opened and then rolled back.
        """
        record = self._jobs.require(job_id)
        if not owner.strip():
            raise StaleExecutionOwnership("an execution attempt must name its owner")
        open_attempt = self.current_attempt(job_id)
        if open_attempt is not None:
            raise StaleExecutionOwnership(
                f"job {job_id!r} already has attempt {open_attempt.attempt} open "
                f"under {open_attempt.owner!r}; close it before opening another"
            )
        used = self.attempt_count(job_id)
        if used >= record.max_attempts:
            raise RetryBudgetExhausted(
                f"job {job_id!r} has used {used} of {record.max_attempts} "
                "attempts; the bound it was admitted under is exhausted"
            )

        # The machine refuses this before any attempt row is written.
        self._jobs.transition(job_id, RUNNING)

        moment = self._clock()
        attempt = JobExecutionAttempt(
            job_id=job_id,
            attempt=used + 1,
            owner=owner,
            started_at=moment,
            heartbeat_at=moment,
            deadline_at=moment + dt.timedelta(seconds=record.attempt_timeout_seconds),
        )
        self._guard(WRITE)
        self._session.add(attempt)
        self._session.flush()
        return attempt

    def heartbeat(self, job_id: str, owner: str) -> JobExecutionAttempt:
        """Record proof of life for the open attempt.

        Refused from any owner other than the one holding it, and from a closed
        attempt, so a superseded execution cannot keep a dead job looking alive.
        """
        attempt = self._require_open(job_id, owner)
        self._guard(WRITE)
        attempt.heartbeat_at = self._clock()
        self._session.flush()
        return attempt

    def complete_attempt(self, job_id: str, owner: str) -> JobExecutionAttempt:
        """Close the open attempt successfully and move the job to SUCCEEDED."""
        attempt = self._require_open(job_id, owner)
        self._jobs.transition(job_id, SUCCEEDED)
        return self._close(attempt, SUCCEEDED, None)

    def fail_attempt(
        self, job_id: str, owner: str, detail: str | None = None
    ) -> JobExecutionAttempt:
        """Close the open attempt as failed and dispose of the job.

        The disposition is the whole of Package 2's retry policy: FAILED, then
        RECOVERABLE when the bound leaves another attempt and DEAD_LETTER when
        it does not. Both are transitions the canonical machine declares, and it
        evaluates each one; nothing here writes a state directly.
        """
        attempt = self._require_open(job_id, owner)
        return self._fail(attempt, detail)

    def time_out(self, job_id: str) -> JobExecutionAttempt:
        """Close the open attempt because its deadline has passed.

        Idempotent: once the attempt is closed, calling again returns the same
        recorded attempt rather than consuming another or moving the job twice.
        A deadline that has not passed is refused, so a caller cannot force one.
        """
        attempt = self.current_attempt(job_id)
        if attempt is None:
            closed = self.attempts(job_id)
            if closed and closed[-1].outcome is not None:
                return closed[-1]
            raise NoOpenAttempt(f"job {job_id!r} has no attempt to time out")
        if not self._expired(attempt):
            raise DeadlineNotReached(
                f"attempt {attempt.attempt} of {job_id!r} runs until "
                f"{attempt.deadline_at}; the clock has not reached it"
            )
        return self._fail(attempt, "attempt deadline exceeded")

    def cancel(self, job_id: str, detail: str | None = None) -> DurableJobRecord:
        """Cancel a job through the canonical machine.

        The machine declares CANCELLED reachable only from RUNNING, so a queued
        job cannot be cancelled and a terminal one cannot be cancelled again.
        Neither rule is restated here - both are refusals from `evaluate`. An
        open attempt is closed in the same unit of work, so cancellation cannot
        leave an attempt open against a terminal job.
        """
        self._jobs.require(job_id)
        self._jobs.transition(job_id, CANCELLED)
        attempt = self.current_attempt(job_id)
        if attempt is not None:
            self._close(attempt, CANCELLED, detail)
        return self._jobs.require(job_id)

    # -- internals -----------------------------------------------------------

    def _require_open(self, job_id: str, owner: str) -> JobExecutionAttempt:
        attempt = self.current_attempt(job_id)
        if attempt is None:
            raise NoOpenAttempt(f"job {job_id!r} has no open execution attempt")
        if attempt.owner != owner:
            raise StaleExecutionOwnership(
                f"attempt {attempt.attempt} of {job_id!r} is held by "
                f"{attempt.owner!r}, not {owner!r}"
            )
        return attempt

    def _fail(
        self, attempt: JobExecutionAttempt, detail: str | None
    ) -> JobExecutionAttempt:
        job_id = attempt.job_id
        self._jobs.transition(job_id, FAILED)
        disposition = (
            RECOVERABLE if self.retry_permitted(job_id) else DEAD_LETTER
        )
        self._jobs.transition(job_id, disposition)
        return self._close(attempt, disposition, detail)

    def _close(
        self, attempt: JobExecutionAttempt, outcome: str, detail: str | None
    ) -> JobExecutionAttempt:
        self._guard(WRITE)
        attempt.ended_at = self._clock()
        attempt.outcome = outcome
        attempt.detail = detail
        self._session.flush()
        return attempt


def _as_utc(moment: dt.datetime) -> dt.datetime:
    """SQLite returns naive values for UTC columns; compare like with like."""
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)
