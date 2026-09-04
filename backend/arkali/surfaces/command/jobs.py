"""The durable-job enqueue and real-progress surface — `ARK-REQ-0027`.

Owner: `surfaces.command`. Phase 7 Atomic Package 4.

REAL FRONTEND CALLERS ON FIVE OF SIX ROUTES. `GET /jobs/{job_id}` and
`GET /jobs/{job_id}/checkpoints` are tagged `BROWSER_SLICE`: the Command
Center's "Yeni Uygulama" screen polls them to show real progress for a
real `software_factory.production` job (ARKALI COMMAND CENTER — DEF-009
FLOW A CONVERGENCE AUTHORIZATION, item 9). The generic `POST /jobs` stays
`BACKEND_ONLY` — no route here should hand the frontend a bare (job_type,
idempotency_key, payload) triple to construct by hand, the same reason
`POST /api/factory/goals` exists instead of the frontend calling
`POST /jobs` directly for a goal. `POST /candidates/{candidate_id}/preview`
is that same shape for "Uygulamayı Aç": a real, domain-specific intake
that derives a deterministic job identity from `candidate_id` alone and
submits it — nothing new for C-19 to learn, one more real caller of the
same `submit`. `GET /candidates/{candidate_id}/preview` is its read-only
counterpart, added so a browser refresh can rediscover a real preview
without a page load itself enqueuing one. `POST /jobs/{job_id}/cancel` is
"Durdur" — see its own docstring for why it checkpoints a request rather
than transitioning anything itself.

WHAT THIS REQUIREMENT ACTUALLY SAYS. `MS §Constitution 8`: **no long AI work in
HTTP requests.** The register assigns it to `execution.durable` with `arch` and
`integ` evidence, so the requirement is about the *architecture* that makes long
work impossible in a request, not about a route being fast. Every route below
can only enqueue or checkpoint, because that is the only thing any of them is
able to call.

WHAT THE HANDLERS DO, IN FULL. Validate the transport shape, take a policy
decision, hand identities and an opaque payload to C-19, and return the
durable reference. Then they end. None opens an execution attempt, waits for
anything, polls anything, transitions anything or calls a provider, and a
structural control derives the forbidden call set from the durable services
themselves (`transition` included) rather than listing method names here —
`cancel_job` below is held to the exact same control as every other route.

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
import itertools
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.execution.durable.job_state_machine import DEFINITION as _JOB_MACHINE
from arkali.execution.durable.job_store import READ, WRITE, JobStore, JobSubmission
from arkali.execution.durable.records import (
    DurableJobRecord,
    JobCheckpointRecord,
    utc_now,
)
from arkali.surfaces.command.contracts import (
    BACKEND_ONLY,
    BROWSER_SLICE,
    EnqueueJobRequest,
    _JobCheckpointResponse,
    JobReferenceResponse,
)
from arkali.surfaces.command.product_preview_resolution import (
    _PreviewBridgeWiring,
    _resolve_candidate_for_project,
)

#: The one real `job_type` this route submits — the frontend never
#: constructs this string itself (ARK-REQ-0074-style: this surface names
#: the identity shape, not a candidate domain fact).
_PREVIEW_JOB_TYPE = "candidate.preview"

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


def _preview_scope_key(candidate_id: str, attempt: int) -> str:
    """The idempotency scope for one preview cycle. `attempt == 1` keeps the
    original, already-shipped identity byte-for-byte (`candidate_id` alone),
    so an already-open or already-terminal FIRST preview is unaffected;
    `attempt > 1` is a real, later preview cycle for the SAME candidate,
    never a second candidate or a second job TYPE."""
    return candidate_id if attempt == 1 else f"{candidate_id}#{attempt}"


def _submit_or_recover_preview(store: JobStore, candidate_id: str) -> DurableJobRecord:
    """"Uygulamayı Aç" for one candidate: rediscover the real active preview
    if one exists, or mint the next real preview cycle if every prior one
    for this candidate has already reached a real terminal state.

    REUSES C-19's OWN idempotent `submit` for every write; the only new
    logic is WHICH `(job_type, idempotency_key)` to ask for, derived purely
    by reading existing rows through the already-public `find_submitted` --
    no new table, no new column, no counter held anywhere but the real
    `DurableJobRecord` rows already being asked about. `DEFINITION.terminal`
    (`execution.durable.job_state_machine`, the SAME canonical Job machine
    `JobStore.transition` itself defers to) is the one true "is this job
    still active" fact reused here -- never a second, guessed vocabulary.
    A job in `RECOVERABLE` is deliberately treated as still-active-enough-
    to-rediscover: it is not in `DEFINITION.terminal` (the machine's own
    docstring: "FAILED is deliberately not terminal so a failed job can
    still reach... RECOVERABLE"), so a later real recovery could still move
    it forward under the SAME identity, and minting a fresh one underneath
    it would silently orphan that recovery path.
    """
    for attempt in itertools.count(1):
        key = _preview_scope_key(candidate_id, attempt)
        existing = store.find_submitted(_PREVIEW_JOB_TYPE, key)
        if existing is None:
            return store.submit(
                JobSubmission(
                    job_id=f"preview-{key}", job_type=_PREVIEW_JOB_TYPE,
                    idempotency_key=key, payload={"candidate_id": candidate_id},
                )
            )
        if existing.lifecycle_state not in _JOB_MACHINE.terminal:
            return existing
    raise AssertionError("unreachable")  # pragma: no cover


def _find_current_preview(store: JobStore, candidate_id: str) -> DurableJobRecord | None:
    """The most recent real preview cycle for this candidate — whether
    still active or already terminal — never an old cycle a newer one has
    superseded, and never a fabricated "still running" for a candidate
    nobody has opened. `None` only when attempt 1 itself was never
    submitted."""
    latest: DurableJobRecord | None = None
    for attempt in itertools.count(1):
        found = store.find_submitted(_PREVIEW_JOB_TYPE, _preview_scope_key(candidate_id, attempt))
        if found is None:
            return latest
        latest = found
    raise AssertionError("unreachable")  # pragma: no cover


def _checkpoint(record: JobCheckpointRecord) -> _JobCheckpointResponse:
    """Project one checkpoint row unchanged — the payload a worker recorded,
    never re-derived or paraphrased here."""
    return _JobCheckpointResponse(
        sequence=record.sequence, payload=record.payload, recorded_at=record.recorded_at,
    )


def build_jobs_router(
    session_scope: _SessionScope,
    guard: _Guard,
    refuse: _Refuse,
    pep: PolicyEnforcementPoint,
    clock: _Clock | None = None,
    preview_bridge: _PreviewBridgeWiring | None = None,
) -> APIRouter:
    """The durable-job routes, over collaborators the application supplies.

    `clock` falls back to the same UTC default C-19 uses, so a caller that
    supplies nothing gets the shipping behaviour and a test can advance time
    deterministically without the surface holding a second time source.

    `preview_bridge` is `(artifact_session_scope, artifact_blobs, ledger)`
    for the one additional route below, `POST /projects/{project_id}/
    preview` — see `product_preview_resolution.py`'s own module docstring
    for why the evidence-store session is a second, separate dependency
    from `session_scope` above (a real, separate database file, exactly as
    every script already touching both `command_center.db` and the
    evidence store keeps them). `None` (the default) omits that one route
    entirely, so every existing caller of `build_jobs_router` is
    unaffected — the identical `workflow_wiring`/`operations_wiring`
    additive-and-optional shape `app.py` already uses for its own optional
    capabilities.
    """
    # No router-level tag: the two original routes were both BACKEND_ONLY
    # (ARK-REQ-0027 is owned by `execution.durable`, no Phase 7 requirement
    # is owned by a surface context, so they owe no frontend), but
    # `GET /jobs/{job_id}` and `GET /jobs/{job_id}/checkpoints` now have a
    # real frontend caller (ARKALI COMMAND CENTER — DEF-009 FLOW A
    # CONVERGENCE AUTHORIZATION, item 9) and must carry their OWN tag, or
    # the router-level one would silently apply to every route. Each route
    # below declares exactly one; the contract-drift control reads this off
    # the live OpenAPI document and fails on a route that declares zero,
    # two, or the wrong one.
    router = APIRouter(prefix="/api")
    ticking: _Clock = clock or utc_now

    def store(session: Session) -> JobStore:
        return JobStore(session, pep, ticking)

    @router.post(
        "/jobs", response_model=JobReferenceResponse, status_code=202,
        tags=[BACKEND_ONLY],
    )
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

    @router.post(
        "/candidates/{candidate_id}/preview", response_model=JobReferenceResponse,
        status_code=202, tags=[BROWSER_SLICE],
    )
    def start_preview(
        candidate_id: str, session: Session = Depends(session_scope)
    ) -> JobReferenceResponse:
        """Enqueue "Uygulamayı Aç" for one candidate. A real, domain-specific
        intake over the same `submit` the generic route uses — the frontend
        never builds a `(job_type, idempotency_key)` pair itself, the same
        reason `POST /api/factory/goals` exists instead of a raw job POST.

        Calling this while a real preview for this candidate is already
        active (QUEUED/RUNNING/CHECKPOINTED/PAUSED/RESUMING/RECOVERABLE)
        rediscovers that same real job — never a duplicate, and the whole
        mechanism a browser refresh needs. Calling it again after the
        candidate's most recent preview has reached a real terminal state
        (`_JOB_MACHINE.terminal`) mints the next real preview cycle for the
        SAME candidate instead of resurrecting the dead one — "Aç" after
        "Durdur" genuinely starts a new run.
        """
        guard(WRITE)
        try:
            record = _submit_or_recover_preview(store(session), candidate_id)
        except Exception as error:
            raise refuse(error) from error
        return _reference(record)

    @router.get(
        "/candidates/{candidate_id}/preview", response_model=JobReferenceResponse | None,
        tags=[BROWSER_SLICE],
    )
    def find_preview(
        candidate_id: str, session: Session = Depends(session_scope)
    ) -> JobReferenceResponse | None:
        """Whether a real preview job already exists for this candidate,
        without creating one. A read, and only a read — the whole mechanism
        a browser refresh needs to rediscover a preview that was already
        opening, already ready, or already stopped, without the page load
        itself enqueuing anything: `start_preview` is a real user action
        (a click), this is not. `null` means honestly nothing yet, not an
        error — a fresh candidate nobody has opened is not a refusal.
        """
        guard(READ)
        record = _find_current_preview(store(session), candidate_id)
        return None if record is None else _reference(record)

    if preview_bridge is not None:

        @router.post(
            "/projects/{project_id}/preview", response_model=JobReferenceResponse,
            status_code=202, tags=[BROWSER_SLICE],
        )
        def start_project_preview(
            project_id: str,
            session: Session = Depends(session_scope),
            artifact_session: Session = Depends(preview_bridge.artifact_session_scope),
        ) -> JobReferenceResponse:
            """"Uygulamayı Aç" from Product Detail. Resolves the Managed
            Product's one real accepted candidate through the canonical
            D-029 chain (`ProjectRegistry` -> `provenance_ref` ->
            `ArtifactStore` -> `CandidateLedger` eligibility,
            `product_preview_resolution.py`), then submits/recovers its
            real preview through the IDENTICAL `_submit_or_recover_preview`
            the candidate-direct route above already uses — never a second
            preview path, never a second identity for the same candidate.
            """
            guard(WRITE)
            try:
                candidate_id = _resolve_candidate_for_project(
                    project_id, registry=ProjectRegistry(session),
                    artifact_session=artifact_session, wiring=preview_bridge,
                )
                record = _submit_or_recover_preview(store(session), candidate_id)
            except Exception as error:
                raise refuse(error) from error
            return _reference(record)

        @router.get(
            "/projects/{project_id}/preview", response_model=JobReferenceResponse | None,
            tags=[BROWSER_SLICE],
        )
        def find_project_preview(
            project_id: str,
            session: Session = Depends(session_scope),
            artifact_session: Session = Depends(preview_bridge.artifact_session_scope),
        ) -> JobReferenceResponse | None:
            """Read-only counterpart for browser refresh — the same real
            shape `find_preview` already gives the candidate-direct route,
            resolved through the same canonical chain as the POST above.
            """
            guard(READ)
            try:
                candidate_id = _resolve_candidate_for_project(
                    project_id, registry=ProjectRegistry(session),
                    artifact_session=artifact_session, wiring=preview_bridge,
                )
            except Exception as error:
                raise refuse(error) from error
            record = _find_current_preview(store(session), candidate_id)
            return None if record is None else _reference(record)

    @router.get(
        "/jobs/{job_id}", response_model=JobReferenceResponse, tags=[BROWSER_SLICE],
    )
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

    @router.get(
        "/jobs/{job_id}/checkpoints", response_model=list[_JobCheckpointResponse],
        tags=[BROWSER_SLICE],
    )
    def list_checkpoints(
        job_id: str, session: Session = Depends(session_scope)
    ) -> list[_JobCheckpointResponse]:
        """Every real checkpoint C-19 holds for this job, oldest first — the
        real progress evidence a worker recorded. A read, and only a read;
        this route derives nothing and stores nothing of its own."""
        guard(READ)
        job_store = store(session)
        try:
            job_store.require(job_id)
        except Exception as error:
            raise refuse(error) from error
        return [_checkpoint(row) for row in job_store.checkpoints(job_id)]

    @router.post(
        "/jobs/{job_id}/cancel", response_model=JobReferenceResponse, tags=[BROWSER_SLICE],
    )
    def cancel_job(
        job_id: str, session: Session = Depends(session_scope)
    ) -> JobReferenceResponse:
        """Request early termination of a real job — Command Center's real
        "Durdur".

        WHY THIS CHECKPOINTS RATHER THAN TRANSITIONS. `transition` is one of
        this module's own forbidden calls (`test_enqueue_surface_authority.
        py::TestTheRouteCannotExecuteTheWork`): an HTTP request may enqueue
        durable work and record a real fact about it, but it may not itself
        move a job's lifecycle state — only a worker, watching that state on
        its own schedule, does that (`scripts/run_candidate_preview_worker.
        py`). This route's whole job is to leave a real, durable `{"phase":
        "cancel_requested"}` checkpoint the worker's own poll loop reads and
        acts on. Idempotent for free: pressing "Durdur" twice just appends a
        second identical checkpoint, never an error.
        """
        guard(WRITE)
        job_store = store(session)
        try:
            record = job_store.require(job_id)
            job_store.checkpoint(job_id, {"phase": "cancel_requested"})
        except Exception as error:
            raise refuse(error) from error
        return _reference(record)

    return router
