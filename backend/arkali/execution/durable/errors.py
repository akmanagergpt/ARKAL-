"""C-19 durable job error types.

Owner: `execution.durable`.

WHY THESE ARE NOT IN `kernel.contracts.errors`. The same reason the C-12, C-14
and C-15 taxonomies are not: `arkali.kernel.contracts.errors` sits at its fan-in
budget, and ADR-0008 makes decomposition the answer to a budget rather than an
exception. The shared base stays in the kernel; the concrete types live with the
context that raises them.

Each failure mode is a distinct type so a negative control can assert the
*reason* something was refused. A control asserting only that an exception was
raised would pass for an unrelated reason - the F-0017 defect.

NO LIFECYCLE ERRORS HERE. An illegal transition is refused by the canonical Job
machine and raises the machine's own typed error, unchanged. Re-raising it as a
durable-job error would make this context look like a second transition
authority, which it is not.

Codes are allocated from 0070 upward; 0060-0065 belong to `evidence.audit`.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import ContractViolation


class InvalidJobIdentity(ContractViolation):
    """A job identity, type or idempotency key is empty or malformed."""

    code = "ARK-ERR-0070"


class DuplicateJobIdentity(ContractViolation):
    """A job id is already registered.

    Distinct from a repeated idempotency key, which is not an error: that
    returns the existing job. This is a different job claiming a taken id.
    """

    code = "ARK-ERR-0071"


class UnknownJob(ContractViolation):
    """An operation names a job that is not registered."""

    code = "ARK-ERR-0072"


class CheckpointImmutabilityViolation(ContractViolation):
    """An attempt to modify or delete a persisted checkpoint.

    A checkpoint is what a restart reads to decide where work resumed from. One
    that can be edited or removed is not a durability record.
    """

    code = "ARK-ERR-0073"


class StaleExecutionOwnership(ContractViolation):
    """A heartbeat or completion arrived from an owner that no longer holds the
    attempt, or for an attempt that has already closed.

    The durability property this protects: a slow writer from a superseded
    attempt must not be able to keep a dead execution looking alive, nor decide
    the outcome of an execution it is no longer running.
    """

    code = "ARK-ERR-0074"


class RetryBudgetExhausted(ContractViolation):
    """A further attempt was requested beyond the bound the job was admitted
    under.

    Refused rather than silently capped: a caller that believes it may retry and
    is quietly ignored has no way to distinguish that from a retry that ran.
    """

    code = "ARK-ERR-0075"


class NoOpenAttempt(ContractViolation):
    """An operation needs an open execution attempt and the job has none."""

    code = "ARK-ERR-0076"


class DeadlineNotReached(ContractViolation):
    """A timeout was forced on an attempt whose deadline has not passed.

    Refused so that timing out is a consequence of the clock, never of a caller
    deciding it would like the attempt to end.
    """

    code = "ARK-ERR-0077"
