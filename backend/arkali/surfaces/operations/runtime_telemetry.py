"""C-34 runtime observability: jobs, workflows, providers, agents, workers
(ARK-REQ-0168).

Owner: `surfaces.operations`.

COMPOSES THE OWNING AUTHORITIES; STORES NOTHING OF ITS OWN. Job state comes
from the real `execution.durable.JobStore`/`JobRecovery` a caller already
holds - reused unmodified except for the one additive `list_by_state` read
Phase 25 added (mirroring `JobStore.get`'s own PEP-gated shape). Stuck-job
detection reuses `execution.durable.JobRecovery.heartbeat_stale` per running
job rather than re-deriving the staleness rule a second time (F-0036's own
lesson: a name and a rule drift apart the moment two places compute the same
fact).

WHY JOBS/WORKFLOWS ARE ALL STRUCTURAL `Protocol`s, NOT DIRECT IMPORTS. Two
real, measured `max_orchestration_depth` violations, found by running the
gate at different points: first `execution.workflow`'s own chain into
`kernel.contracts` (already 4 of 4) would have been extended to 5 by a
direct `WorkflowExecutor` import - the identical shape Phase 16's
`product_generation.py` and Phase 19's `pipeline.py` each answered with a
`Protocol`. Then Package 7 declared `surfaces.command -> surfaces.
operations`, and `execution.durable`'s own chain (`execution.durable ->
control.policy -> kernel.contracts`, already 3 of 4 on its own) became a
*second* path to 5 once wrapped by that new edge - so `JobStore`/
`JobRecovery` are Protocols too now, for the identical reason. A caller
still passes real instances; only the references at this call site are
structural.

WHY PROVIDERS/AGENTS/WORKERS ARE HONEST `NOT_CONFIGURED`. `control.registry.
provider` holds no live provider registry on this host (Phase 16/22's own
acceptance records: "no configured provider exists anywhere in this
repository", confirmed again directly here); no live agent runtime exists
(DEF-009); and `execution.scheduler.admission` itself resolves
`CAPABILITY_NOT_CONFIGURED` for every real submission (Phase 8's own honest
design). Reporting anything else for these three dimensions would be exactly
the fabricated telemetry ARK-REQ-0218/0355 forbid.
"""

from __future__ import annotations

from typing import Final, Protocol, Sequence

from arkali.surfaces.operations.contracts import DimensionReading, RuntimeSnapshot


class _JobLike(Protocol):
    job_id: str


class JobSource(Protocol):
    """Structural match for `execution.durable.JobStore.list_by_state`."""

    def list_by_state(self, states: tuple[str, ...]) -> Sequence[_JobLike]: ...


class HeartbeatSource(Protocol):
    """Structural match for `execution.durable.JobRecovery.heartbeat_stale`."""

    def heartbeat_stale(self, job_id: str) -> bool: ...


class WorkflowActivitySource(Protocol):
    """Structural match for `execution.workflow.WorkflowExecutor.list_by_state`.

    Only the shape this module needs - a count of executions per state - so no
    concrete `execution.workflow` type crosses this boundary, and the
    `max_orchestration_depth` chain through that context is never extended.
    """

    def list_by_state(self, states: tuple[str, ...]) -> Sequence[object]: ...


#: Non-terminal Job states (STATE_MACHINES.md §3): active work in progress.
_JOB_ACTIVE_STATES: Final[tuple[str, ...]] = (
    "RUNNING", "CHECKPOINTED", "PAUSED", "RESUMING", "RECOVERABLE", "FAILED",
)
#: The state a submitted-but-not-yet-running job sits in.
_JOB_QUEUED_STATES: Final[tuple[str, ...]] = ("QUEUED",)
#: Non-terminal WorkflowExecution states (STATE_MACHINES.md §4).
_WORKFLOW_ACTIVE_STATES: Final[tuple[str, ...]] = (
    "PENDING", "RUNNING", "WAITING_SIGNAL", "WAITING_APPROVAL", "COMPENSATING",
)

_NO_PROVIDER_REGISTRY = (
    "no provider is configured anywhere in this repository "
    "(control.registry.provider holds no live registry instance on this host)"
)
_NO_AGENT_RUNTIME = (
    "no live agent runtime exists (DEF-009: no orchestrator chains "
    "goal -> blueprint -> routing -> candidate -> product)"
)
_NO_WORKER_POOL = (
    "execution.scheduler.admission resolves CAPABILITY_NOT_CONFIGURED for "
    "every real submission; no live worker pool executes durable jobs "
    "(Phase 8's own designed, honestly-recorded absence)"
)


def observe_runtime(
    job_store: JobSource, job_recovery: HeartbeatSource, executor: WorkflowActivitySource,
) -> RuntimeSnapshot:
    """The real, live runtime dimensions, re-derived on every call."""
    active_jobs = job_store.list_by_state(_JOB_ACTIVE_STATES)
    queued_jobs = job_store.list_by_state(_JOB_QUEUED_STATES)
    running_jobs = job_store.list_by_state(("RUNNING",))
    stuck = tuple(j for j in running_jobs if job_recovery.heartbeat_stale(j.job_id))
    active_workflows = executor.list_by_state(_WORKFLOW_ACTIVE_STATES)

    return RuntimeSnapshot(
        jobs_active=DimensionReading.real(
            "jobs_active", float(len(active_jobs)),
            f"{len(active_jobs)} job(s) in a non-terminal state "
            f"({', '.join(_JOB_ACTIVE_STATES)})",
        ),
        jobs_queued=DimensionReading.real(
            "jobs_queued", float(len(queued_jobs)),
            f"{len(queued_jobs)} job(s) QUEUED, not yet started",
        ),
        jobs_stuck=DimensionReading.real(
            "jobs_stuck", float(len(stuck)),
            f"{len(stuck)} of {len(running_jobs)} RUNNING job(s) have a stale "
            "heartbeat (execution.durable.JobRecovery.heartbeat_stale)",
        ),
        workflows_active=DimensionReading.real(
            "workflows_active", float(len(active_workflows)),
            f"{len(active_workflows)} workflow execution(s) in a non-terminal "
            f"state ({', '.join(_WORKFLOW_ACTIVE_STATES)})",
        ),
        providers=DimensionReading.not_configured("providers", _NO_PROVIDER_REGISTRY),
        agents=DimensionReading.not_configured("agents", _NO_AGENT_RUNTIME),
        workers=DimensionReading.not_configured("workers", _NO_WORKER_POOL),
    )


__all__ = ["observe_runtime", "JobSource", "HeartbeatSource", "WorkflowActivitySource"]
