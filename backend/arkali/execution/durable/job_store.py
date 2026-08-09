"""C-19 durable job store.

Owner: `execution.durable`.

THE MACHINE IS THE ONLY TRANSITION AUTHORITY. `transition` builds the canonical
`Job` machine and calls `evaluate`, which raises on every rejection. There is no
transition table, no allowed-target set and no state comparison in this module,
and a structural control asserts that, so a second authority cannot be
reintroduced quietly. The machine's typed rejections propagate unchanged.

IDEMPOTENCY IS PERSISTED, NOT CACHED. `submit` resolves a repeated
(`job_type`, `idempotency_key`) to the existing row by querying the database, and
the guarantee behind it is the unique constraint - not the lookup. An in-memory
map would forget on restart, which is the one condition durability exists for.
Re-submitting a known key returns the recorded job unchanged; it does not raise
and does not overwrite.

EVERY OPERATION IS GOVERNED. The PEP is injected with no default, so a caller
cannot obtain a store that writes without a policy decision. Reads request
`READ_FILE`, writes `WRITE_WORKSPACE_FILE` - the classes `evidence.audit`
already uses for persisted governed operations. No new operation class is
invented, and `unmapped_action_resolution: DENY` means none could be.

THE CLOCK IS INJECTED. Timestamps come from a supplied callable, so the
time-dependent semantics later packages add are testable without sleeping. This
package records time and decides nothing from it.

TRANSACTION BOUNDARIES BELONG TO THE CALLER. Like `ProjectRegistry`,
`ArtifactStore` and `AuditChain`, this service never commits, so a caller cannot
obtain a partially committed store.

NOTHING HERE SCHEDULES. No queue, claim, lease or admission decision exists;
`submit` records a job and returns. Allocation is C-21 at Phase 8.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.execution.durable.errors import (
    DuplicateJobIdentity,
    InvalidJobIdentity,
    UnknownJob,
)
from arkali.execution.durable.job_state_machine import build
from arkali.execution.durable.records import (
    INITIAL_STATE,
    DurableJobRecord,
    JobCheckpointRecord,
    utc_now,
)
from arkali.kernel.contracts.state_machine import TransitionOutcome

#: The actor this context presents to the PDP.
ACTOR: Final[str] = "execution.durable"
TRUST_TIER: Final[str] = "TRUST-0"

READ: Final[str] = "READ_FILE"
WRITE: Final[str] = "WRITE_WORKSPACE_FILE"

#: A callable returning the current instant. Injected so later packages'
#: time-dependent behaviour is testable without sleeping.
Clock = Callable[[], dt.datetime]


class JobSubmission:
    """What a producer must supply to submit one durable job.

    A value object rather than five keyword arguments, because
    `max_parameters_per_public_function` is 6 and ADR-0008 makes decomposition
    the answer to a budget. It carries no lifecycle field: the initial state is
    derived from the machine, so there is nothing here a caller could use to
    start a job in a state of its choosing.
    """

    __slots__ = ("job_id", "job_type", "idempotency_key", "payload")

    def __init__(
        self,
        *,
        job_id: str,
        job_type: str,
        idempotency_key: str,
        payload: dict[str, object] | None = None,
    ) -> None:
        self.job_id = job_id
        self.job_type = job_type
        self.idempotency_key = idempotency_key
        self.payload = dict(payload or {})

    def identities(self) -> tuple[str, str, str]:
        """The three values that must be non-empty for a job to exist."""
        return (self.job_id, self.job_type, self.idempotency_key)


class JobStore:
    """Durable job persistence over one session."""

    def __init__(
        self,
        session: Session,
        pep: PolicyEnforcementPoint,
        clock: Clock = utc_now,
    ) -> None:
        self._session = session
        self._pep = pep
        self._clock = clock
        self._machine = build()

    @property
    def machine_name(self) -> str:
        """The lifecycle authority this store defers to."""
        return self._machine.machine

    def _guard(self, operation: str) -> None:
        self._pep.require_auto(
            PolicyRequest(
                operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
            )
        )

    # -- reads ---------------------------------------------------------------

    def get(self, job_id: str) -> DurableJobRecord | None:
        self._guard(READ)
        return self._session.execute(
            select(DurableJobRecord).where(DurableJobRecord.job_id == job_id)
        ).scalar_one_or_none()

    def require(self, job_id: str) -> DurableJobRecord:
        found = self.get(job_id)
        if found is None:
            raise UnknownJob(f"no durable job {job_id!r} is registered")
        return found

    def find_submitted(self, job_type: str, idempotency_key: str) -> DurableJobRecord | None:
        """The job already recorded under this idempotency identity, if any."""
        self._guard(READ)
        return self._session.execute(
            select(DurableJobRecord).where(
                DurableJobRecord.job_type == job_type,
                DurableJobRecord.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()

    def checkpoints(self, job_id: str) -> tuple[JobCheckpointRecord, ...]:
        """Every checkpoint for a job, oldest first."""
        self._guard(READ)
        rows = self._session.execute(
            select(JobCheckpointRecord)
            .where(JobCheckpointRecord.job_id == job_id)
            .order_by(JobCheckpointRecord.sequence)
        ).scalars()
        return tuple(rows)

    def next_checkpoint_sequence(self, job_id: str) -> int:
        """The next ordinal for a job, derived from stored rows, never supplied."""
        self._guard(READ)
        highest = self._session.execute(
            select(func.max(JobCheckpointRecord.sequence)).where(
                JobCheckpointRecord.job_id == job_id
            )
        ).scalar_one_or_none()
        return 1 if highest is None else int(highest) + 1

    # -- writes --------------------------------------------------------------

    def submit(self, submission: JobSubmission) -> DurableJobRecord:
        """Record a durable job, or return the one this key already submitted.

        Idempotent by the persisted unique constraint. The lookup below turns a
        repeat into a typed result instead of a driver error; it is not the
        guarantee, and a second submission path that skipped it would still be
        refused by the database.
        """
        for value in submission.identities():
            if not value.strip():
                raise InvalidJobIdentity(
                    "a durable job needs a non-empty id, type and idempotency key"
                )
        existing = self.find_submitted(submission.job_type, submission.idempotency_key)
        if existing is not None:
            return existing
        if self.get(submission.job_id) is not None:
            raise DuplicateJobIdentity(
                f"job {submission.job_id!r} is already registered under a different "
                "idempotency key"
            )

        self._guard(WRITE)
        moment = self._clock()
        record = DurableJobRecord(
            job_id=submission.job_id,
            job_type=submission.job_type,
            idempotency_key=submission.idempotency_key,
            lifecycle_state=INITIAL_STATE,
            payload=submission.payload,
            created_at=moment,
            updated_at=moment,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def transition(self, job_id: str, target: str) -> TransitionOutcome:
        """Move a job's lifecycle state through the canonical machine.

        The machine decides. This method records the result; it never decides
        whether the move is legal, and it raises before touching the row.
        """
        record = self.require(job_id)
        outcome = self._machine.evaluate(record.lifecycle_state, target)
        self._guard(WRITE)
        record.lifecycle_state = target
        record.updated_at = self._clock()
        self._session.flush()
        return outcome

    def checkpoint(self, job_id: str, payload: dict[str, object]) -> JobCheckpointRecord:
        """Append a checkpoint to an existing job.

        The foreign key is what guarantees the job exists; the lookup here
        raises a typed error rather than a driver error.
        """
        self.require(job_id)
        sequence = self.next_checkpoint_sequence(job_id)
        self._guard(WRITE)
        record = JobCheckpointRecord(
            job_id=job_id,
            sequence=sequence,
            payload=dict(payload),
            recorded_at=self._clock(),
        )
        self._session.add(record)
        self._session.flush()
        return record
