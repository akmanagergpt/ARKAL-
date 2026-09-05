"""The Managed Product change-request routes: "Değişikliği Başlat" /
"Kabul Et" / "Vazgeç" (D-030 V1).

Owner: `surfaces.command`. Split from `jobs.py` under ADR-0008
decomposition — `jobs.py` was already at its own `max_module_logical_
lines` budget, the identical reason that module itself is already
separate from `app.py`.

"VAZGEÇ" NEEDS NO ROUTE OF ITS OWN HERE. It is the EXISTING, unchanged
`POST /jobs/{job_id}/cancel` from `jobs.py` — see `product_change_bridge.
py`'s own module docstring for why.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from arkali.execution.durable.job_state_machine import FAILED
from arkali.execution.durable.job_state_machine import DEFINITION as _JOB_MACHINE
from arkali.execution.durable.job_store import READ, WRITE, JobStore, JobSubmission
from arkali.execution.durable.records import DurableJobRecord, utc_now
from arkali.surfaces.command.contracts import (
    BROWSER_SLICE,
    JobReferenceResponse,
    _ChangePromotionResponse,
    _StartChangeRequest,
)
from arkali.surfaces.command.jobs import _reference
from arkali.surfaces.command.product_change_bridge import _ProductChangeWiring, _promote_ready_change

_CHANGE_JOB_TYPE = "managed_product.change"
#: `execution.durable.job_state_machine.DEFINITION.terminal` deliberately
#: excludes `FAILED` (a failed job may still reach a real `RECOVERABLE`
#: retry — see that module's own docstring), the assumption `jobs.
#: _submit_or_recover_preview` inherits correctly since a preview worker
#: crash genuinely can be retried. `scripts/run_product_change_worker.py`
#: implements no such recovery for `managed_product.change` -- a real
#: `ModelPlanInvalidError`/refusal is genuinely final for that one cycle —
#: so this scope key treats `FAILED` as terminal too, or a user whose
#: request hit a transient provider timeout would be shown that same dead
#: job forever and could never submit a new one.
_CHANGE_DONE_STATES = _JOB_MACHINE.terminal + (FAILED,)

_SessionScope = Callable[[], Iterator[Session]]
_Guard = Callable[[str], None]
_Refuse = Callable[[Exception], Exception]
_Clock = Callable[[], object]


def _change_scope_key(project_id: str, attempt: int) -> str:
    """Same shape as `jobs._preview_scope_key`, one change cycle per attempt."""
    return project_id if attempt == 1 else f"{project_id}#{attempt}"


def _submit_or_recover_change(
    store: JobStore, project_id: str, payload: dict[str, object],
) -> DurableJobRecord:
    """One project's real change-or-restore proposal slot — identical
    reasoning to `jobs._submit_or_recover_preview`. `payload` carries
    either `request_text` ("Değişikliği Başlat") or
    `source_basis_revision_id` ("Bu sürüme geri dön") — opaque here
    either way, since only the worker (`scripts/run_product_change_
    worker.py`) branches on its shape; a project has exactly one active
    change-or-restore proposal at a time, matching the single real
    `managed_product.change` job type both share."""
    for attempt in itertools.count(1):
        key = _change_scope_key(project_id, attempt)
        existing = store.find_submitted(_CHANGE_JOB_TYPE, key)
        if existing is None:
            return store.submit(
                JobSubmission(
                    job_id=f"change-{key}", job_type=_CHANGE_JOB_TYPE,
                    idempotency_key=key, payload=payload,
                )
            )
        if existing.lifecycle_state not in _CHANGE_DONE_STATES:
            return existing
    raise AssertionError("unreachable")  # pragma: no cover


def _find_current_change(store: JobStore, project_id: str) -> DurableJobRecord | None:
    """Identical reasoning to `jobs._find_current_preview`."""
    latest: DurableJobRecord | None = None
    for attempt in itertools.count(1):
        found = store.find_submitted(_CHANGE_JOB_TYPE, _change_scope_key(project_id, attempt))
        if found is None:
            return latest
        latest = found
    raise AssertionError("unreachable")  # pragma: no cover


def _build_product_change_router(
    session_scope: _SessionScope, guard: _Guard, refuse: _Refuse, pep: object,
    clock: _Clock | None, product_change: _ProductChangeWiring,
) -> APIRouter:
    """The three real Managed Product change routes. `product_change` is
    required (never `None`) — the composition root only calls this at all
    when it wants the capability, exactly as `build_workflow_router`
    itself is only ever called inside `if workflow_wiring is not None`.
    """
    router = APIRouter(prefix="/api")
    ticking = clock or utc_now

    def store(session: Session) -> JobStore:
        return JobStore(session, pep, ticking)

    @router.post(
        "/projects/{project_id}/changes", response_model=JobReferenceResponse,
        status_code=202, tags=[BROWSER_SLICE],
    )
    def start_change(
        project_id: str, body: _StartChangeRequest, session: Session = Depends(session_scope),
    ) -> JobReferenceResponse:
        """Enqueue "Değişikliği Başlat" for one project — a real, domain-
        specific intake over the same idempotent `submit` every other
        durable-job route on this surface uses."""
        guard(WRITE)
        try:
            record = _submit_or_recover_change(
                store(session), project_id,
                {"project_id": project_id, "request_text": body.request_text},
            )
        except Exception as error:
            raise refuse(error) from error
        return _reference(record)

    @router.post(
        "/projects/{project_id}/revisions/{revision_id}/restore",
        response_model=JobReferenceResponse, status_code=202, tags=[BROWSER_SLICE],
    )
    def start_restore(
        project_id: str, revision_id: str, session: Session = Depends(session_scope),
    ) -> JobReferenceResponse:
        """"Bu sürüme geri dön" — enqueue a real restore proposal over the
        SAME `managed_product.change` job type and the SAME per-project
        idempotency slot "Değişikliği Başlat" uses (a project has exactly
        one active change-or-restore proposal at a time); the worker
        distinguishes the payload shape and calls `engineering.product_
        change.restore.prepare_restore` instead of `prepare_modification`
        — no model is ever invoked for a pure restore. `revision_id` is
        the SOURCE-BASIS revision being restored, never required to be
        the project's current revision.
        """
        guard(WRITE)
        try:
            record = _submit_or_recover_change(
                store(session), project_id,
                {"project_id": project_id, "source_basis_revision_id": revision_id},
            )
        except Exception as error:
            raise refuse(error) from error
        return _reference(record)

    @router.get(
        "/projects/{project_id}/changes", response_model=JobReferenceResponse | None,
        tags=[BROWSER_SLICE],
    )
    def find_change(
        project_id: str, session: Session = Depends(session_scope),
    ) -> JobReferenceResponse | None:
        """Read-only rediscovery for a browser refresh — the same shape
        `find_preview` already gives the preview bridge."""
        guard(READ)
        record = _find_current_change(store(session), project_id)
        return None if record is None else _reference(record)

    @router.post(
        "/projects/{project_id}/changes/{job_id}/promote",
        response_model=_ChangePromotionResponse, tags=[BROWSER_SLICE],
    )
    def promote_change(
        project_id: str, job_id: str, session: Session = Depends(session_scope),
    ) -> _ChangePromotionResponse:
        """"Kabul Et" — real, synchronous promotion (see `product_change_
        bridge.py` for why this is safe in-request, and never a durable
        job of its own). Leaves a real `{"phase": "promoted"}` checkpoint
        on success — a recorded fact, never a `transition` call (the same
        distinction `cancel_job` already draws for "Durdur") — so the
        still-live worker's own poll loop notices and stops the review
        preview, transitioning the job to SUCCEEDED itself."""
        guard(WRITE)
        job_store = store(session)
        try:
            result = _promote_ready_change(
                project_id, job_id, store=job_store, wiring=product_change,
            )
        except Exception as error:
            raise refuse(error) from error
        job_store.checkpoint(job_id, {"phase": "promoted", **result})
        return _ChangePromotionResponse(
            revision_id=str(result["revision_id"]), provenance_ref=str(result["provenance_ref"]),
        )

    return router
