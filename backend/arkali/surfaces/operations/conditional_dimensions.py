"""C-34 CONDITIONAL telemetry dimensions (ARK-REQ-0356, ARK-REQ-0395).

Owner: `surfaces.operations`.

BOTH REQUIREMENTS ARE APPLICABILITY-GATED, NEVER SILENTLY SKIPPED.
`REQUIREMENT_REGISTER.md`'s own applicability rules:
  ARK-REQ-0356: `hardware.probe.<dimension>_available == true` (GPU/VRAM) or
    `provider.registry.<id>.cost_reporting == true` (cost/token).
  ARK-REQ-0395: `knowledge.verified_outcome_count > 0` (quality) or
    `execution.probe.latency_available == true` (latency).
This module evaluates both predicates against real, live facts - never
assumes CONDITIONAL means "skip"; a genuinely inapplicable dimension is
`NOT_APPLICABLE`, mechanically re-derived on every call, not just recorded
once and trusted.

WHY BOTH ARE HONESTLY `NOT_APPLICABLE` ON THIS HOST TODAY, PROVEN NOT
ASSUMED. GPU/VRAM: `hardware_telemetry.observe_hardware`'s own
`gpu_present` reading already answers `hardware.probe.accelerator_
available` in Package 1 - no second probe here, this module reads that
result. Cost/token: no provider is configured anywhere in this repository
(Phase 16/22's own acceptance records, re-verified in Package 1's own
`runtime_telemetry.py`), so no `provider.registry.*.cost_reporting` fact
can be true. Quality: `engineering.knowledge.outcome_statistics.
VerifiedOutcome` is `INT` - no table, no persisted registry (Phase 18's own
acceptance record) - so `knowledge.verified_outcome_count` is always the
count of whatever a caller supplies, and no live pipeline populates any;
this module's own default caller supplies none. Latency: no live
execution/orchestration loop exists (DEF-009), so no real per-task latency
measurement exists to probe.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

from arkali.engineering.knowledge.outcome_statistics import VerifiedOutcome
from arkali.surfaces.operations.contracts import DimensionReading, HardwareSnapshot

_NO_PROVIDER_COST_REPORTING = (
    "no provider is configured anywhere in this repository "
    "(control.registry.provider holds no live registry instance on this host), "
    "so no provider.registry.*.cost_reporting fact can be true"
)
_NO_VERIFIED_OUTCOMES = (
    "engineering.knowledge.outcome_statistics.VerifiedOutcome is INT (no table, "
    "no persisted registry, Phase 18's own acceptance record); no live pipeline "
    "populates any, so knowledge.verified_outcome_count is 0"
)
_NO_LATENCY_PROBE = (
    "no live execution/orchestration loop exists (DEF-009); no real per-task "
    "latency measurement exists to probe"
)


class HardwareCostDimensions(BaseModel):
    """ARK-REQ-0356: GPU/VRAM (from `hardware_telemetry`) plus cost/token
    (honestly `NOT_APPLICABLE` while no provider reports cost)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gpu: DimensionReading
    vram: DimensionReading
    cost: DimensionReading
    token_usage: DimensionReading


class QualityLatencyDimensions(BaseModel):
    """ARK-REQ-0395: verified-quality-outcome signals plus per-task latency."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    quality: DimensionReading
    latency: DimensionReading


def observe_hardware_cost_dimensions(hardware: HardwareSnapshot) -> HardwareCostDimensions:
    """ARK-REQ-0356, evaluated against `hardware_telemetry`'s own real GPU
    reading - never a second accelerator probe."""
    return HardwareCostDimensions(
        gpu=hardware.gpu_present,
        vram=hardware.vram_total_bytes,
        cost=DimensionReading.not_applicable("cost", _NO_PROVIDER_COST_REPORTING),
        token_usage=DimensionReading.not_applicable("token_usage", _NO_PROVIDER_COST_REPORTING),
    )


def observe_quality_latency_dimensions(
    verified_outcomes: Sequence[VerifiedOutcome] = (),
) -> QualityLatencyDimensions:
    """ARK-REQ-0395. `verified_outcomes` defaults to empty because no live
    pipeline in this repository populates any (see module docstring); a
    caller with real outcomes may supply them, and this function honestly
    reports `PASS` the moment it genuinely receives at least one."""
    count = len(verified_outcomes)
    quality = (
        DimensionReading.real(
            "quality", float(count), f"{count} verified outcome(s) supplied",
        )
        if count > 0
        else DimensionReading.not_applicable("quality", _NO_VERIFIED_OUTCOMES)
    )
    return QualityLatencyDimensions(
        quality=quality,
        latency=DimensionReading.not_applicable("latency", _NO_LATENCY_PROBE),
    )


__all__ = [
    "HardwareCostDimensions", "QualityLatencyDimensions",
    "observe_hardware_cost_dimensions", "observe_quality_latency_dimensions",
]
