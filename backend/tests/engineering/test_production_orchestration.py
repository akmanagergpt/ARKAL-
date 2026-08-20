from __future__ import annotations

import pathlib

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.capability.capability_graph import CapabilityQueryResult
from arkali.engineering.factory.production_orchestration import (
    FactoryIntakeState,
    ProductionFactory,
    ProductionGoalRequest,
)
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]
RESOLVED_GOAL = "The system must respond within at least 200 ms."


class RecordingSink:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def enqueue(self, request_id: str, payload: dict[str, object]) -> str:
        self.calls.append((request_id, payload))
        return request_id


def _request(goal: str = RESOLVED_GOAL) -> ProductionGoalRequest:
    return ProductionGoalRequest(
        request_id="production-1", goal_text=goal,
        capability_id="localai.ollama.qwen2_5_coder_14b",
    )


def test_real_local_capability_routes_and_enqueues_canonical_payload() -> None:
    def query(capability_id: str) -> CapabilityQueryResult:
        return CapabilityQueryResult(
            capability_id=capability_id, state=HonestState.PASS,
            reason="real local runtime configured",
        )

    sink = RecordingSink()
    result = ProductionFactory(AuthorityMap.load(REPO), query).submit_goal(
        _request(), sink
    )

    assert result.state is FactoryIntakeState.QUEUED
    assert result.durable_job_id == "production-1"
    assert sink.calls[0][1]["blueprint_id"] == result.blueprint_id
    assert sink.calls[0][1]["selected_tier"] == "local_model"


def test_unresolved_goal_never_reaches_routing_or_durable_sink() -> None:
    queried = False

    def query(capability_id: str) -> CapabilityQueryResult:
        nonlocal queried
        queried = True
        raise AssertionError(capability_id)

    sink = RecordingSink()
    result = ProductionFactory(AuthorityMap.load(REPO), query).submit_goal(
        _request("It should be fast."), sink
    )

    assert result.state is FactoryIntakeState.GOVERNED_STOP
    assert result.unresolved_count > 0
    assert not queried
    assert sink.calls == []


def test_absent_runtime_escalates_without_fabricating_a_job() -> None:
    sink = RecordingSink()
    result = ProductionFactory(AuthorityMap.load(REPO)).submit_goal(_request(), sink)

    assert result.state is FactoryIntakeState.ESCALATED
    assert result.selected_tier == "human_governance"
    assert result.durable_job_id is None
    assert sink.calls == []
