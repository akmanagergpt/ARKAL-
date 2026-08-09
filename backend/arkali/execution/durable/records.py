"""C-19 durable job record and checkpoint.

Owner: `execution.durable` - AUTHORITY_MAP.yaml concern `durable job state`.
`ARCHITECTURE.md` section 3 row 14 names this context the Durable Job Runtime.

TWO IDENTITIES, ONE STORE. `job_id` answers "which row is this?" and is the
primary key. (`job_type`, `idempotency_key`) answers "has this work already been
submitted?" and is a unique constraint. The second is deliberately NOT a separate
table: it is a fact about a job, and a second table holding the same fact would
be a second place that answers the same question - the duplicate authority
`MS §Constitution 1` forbids. The constraint is the authority; the lookup in
`JobStore.submit` only turns a driver error into a typed result.

IDEMPOTENCY IS SCOPED BY JOB TYPE. The same key under two job types is two
different pieces of work. A global key space would let one producer suppress
another's job by reusing a string.

`lifecycle_state` IS A RECORDED VALUE, NOT A TRANSITION TABLE. The `Job` machine
delivered in Phase 3 is the sole authority; `INITIAL_STATE` below is *derived*
from that machine's declared relation rather than named, so this module cannot
nominate a state the machine does not recognise. No state literal is written
here and a structural control asserts that.

CHECKPOINT ORDERING IS IDENTITY. The primary key is (`job_id`, `sequence`), so
two checkpoints cannot claim one position and an ordinal cannot be silently
reused. Checkpoints refuse both update and delete: a restart reads them to decide
where work resumed from, and a record that can be edited or removed is not a
durability record. The job row itself stays mutable, because the machine declares
non-terminal states and the row follows it.

EXECUTION ATTEMPTS ARE THE RETRY ACCOUNTING. Package 2 adds
`job_execution_attempt`, one row per attempt, keyed (`job_id`, `attempt`). The
attempt count is therefore *derived from rows*, never held in a counter that a
restart could reset or a caller could set. The primary key is also the
concurrency backstop: two writers racing to open the same next attempt cannot
both succeed, whatever the service does.

`owner` RECORDS WHO IS EXECUTING; IT DOES NOT DECIDE WHO SHOULD. Package 2
refuses a heartbeat or completion from a stale owner, which is a durability
property. Choosing an owner, allocating one, or balancing across them is
`execution.scheduler` at Phase 8 and appears nowhere here.

NOTHING HERE SCHEDULES. No queue, admission, priority, capacity or resource
field exists. Admission and allocation are C-21 at Phase 8, and a column added
now for a behaviour that does not exist would be a claim.

ENGINE-NEUTRAL (ARK-REQ-0012). Declarative mapping only - `String`, `Integer`,
`DateTime`, `JSON` and standard constraints, all rendered for SQLite and
PostgreSQL alike. No PRAGMA, no raw SQL, no dialect branch. The engine is built
only by `kernel.persistence`.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from arkali.execution.durable.errors import CheckpointImmutabilityViolation
from arkali.execution.durable.job_state_machine import DEFINITION
from arkali.kernel.persistence.base import PersistenceBase

JOB_TABLE: Final[str] = "durable_job"
CHECKPOINT_TABLE: Final[str] = "job_checkpoint"
ATTEMPT_TABLE: Final[str] = "job_execution_attempt"

IDENTITY_LENGTH: Final[int] = 64
FIELD_LENGTH: Final[int] = 200
STATE_LENGTH: Final[int] = 40

#: Retry bound and per-attempt timeout applied when a submission names none.
#: Recorded on the row, so the bound a job was admitted under survives a restart
#: and cannot be widened by changing a default later.
DEFAULT_MAX_ATTEMPTS: Final[int] = 3
DEFAULT_ATTEMPT_TIMEOUT_SECONDS: Final[int] = 300

#: The named constraint that IS the idempotency authority.
IDEMPOTENCY_CONSTRAINT: Final[str] = "uq_durable_job_idempotency"

#: The state a job starts in. Read from the machine's declared relation - the
#: single state with no incoming transition - so this module writes no state
#: literal of its own and cannot drift from `STATE_MACHINES.md` section 3.
INITIAL_STATE: Final[str] = next(
    state for state in DEFINITION.states
    if all(target != state for _, target in DEFINITION.transitions)
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class DurableJobRecord(PersistenceBase):
    """One durable job: its identity, its idempotency key and its recorded state."""

    __tablename__ = JOB_TABLE
    __table_args__ = (
        UniqueConstraint("job_type", "idempotency_key", name=IDEMPOTENCY_CONSTRAINT),
    )

    job_id: Mapped[str] = mapped_column(String(IDENTITY_LENGTH), primary_key=True)
    job_type: Mapped[str] = mapped_column(String(FIELD_LENGTH), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(FIELD_LENGTH), nullable=False)
    #: Recorded outcome of a machine-evaluated move. Never decided here.
    lifecycle_state: Mapped[str] = mapped_column(String(STATE_LENGTH), nullable=False)
    #: The job's input. Opaque to this contract; the runtime that executes a job
    #: type owns its meaning.
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    #: The retry bound this job was admitted under. Persisted rather than read
    #: from configuration at retry time, so changing a default later cannot
    #: widen the budget of a job already in flight.
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_MAX_ATTEMPTS
    )
    #: How long one attempt may run before it is timed out. The basis is stored
    #: per attempt as an absolute deadline, so a restart cannot move it.
    attempt_timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=DEFAULT_ATTEMPT_TIMEOUT_SECONDS
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    checkpoints: Mapped[list[JobCheckpointRecord]] = relationship(
        back_populates="job", cascade="save-update"
    )
    attempts: Mapped[list[JobExecutionAttempt]] = relationship(
        back_populates="job", cascade="save-update"
    )


class JobCheckpointRecord(PersistenceBase):
    """A point a job's work can be resumed from.

    Immutable once persisted. `sequence` is derived from the stored rows, never
    supplied, and is part of the primary key so ordering cannot collide.
    """

    __tablename__ = CHECKPOINT_TABLE

    job_id: Mapped[str] = mapped_column(
        String(IDENTITY_LENGTH),
        ForeignKey(f"{JOB_TABLE}.job_id"),
        primary_key=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    job: Mapped[DurableJobRecord] = relationship(back_populates="checkpoints")


class JobExecutionAttempt(PersistenceBase):
    """One execution attempt of a job: who ran it, until when, and how it ended.

    The rows ARE the retry accounting. `attempt` is part of the primary key, so
    the database refuses two rows for one attempt number however the service
    behaves - the concurrency backstop, not a service-level check.

    An attempt is OPEN while `ended_at` is NULL and CLOSED once it is set. A
    closed attempt is history: the service refuses to write to one, and a closed
    attempt's outcome is what a later reopen reads.
    """

    __tablename__ = ATTEMPT_TABLE

    job_id: Mapped[str] = mapped_column(
        String(IDENTITY_LENGTH),
        ForeignKey(f"{JOB_TABLE}.job_id"),
        primary_key=True,
    )
    #: 1-based. Derived from the stored rows, never supplied by a caller.
    attempt: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: Who is executing. Recorded, never chosen here - see the module docstring.
    owner: Mapped[str] = mapped_column(String(FIELD_LENGTH), nullable=False)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: Last proof of life. Compared against the injected clock; never slept on.
    heartbeat_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: Absolute, computed once when the attempt opens. An absolute deadline
    #: cannot be reset by a restart the way a remaining-duration counter could.
    deadline_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: NULL while open. Set once, with `outcome`, when the attempt closes.
    ended_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The recorded Job state this attempt ended in. A value, not a decision:
    #: the canonical machine decided it before it was written here.
    outcome: Mapped[str | None] = mapped_column(String(STATE_LENGTH), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(FIELD_LENGTH), nullable=True)

    job: Mapped[DurableJobRecord] = relationship(back_populates="attempts")

    @property
    def is_open(self) -> bool:
        return self.ended_at is None


def _refuse(action: str, identity: str) -> CheckpointImmutabilityViolation:
    return CheckpointImmutabilityViolation(
        f"checkpoint {identity!r} cannot be {action}; a restart reads checkpoints "
        "to decide where work resumed from, so they are recorded once and never "
        "edited or removed",
        source="docs/contracts/job.md section 4",
    )


@event.listens_for(JobCheckpointRecord, "before_update", propagate=True)
def _refuse_checkpoint_update(
    _mapper: object, _connection: object, target: JobCheckpointRecord
) -> None:
    raise _refuse("modified", f"{target.job_id}#{target.sequence}")


@event.listens_for(JobCheckpointRecord, "before_delete", propagate=True)
def _refuse_checkpoint_delete(
    _mapper: object, _connection: object, target: JobCheckpointRecord
) -> None:
    raise _refuse("deleted", f"{target.job_id}#{target.sequence}")
