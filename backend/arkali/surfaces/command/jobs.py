"""The durable-job enqueue surface — `ARK-REQ-0027`.

Owner: `surfaces.command`. Phase 7 Atomic Package 4.

WHAT THIS REQUIREMENT ACTUALLY SAYS. `MS §Constitution 8`: **no long AI work in
HTTP requests.** The register assigns it to `execution.durable` with `arch` and
`integ` evidence, so the requirement is about the *architecture* that makes long
work impossible in a request, not about a route being fast. The route below can
only enqueue, because enqueueing is the only thing it is able to call.

WHAT THE HANDLER DOES, IN FULL. Validate the transport shape, take a policy
decision, hand three identities and an opaque payload to C-19, and return the
durable reference. Then it ends. It opens no execution attempt, waits for
nothing, polls nothing, transitions nothing and calls no provider, and a
structural control derives the forbidden call set from the durable services
themselves rather than listing method names here.

WHY THE RESPONSE IS `202 Accepted`. It is the honest status for this contract:
the request has been accepted and the processing has **not** completed - which
is precisely what `ARK-REQ-0027` requires. It also avoids inventing a
created-versus-existing distinction that C-19's idempotency deliberately makes
irrelevant: a repeated `(job_type, idempotency_key)` resolves to the job already
recorded, and the caller gets the same reference either way.

IDEMPOTENCY IS NOT IMPLEMENTED HERE. `JobStore.submit` is idempotent by a
persisted unique constraint. This surface holds no cache, no seen-set and no
lookup of its own; an in-memory one would forget on restart, which is the single
condition durability exists for.

DELEGATION, NOT DATA ACCESS. No query, no statement, no mapped column, no
engine, no session factory. The session arrives as a dependency and goes
straight to `JobStore`, exactly as the Phase 5 routes hand theirs to
`ProjectRegistry`.

THE JOB-TYPE REGISTRY IS NOT AN ADMISSION GATE. Submitting an undeclared job
type is permitted, and that is not an oversight: C-19 records the registry as
the authority on *pause capability*, and making registration a precondition of
submitting would be admission control, which is C-21 at **Phase 8**.

NOTHING HERE SCHEDULES. No worker, queue, priority, capacity, resource or
dispatch concept appears, and no route decides when or by whom a job runs.

SEPARATE FROM `app.py` FROM THE FIRST LINE. `app.py` already touches three
bounded contexts and that is the whole `max_contexts_touched_by_module` budget -
measured before this module was written, not discovered by a firing gate.
ADR-0008 makes decomposition the answer.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.execution.durable.job_store import READ, WRITE, JobStore, JobSubmission
from arkali.execution.durable.records import DurableJobRecord, utc_now
from arkali.surfaces.command.contracts import (
    BACKEND_ONLY,
    EnqueueJobRequest,
    JobReferenceResponse,
)

#: Supplied by the composition root so this module neither builds a session nor
#: decides policy: it receives the same guard and the same refusal mapping every
#: other route on this surface uses.
_SessionScope = Callable[[], Iterator[Session]]
_Guard = Callable[[str], None]
_Refuse = Callable[[Exception], Exception]
_Clock = Callable[[], dt.datetime]

#: The two operation classes are IMPORTED from the context whose operations they
#: govern, not restated. `READ` and `WRITE` are the classes C-19 already requests
#: for its persisted governed operations, so the surface asking for a third
#: spelling of them would be a second vocabulary. No new operation class is
#: invented, and `unmapped_action_resolution: DENY` means none could be.


def _reference(record: DurableJobRecord) -> JobReferenceResponse:
    """Project the durable record onto the transport shape.

    Field by field and by name, so a column added to C-19 later cannot appear
    on the wire by accident. Nothing executional is projected.
    """
    return JobReferenceResponse(
        job_id=record.job_id,
        job_type=record.job_type,
        idempotency_key=record.idempotency_key,
        lifecycle_state=record.lifecycle_state,
        created_at=record.created_at,
    )


def build_jobs_router(
    session_scope: _SessionScope,
    guard: _Guard,
    refuse: _Refuse,
    pep: PolicyEnforcementPoint,
    clock: _Clock | None = None,
) -> APIRouter:
    """The durable-job routes, over collaborators the application supplies.

    `clock` falls back to the same UTC default C-19 uses, so a caller that
    supplies nothing gets the shipping behaviour and a test can advance time
    deterministically without the surface holding a second time source.
    """
    # BACKEND_ONLY is a declaration, not an excuse: `ARK-REQ-0027` is owned by
    # `execution.durable` with `arch, integ` evidence and no Phase 7 requirement
    # is owned by a surface context, so these routes owe no frontend. The
    # contract-drift control reads this tag off the live OpenAPI document and
    # fails on a route that declares no audience at all.
    router = APIRouter(prefix="/api", tags=[BACKEND_ONLY])
    ticking: _Clock = clock or utc_now

    def store(session: Session) -> JobStore:
        return JobStore(session, pep, ticking)

    @router.post("/jobs", response_model=JobReferenceResponse, status_code=202)
    def enqueue_job(
        body: EnqueueJobRequest, session: Session = Depends(session_scope)
    ) -> JobReferenceResponse:
        """Persist durable work and return its reference. Nothing runs here.

        The handler's whole body is: decide, submit, project, return. There is
        no branch in which work is executed, awaited or polled, and the job is
        left in the state the canonical machine declares as initial - which the
        integration evidence asserts, along with there being zero execution
        attempts against it.
        """
        guard(WRITE)
        try:
            record = store(session).submit(
                JobSubmission(
                    job_id=body.job_id,
                    job_type=body.job_type,
                    idempotency_key=body.idempotency_key,
                    payload=body.payload,
                )
            )
        except Exception as error:
            raise refuse(error) from error
        return _reference(record)

    @router.get("/jobs/{job_id}", response_model=JobReferenceResponse)
    def get_job(
        job_id: str, session: Session = Depends(session_scope)
    ) -> JobReferenceResponse:
        """Resolve a durable reference. A read, and only a read.

        This is what makes the reference returned by the enqueue route useful,
        and it is the minimum needed for that: no list, no filter, no execution
        detail and no cancellation. It reports the state C-19 recorded and never
        advances it.
        """
        guard(READ)
        try:
            record = store(session).require(job_id)
        except Exception as error:
            raise refuse(error) from error
        return _reference(record)

    return router
