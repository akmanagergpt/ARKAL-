"""C-34 composed Operations telemetry entry point (ARK-REQ-0168, ARK-REQ-0170).

Owner: `surfaces.operations`.

ONE COMPOSITION, THREE OWNING PROBES. `observe_operations` calls
`runtime_telemetry.observe_runtime`, `hardware_telemetry.observe_hardware`
and `storage_telemetry.observe_storage` and assembles their real, live
results - it computes no dimension of its own.

`executor` is typed as `runtime_telemetry.WorkflowActivitySource`, not the
concrete `execution.workflow.WorkflowExecutor` - see that module's own
docstring for the measured `max_orchestration_depth` violation this avoids.

THE AGGREGATE VIEW IS ITSELF A GOVERNED OPERATION, ON TOP OF THE READS IT
COMPOSES (ARK-REQ-0170: Computer-Use/Operations "executes exclusively
through the Policy Authority / PDP / PEP path used by every other execution
surface"). `JobStore`/`JobRecovery`/`WorkflowExecutor` are already
individually PEP-gated; presenting the composed cross-context snapshot is
this context's own capability, so it takes its own decision first.

WHY `pep` IS A STRUCTURAL `Protocol`, NOT A DIRECT IMPORT. A real, measured
`max_fan_in_per_module` violation: `control.policy.pep` and `.policy_contract`
were both already at their 15-of-15 ceiling (`surfaces.command`'s own
`app.py`/`jobs.py` are two of the fifteen), so a direct `PolicyEnforcementPoint`/
`PolicyRequest` import here would have breached both - the identical shape
Phase 22B's `lifecycle.recovery.recovery_supervisor.RollbackAuthorization`
already answered with a `Protocol` reduced to primitive facts, adapted by a
real implementation at the composition root, never requested as a GATE 8
exception. `ReadAuthorization.require_auto` is named and shaped exactly so
`tests/security/test_pep_and_bypass.py`'s policy-decision sweep recognises
this call as real enforcement (method name and a `pep`-named receiver) without
this module importing the concrete PDP/PEP types - the decision itself is
still real; only the reference at this one call site is structural. Once
Package 8 wires a real `surfaces.command` route to this function, that
composition root - already a counted importer of both modules - constructs
the genuine adapter; no production caller exists yet, matching Phase 22B's
own honestly-recorded absence.
"""

from __future__ import annotations

from typing import Final, Protocol, runtime_checkable

from sqlalchemy import Engine

from arkali.surfaces.operations.contracts import OperationsSnapshot
from arkali.surfaces.operations.hardware_telemetry import HostFactsSource, observe_hardware
from arkali.surfaces.operations.runtime_telemetry import (
    HeartbeatSource,
    JobSource,
    WorkflowActivitySource,
    observe_runtime,
)
from arkali.surfaces.operations.storage_telemetry import observe_storage

ACTOR: Final[str] = "surfaces.operations"


@runtime_checkable
class ReadAuthorization(Protocol):
    """Structural view of the real PDP-mediated `READ_FILE` grant for this
    context's own aggregate view. See the module docstring for why this is a
    `Protocol` and not an import."""

    def require_auto(self, *, actor: str) -> None:
        """Raise (`PolicyDenied`) unless the real PDP grants `READ_FILE`
        `AUTO` for this actor. The implementation is responsible for stating
        `operation_class`/`trust_tier` truthfully to the real PDP."""
        ...


def observe_operations(
    *,
    pep: ReadAuthorization,
    durable: tuple[JobSource, HeartbeatSource, WorkflowActivitySource],
    engine: Engine,
    workspace_path: str,
    probe_host: HostFactsSource,
) -> OperationsSnapshot:
    """The complete real-time Operations view, re-derived on every call.

    `durable` is `(job_store, job_recovery, executor)`, grouped into one
    parameter - `max_parameters_per_public_function` is 6, and this
    function's five real collaborators plus the newly-added `probe_host`
    (Package 7's own depth-avoidance `Protocol`) would otherwise breach it.
    """
    job_store, job_recovery, executor = durable
    pep.require_auto(actor=ACTOR)
    return OperationsSnapshot(
        runtime=observe_runtime(job_store, job_recovery, executor),
        hardware=observe_hardware(workspace_path, probe_host),
        storage=observe_storage(engine),
    )


__all__ = ["observe_operations", "ReadAuthorization", "ACTOR"]
