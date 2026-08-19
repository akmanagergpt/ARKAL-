"""C-34 Operations telemetry value objects (ARK-REQ-0168, 0355, 0356, 0395).

Owner: `surfaces.operations`.

ONE READING SHAPE FOR EVERY DIMENSION. `DimensionReading` carries the same
`HonestState` taxonomy every other verification surface in this repository
already uses (`kernel.contracts.honest_state`) - never a second verdict
vocabulary invented for telemetry. A dimension whose owning authority is
absent, unconfigured or not yet built on this host reports `NOT_CONFIGURED`
with an honest `detail` explaining why, exactly as `execution_routing.py`
(Phase 16) and `CapabilityGraph.can_perform` (Phase 3/9B) already resolve an
unactivated capability - never a fabricated value (ARK-REQ-0218, ARK-REQ-355:
no invented telemetry).

NOTHING IS CACHED. `OperationsSnapshot` is a frozen value returned by one call
into the live authorities it composes; a second call re-derives it from
scratch. Holding an old snapshot and re-reading its fields is a caller error,
not a live read - the same discipline `HostFacts`/`CapabilityGraph.can_perform`
already established.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.honest_state import HonestState


class DimensionReading(BaseModel):
    """One observed operations dimension: its state and, when real, a value.

    `value` is populated only when `state` is `PASS` - a `NOT_CONFIGURED`
    reading never carries a number, so a caller cannot mistake "no data" for
    a real zero.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    dimension: str
    state: HonestState
    detail: str
    value: float | None = None

    @classmethod
    def real(cls, dimension: str, value: float, detail: str) -> DimensionReading:
        return cls(dimension=dimension, state=HonestState.PASS, value=value, detail=detail)

    @classmethod
    def not_configured(cls, dimension: str, detail: str) -> DimensionReading:
        return cls(dimension=dimension, state=HonestState.NOT_CONFIGURED, detail=detail)

    @classmethod
    def not_applicable(cls, dimension: str, detail: str) -> DimensionReading:
        return cls(dimension=dimension, state=HonestState.NOT_APPLICABLE, detail=detail)


class RuntimeSnapshot(BaseModel):
    """The MANDATORY (ARK-REQ-0168) real-time dimensions this context owns."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    jobs_active: DimensionReading
    jobs_queued: DimensionReading
    jobs_stuck: DimensionReading
    workflows_active: DimensionReading
    providers: DimensionReading
    agents: DimensionReading
    workers: DimensionReading


class HardwareSnapshot(BaseModel):
    """CPU/RAM (MANDATORY) plus GPU/VRAM (CONDITIONAL, ARK-REQ-0356)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cpu_logical_cores: DimensionReading
    ram_total_bytes: DimensionReading
    disk_free_bytes: DimensionReading
    network_reachable: DimensionReading
    gpu_present: DimensionReading
    vram_total_bytes: DimensionReading


class StorageSnapshot(BaseModel):
    """Durable-store facts (MANDATORY, part of ARK-REQ-0168's "DB/storage")."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    database_reachable: DimensionReading
    database_size_bytes: DimensionReading


class OperationsSnapshot(BaseModel):
    """The composed real-time view this context presents (ARK-REQ-0168)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runtime: RuntimeSnapshot
    hardware: HardwareSnapshot
    storage: StorageSnapshot


__all__ = [
    "DimensionReading", "RuntimeSnapshot", "HardwareSnapshot",
    "StorageSnapshot", "OperationsSnapshot",
]
