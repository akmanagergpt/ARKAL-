"""C-19 durable-job error to HTTP-status mapping.

Owner: `surfaces.command`. Phase 7 Atomic Package 4.

WHY THIS IS A SEPARATE MODULE, AND WHY IT WAS SEPARATE FROM THE FIRST LINE.
`error_mapping.py` already touches three bounded contexts -
`control.registry.project`, `control.policy` and `kernel.contracts` - which is
exactly `max_contexts_touched_by_module`. Measured before writing anything, not
discovered by a firing gate. Adding the `execution.durable` taxonomy there would
have made four, so the durable half lives here and `error_mapping.py` composes
it across a same-context import. ADR-0008 makes decomposition the answer; this
is the same reasoning that put `error_mapping.py` outside `app.py` at Phase 5.

NOTHING IS SWALLOWED AND NOTHING IS DEFAULTED. Only the refusals this surface
genuinely has an opinion about appear. An unmapped durable error propagates, so
an unforeseen failure surfaces as a server error rather than being reported as a
client mistake.

LIFECYCLE REFUSALS ARE NOT HERE. An illegal Job transition raises the canonical
machine's own typed error, which `error_mapping.py` already maps for every
machine in the repository. Restating those here would be a second mapping for
one taxonomy.
"""

from __future__ import annotations

from typing import Final

from arkali.execution.durable.errors import (
    DuplicateJobIdentity,
    DuplicateJobType,
    InvalidJobIdentity,
    PauseNotSupported,
    UnknownJob,
    UnknownJobType,
)

#: Ordered most-specific first, matching the sibling table's discipline.
#:
#: `InvalidJobIdentity` is 400 because an empty or malformed id, type or
#: idempotency key is a request the caller can fix. An **unregistered** job type
#: is deliberately NOT an enqueue error at all: C-19 records the job-type
#: registry as the authority on pause capability, not as a precondition of
#: submitting, because requiring registration to submit is admission control and
#: admission is C-21 at Phase 8. `UnknownJobType` is mapped for the operations
#: that genuinely ask a type about its capabilities.
DURABLE_STATUS_BY_ERROR: Final[tuple[tuple[type[Exception], int], ...]] = (
    (UnknownJob, 404),
    (UnknownJobType, 404),
    (DuplicateJobIdentity, 409),
    (DuplicateJobType, 409),
    (PauseNotSupported, 409),
    (InvalidJobIdentity, 400),
)


def durable_error_types() -> tuple[type[Exception], ...]:
    """Every durable error type this surface maps. Read by the coverage control."""
    return tuple(error_type for error_type, _ in DURABLE_STATUS_BY_ERROR)
