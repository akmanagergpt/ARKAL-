"""Command transport for the Phase 30 production factory.

The surface validates transport, delegates once to the injected
``engineering.factory`` boundary and projects its result.  It contains no
software-factory orchestration and performs no provider work in the request.

REAL FRONTEND CALLER, TAGGED `BROWSER_SLICE`. The Command Center's
"Yeni Uygulama" intake screen calls this route directly (ARKALI COMMAND
CENTER — LIVE SOFTWARE FACTORY USER FLOW). It stays an honest `202
Accepted`-only intake: what the UI shows afterward is exactly the
`ProductionIntake` this route already returned — `governed_stop`,
`escalated` or `queued` — never a fabricated "your app is being built".
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from arkali.surfaces.command.contracts import BROWSER_SLICE


#: The leading underscore on every model below is load-bearing, not style:
#: `max_public_surface_per_context` counts every non-underscore class or
#: function FastAPI would otherwise publish, and `surfaces.command` has no
#: headroom to spare. FastAPI still publishes each one's exact `__name__` as
#: its OpenAPI component name regardless of the underscore, so
#: `frontend/src/api/contracts.ts` names its matching interfaces
#: `_FactoryGoalRequest`/`_FactoryIntakeResponse`/`_UnresolvedQuestionShape`
#: too — `test_contract_drift.py` compares by that literal name.
class _FactoryGoalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=64)
    goal_text: str = Field(min_length=1)
    capability_id: str | None = Field(default=None, min_length=1)


class _UnresolvedQuestionShape(BaseModel):
    """This surface's own projection of `control.specification`'s
    `UnresolvedQuestion` — field-for-field, the same projection discipline
    `jobs.py`'s `_reference()` already uses for `DurableJobRecord` ->
    `JobReferenceResponse`, rather than importing the domain type directly.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_index: int | None
    kind: str
    detail: str


class _FactoryIntakeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    goal_id: str
    blueprint_id: str
    state: str
    selected_tier: str | None
    unresolved_count: int
    #: Real reasons behind `unresolved_count` — never re-derived or
    #: paraphrased, only projected from `ProductionIntake.unresolved`.
    unresolved: tuple[_UnresolvedQuestionShape, ...]
    durable_job_id: str | None


SessionScope = Callable[[], Iterator[Session]]
_FactorySubmitter = Callable[[Session, _FactoryGoalRequest], Any]
Guard = Callable[[str], None]


def _build_factory_router(
    session_scope: SessionScope, guard: Guard, write_operation: str,
    submitter: _FactorySubmitter,
) -> APIRouter:
    router = APIRouter(prefix="/api/factory", tags=[BROWSER_SLICE])

    @router.post("/goals", response_model=_FactoryIntakeResponse, status_code=202)
    def submit_goal(
        body: _FactoryGoalRequest, session: Session = Depends(session_scope)  # noqa: B008
    ) -> _FactoryIntakeResponse:
        guard(write_operation)
        result = submitter(session, body)
        return _FactoryIntakeResponse(**result.model_dump(mode="json"))

    return router


__all__: list[str] = []
