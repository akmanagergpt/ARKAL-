"""The C-34 Operations HTTP surface (ARK-REQ-0168, 0169, 0170, 0355-0357).

Owner: `surfaces.command`. Composes `surfaces.operations` unmodified via the
declared `surfaces.command -> surfaces.operations` sibling edge
(`AUTHORITY_MAP.yaml`, Phase 25) - the identical layering `jobs.py`/
`workflow.py` already use for their own owning contexts.

READ-ONLY BY DESIGN. This surface exposes telemetry (`GET /operations/
snapshot`, `/conditional`) and Computer-Use *authorization decisions*
(`POST /operations/computer-use/authorize`) - never raw execution. A
network-reachable endpoint that ran an arbitrary caller-supplied process
would be an unreviewed remote-execution surface regardless of how tightly
the PDP gates the operation *class*; the PDP has no opinion on a command's
*content*. `process_boundary.py`/`file_boundary.py`/`browser_boundary.py`
remain library capabilities for a future, human-supervised orchestration
surface - not exposed here. Deliberate scope boundary, not an oversight.

EVERY COLLABORATOR IN `wiring` IS SUPPLIED, NOT BUILT HERE - the identical
`ExecutorFactory` shape `workflow.py` already established, generalised to
two real, measured constraints found by running the gate:
  (1) this module would otherwise need its own `PolicyEnforcementPoint`
      construction - `max_fan_in_per_module` on `control.policy.pep`/
      `.policy_contract` (both already 15 of 15 counting `app.py`/
      `jobs.py`'s own imports) - the identical constraint Packages 2 and 5
      already answered the same way;
  (2) a direct `engineering.localai.host_probe` import here, alongside the
      three contexts this module already reaches
      (`surfaces.operations`/`control.policy`/`execution.durable`), would
      have breached `max_contexts_touched_by_module` (3) - so `probe_host`
      is supplied too, real and unmodified, from the composition root
      (`scripts/run_command_center.py`, outside the measured graph).
`guard` (already bound to the real PEP by `app.py`) is reused as the
aggregate view's own authorization, exactly as `telemetry.
ReadAuthorization` requires, with no new PDP/PEP import here either.

BACKEND_ONLY. No Phase 25 requirement is owned by any `surfaces.*` context
(all eight are owned by `surfaces.operations`, `control.policy` or
`acceptance.engine`, none with `e2e` evidence), so no frontend obligation
exists and none is invented here - the identical reasoning `jobs.py`
already recorded for `ARK-REQ-0027`.
"""

from __future__ import annotations

import pathlib
from collections.abc import Callable, Iterator

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.execution.durable.recovery import JobRecovery
from arkali.surfaces.command.contracts import BACKEND_ONLY
from arkali.surfaces.operations.ai_review_bundle import ArchitectureSummary, observe_architecture
from arkali.surfaces.operations.computer_use import authorize_computer_use_action
from arkali.surfaces.operations.computer_use_contracts import ComputerUseDecision
from arkali.surfaces.operations.conditional_dimensions import (
    HardwareCostDimensions,
    QualityLatencyDimensions,
    observe_hardware_cost_dimensions,
    observe_quality_latency_dimensions,
)
from arkali.surfaces.operations.contracts import OperationsSnapshot
from arkali.surfaces.operations.hardware_telemetry import HostFactsSource, observe_hardware
from arkali.surfaces.operations.runtime_telemetry import WorkflowActivitySource
from arkali.surfaces.operations.telemetry import ReadAuthorization, observe_operations

SessionScope = Callable[[], Iterator[Session]]
Guard = Callable[[str], None]
Refuse = Callable[[Exception], Exception]

#: `execution.durable.recovery` has ample fan-in headroom (unlike
#: `control.policy.pep`/`.policy_contract`), so `JobRecovery` is imported
#: directly for this factory's type - only the PEP construction itself is
#: kept out of this module (see the module docstring).
JobRecoveryFactory = Callable[[Session], JobRecovery]
ExecutorFactory = Callable[[Session], WorkflowActivitySource]
#: `(job_recovery_factory, executor_factory, pdp, probe_host)`.
Wiring = tuple[JobRecoveryFactory, ExecutorFactory, PolicyDecisionPoint, HostFactsSource]


class _ComputerUseAuthorizeRequest(BaseModel):
    """The wire shape for a Computer-Use authorization request. Never
    carries a command to execute - only the facts the PDP is allowed to
    consider, mirroring `PolicyRequest`'s own tri-state discipline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation_class: str
    trust_tier: str = "TRUST-1"
    local_only: bool = False


class _GuardReadAuthorization(ReadAuthorization):
    """`telemetry.ReadAuthorization`, backed by `app.py`'s own already-real
    `guard` closure - no new PDP/PEP import needed here."""

    def __init__(self, guard: Guard) -> None:
        self._guard = guard

    def require_auto(self, *, actor: str) -> None:
        del actor  # `guard` already carries this surface's own real actor.
        self._guard("READ_FILE")


def _build_operations_router(
    session_scope: SessionScope,
    guard: Guard,
    refuse: Refuse,
    engine: Engine,
    repo_root: pathlib.Path,
    wiring: Wiring,
) -> APIRouter:
    """The Operations telemetry + Computer-Use authorization routes."""
    job_recovery_factory, executor_factory, pdp, probe_host = wiring
    router = APIRouter(prefix="/api/operations", tags=[BACKEND_ONLY])
    read_authorization = _GuardReadAuthorization(guard)

    @router.get("/snapshot", response_model=OperationsSnapshot)
    def snapshot(session: Session = Depends(session_scope)) -> OperationsSnapshot:
        guard("READ_FILE")
        recovery: JobRecovery = job_recovery_factory(session)
        executor = executor_factory(session)
        try:
            return observe_operations(
                pep=read_authorization,
                durable=(recovery.execution.jobs, recovery, executor),
                engine=engine, workspace_path=str(repo_root), probe_host=probe_host,
            )
        except Exception as error:
            raise refuse(error) from error

    @router.get("/conditional/hardware-cost", response_model=HardwareCostDimensions)
    def conditional_hardware_cost() -> HardwareCostDimensions:
        guard("READ_FILE")
        return observe_hardware_cost_dimensions(
            observe_hardware(str(repo_root), probe_host)
        )

    @router.get("/conditional/quality-latency", response_model=QualityLatencyDimensions)
    def conditional_quality_latency() -> QualityLatencyDimensions:
        guard("READ_FILE")
        return observe_quality_latency_dimensions()

    @router.get("/architecture", response_model=ArchitectureSummary)
    def architecture() -> ArchitectureSummary:
        guard("READ_FILE")
        return observe_architecture(repo_root)

    @router.post("/computer-use/authorize", response_model=ComputerUseDecision)
    def authorize(body: _ComputerUseAuthorizeRequest) -> ComputerUseDecision:
        """The real PDP's decision only - never executes anything."""
        guard("READ_FILE")
        return authorize_computer_use_action(
            pdp, operation_class=body.operation_class, trust_tier=body.trust_tier,
            local_only=body.local_only,
        )

    return router


__all__ = [
    "_build_operations_router", "_ComputerUseAuthorizeRequest",
    "JobRecoveryFactory", "ExecutorFactory", "Wiring",
]
