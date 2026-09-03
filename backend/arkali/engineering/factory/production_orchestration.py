"""Shipping Phase 30 goal-intake composition (D-027).

Owner: ``engineering.factory``.  This module owns only the top-level ordering
of already-canonical authorities.  Blueprint derivation remains
``control.specification``; tier selection remains this context's existing
D-026 service; durable persistence is reached through a structural port so no
job lifecycle, scheduler, workflow, provider, repair, acceptance or release
authority is reproduced here.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.capability.capability_graph import CapabilityQueryResult
from arkali.control.specification.blueprint_contracts import (
    RequirementBlueprint,
    UnresolvedQuestion,
)
from arkali.control.specification.blueprint_engine import derive_blueprint
from arkali.engineering.factory.execution_routing import (
    ExecutionTier,
    TierEligibilityRequest,
    TierSelection,
    select_execution_tier,
)


class DurableFactorySink(Protocol):
    """Structural boundary to C-19; the durable authority owns the record."""

    def enqueue(self, request_id: str, payload: dict[str, object]) -> str: ...


class FactoryIntakeState(enum.StrEnum):
    GOVERNED_STOP = "governed_stop"
    ESCALATED = "escalated"
    QUEUED = "queued"


class ProductionGoalRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=64)
    goal_text: str = Field(min_length=1)
    capability_id: str | None = Field(default=None, min_length=1)


class ProductionIntake(BaseModel):
    """An honest intake result; it carries no product-acceptance verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    goal_id: str
    blueprint_id: str
    state: FactoryIntakeState
    selected_tier: ExecutionTier | None = None
    unresolved_count: int = Field(ge=0)
    #: The real, mechanically-derived reasons behind `unresolved_count` — the
    #: same `UnresolvedQuestion` values `blueprint.unresolved` already holds,
    #: reused unmodified rather than restated, so a caller can explain a
    #: `GOVERNED_STOP` instead of only counting it.
    unresolved: tuple[UnresolvedQuestion, ...] = ()
    durable_job_id: str | None = None


class ProductionFactory:
    """Compose goal derivation, routing and durable submission, in that order."""

    def __init__(
        self,
        authority_map: AuthorityMap,
        capability_query: Callable[[str], CapabilityQueryResult] | None = None,
    ) -> None:
        self._authority_map = authority_map
        self._capability_query = capability_query

    def submit_goal(
        self, request: ProductionGoalRequest, sink: DurableFactorySink
    ) -> ProductionIntake:
        blueprint = derive_blueprint(request.goal_text, self._authority_map)
        if not blueprint.is_fully_resolved:
            return self._result(request, blueprint, FactoryIntakeState.GOVERNED_STOP)

        selection = select_execution_tier(
            TierEligibilityRequest(
                task_id=request.request_id,
                deterministic_capable=False,
                capability_id=request.capability_id,
            ),
            capability_query=self._capability_query,
        )
        if not selection.is_automated:
            return self._result(
                request, blueprint, FactoryIntakeState.ESCALATED, selection
            )

        payload: dict[str, object] = {
            "goal": blueprint.goal.model_dump(mode="json"),
            "blueprint": blueprint.model_dump(mode="json"),
            "blueprint_id": blueprint.blueprint_id,
            "selected_tier": selection.selected.value,
        }
        durable_job_id = sink.enqueue(request.request_id, payload)
        return self._result(
            request, blueprint, FactoryIntakeState.QUEUED, selection, durable_job_id
        )

    @staticmethod
    def _result(
        request: ProductionGoalRequest,
        blueprint: RequirementBlueprint,
        state: FactoryIntakeState,
        selection: TierSelection | None = None,
        durable_job_id: str | None = None,
    ) -> ProductionIntake:
        return ProductionIntake(
            request_id=request.request_id,
            goal_id=blueprint.goal.goal_id,
            blueprint_id=blueprint.blueprint_id,
            state=state,
            selected_tier=selection.selected if selection is not None else None,
            unresolved_count=len(blueprint.unresolved),
            unresolved=blueprint.unresolved,
            durable_job_id=durable_job_id,
        )


__all__ = [
    "DurableFactorySink",
    "FactoryIntakeState",
    "ProductionFactory",
    "ProductionGoalRequest",
    "ProductionIntake",
]
