"""Command transport for the Phase 30 production factory.

The surface validates transport, delegates once to the injected
``engineering.factory`` boundary and projects its result.  It contains no
software-factory orchestration and performs no provider work in the request.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from arkali.surfaces.command.contracts import BACKEND_ONLY


class _FactoryGoalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=64)
    goal_text: str = Field(min_length=1)
    capability_id: str | None = Field(default=None, min_length=1)


class _FactoryIntakeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    goal_id: str
    blueprint_id: str
    state: str
    selected_tier: str | None
    unresolved_count: int
    durable_job_id: str | None


SessionScope = Callable[[], Iterator[Session]]
_FactorySubmitter = Callable[[Session, _FactoryGoalRequest], Any]
Guard = Callable[[str], None]


def _build_factory_router(
    session_scope: SessionScope, guard: Guard, write_operation: str,
    submitter: _FactorySubmitter,
) -> APIRouter:
    router = APIRouter(prefix="/api/factory", tags=[BACKEND_ONLY])

    @router.post("/goals", response_model=_FactoryIntakeResponse, status_code=202)
    def submit_goal(
        body: _FactoryGoalRequest, session: Session = Depends(session_scope)  # noqa: B008
    ) -> _FactoryIntakeResponse:
        guard(write_operation)
        result = submitter(session, body)
        return _FactoryIntakeResponse(**result.model_dump(mode="json"))

    return router


__all__: list[str] = []
