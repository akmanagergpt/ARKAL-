"""Explicit historical-revision preview: "Önizle" on a non-current
`Sürüm` (Managed Product Revision History + Restore-as-New Convergence).

Owner: `surfaces.command`. Split from `jobs.py` under the same ADR-0008
decomposition `product_change_bridge.py`/`product_change_routes.py`
already used — `jobs.py` already carries the generic job routes plus the
current-revision preview bridge, and is already the largest module in
this context.

EPHEMERAL, NEVER A SECOND PREVIEW PATH. This module submits/recovers
through the SAME `_submit_or_recover_preview`/`_find_current_preview`
(`jobs.py`, unmodified) every other preview route already uses, and the
SAME `candidate.preview` job type/worker (`scripts/run_candidate_preview_
worker.py`'s own `_revision_preview`, already generic over any explicit
`revision_id`, not only the current one -- zero changes needed there).
Previewing revision 1 while revision 2 is current changes nothing in
`ProjectRegistry`, `CandidateLedger` or the current-revision resolution
`jobs.py`'s own `/projects/{project_id}/preview` route uses — it is a
real, isolated, read-only runtime cycle over that one revision's own
immutable source, keyed by that revision's own real identity
(`_PreviewSubject.subject_id`), so it can never be confused with, or
silently promoted into, a preview of any other revision.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from arkali.control.registry.project.registry import ProjectRegistry
from arkali.execution.durable.job_store import READ, WRITE, JobStore
from arkali.execution.durable.records import utc_now
from arkali.surfaces.command.contracts import BROWSER_SLICE, JobReferenceResponse
from arkali.surfaces.command.jobs import _find_current_preview, _reference, _submit_or_recover_preview
from arkali.surfaces.command.product_preview_resolution import (
    _PreviewBridgeWiring,
    _resolve_preview_subject_for_explicit_revision,
)

_SessionScope = Callable[[], Iterator[Session]]
_Guard = Callable[[str], None]
_Refuse = Callable[[Exception], Exception]
_Clock = Callable[[], object]


def _build_revision_preview_router(
    session_scope: _SessionScope, guard: _Guard, refuse: _Refuse, pep: object,
    preview_bridge: _PreviewBridgeWiring, clock: _Clock | None = None,
) -> APIRouter:
    """The two real explicit-revision preview routes. `preview_bridge` is
    required (never `None`) — the composition root only calls this when
    it wants the capability, exactly as `build_jobs_router`'s own
    `/projects/{project_id}/preview` route is only ever added the same
    way."""
    router = APIRouter(prefix="/api")
    ticking: _Clock = clock or utc_now

    def store(session: Session) -> JobStore:
        return JobStore(session, pep, ticking)

    @router.post(
        "/projects/{project_id}/revisions/{revision_id}/preview",
        response_model=JobReferenceResponse, status_code=202, tags=[BROWSER_SLICE],
    )
    def start_revision_preview(
        project_id: str, revision_id: str,
        session: Session = Depends(session_scope),
        artifact_session: Session = Depends(preview_bridge.artifact_session_scope),
    ) -> JobReferenceResponse:
        """"Önizle" on an explicitly selected historical `Sürüm` — never
        the project's current revision by default, always exactly the
        one named in the path. Ephemeral: creates no `ProjectRevisionRecord`,
        changes no current revision, and never mutates `CandidateLedger`.
        """
        guard(WRITE)
        try:
            subject = _resolve_preview_subject_for_explicit_revision(
                project_id, revision_id, registry=ProjectRegistry(session),
                artifact_session=artifact_session, wiring=preview_bridge,
            )
            payload = (
                {"candidate_id": subject.subject_id} if subject.kind == "candidate"
                else {"project_id": project_id, "revision_id": subject.revision_id}
            )
            record = _submit_or_recover_preview(store(session), subject.subject_id, payload)
        except Exception as error:
            raise refuse(error) from error
        return _reference(record)

    @router.get(
        "/projects/{project_id}/revisions/{revision_id}/preview",
        response_model=JobReferenceResponse | None, tags=[BROWSER_SLICE],
    )
    def find_revision_preview(
        project_id: str, revision_id: str,
        session: Session = Depends(session_scope),
        artifact_session: Session = Depends(preview_bridge.artifact_session_scope),
    ) -> JobReferenceResponse | None:
        """Read-only counterpart for browser refresh — the same real
        shape every other preview route's `find_*` already gives."""
        guard(READ)
        try:
            subject = _resolve_preview_subject_for_explicit_revision(
                project_id, revision_id, registry=ProjectRegistry(session),
                artifact_session=artifact_session, wiring=preview_bridge,
            )
        except Exception as error:
            raise refuse(error) from error
        record = _find_current_preview(store(session), subject.subject_id)
        return None if record is None else _reference(record)

    return router
