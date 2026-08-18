"""Hardware-aware model suitability (ARK-REQ-0129: "hardware-aware... local AI").

Owner: engineering.localai.

CPU-ONLY IS ALWAYS A VALID ANSWER. A model is judged suitable when the host's
RAM can plausibly hold it; an accelerator narrows nothing here and is never
required (Stage 6: "Do not assume GPU support" - the suitability verdict is
identical whether or not `HostFacts.accelerator_present` is true, and no field
below reads it). Advertising accelerator presence is `host_probe.py`'s job;
using it to route or accelerate inference is a future capability's concern out
of this phase's denominator.

A CONSERVATIVE, DECLARED ESTIMATE, NEVER A MEASUREMENT CLAIM. `quantization`
determines an approximate bytes-per-parameter figure; a model whose
quantization is not in the known table is honestly `NOT_TESTED` rather than
guessed at zero cost. Real memory headroom (60% of total RAM, so the host OS
and every other process are not starved) is required, not merely "less than
total" - this is a suitability *decision*, not a bare capacity comparison.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arkali.engineering.localai.adapter import HonestState, LocalModelDescriptor
from arkali.engineering.localai.host_probe import HostFacts

#: Conservative bytes-per-parameter by GGUF quantization level. Deliberately a
#: closed, declared table: an unknown quantization is `NOT_TESTED`, never
#: defaulted to the cheapest or most expensive entry.
_BYTES_PER_PARAM_BY_QUANTIZATION: dict[str, float] = {
    "Q4_K_M": 0.6, "Q4_0": 0.55, "Q5_K_M": 0.7, "Q5_0": 0.65,
    "Q8_0": 1.05, "F16": 2.0, "F32": 4.0,
}

#: Fraction of total RAM a model may occupy without starving the host.
_MAX_RAM_FRACTION = 0.6


class SuitabilityVerdict(BaseModel):
    """Deterministic, hardware-aware answer for one model on one host."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_id: str
    state: HonestState
    reason: str
    estimated_memory_bytes: int | None = None


def _parameter_count(parameter_size: str) -> float | None:
    """`"7.6B"` -> `7_600_000_000.0`. Returns None for an unparseable size."""
    text = parameter_size.strip().upper()
    if not text.endswith("B") or len(text) < 2:
        return None
    try:
        return float(text[:-1]) * 1_000_000_000
    except ValueError:
        return None


def estimate_memory_bytes(descriptor: LocalModelDescriptor) -> int | None:
    """Conservative estimated resident memory, or None if not estimable."""
    params = _parameter_count(descriptor.parameter_size)
    per_param = _BYTES_PER_PARAM_BY_QUANTIZATION.get(descriptor.quantization)
    if params is None or per_param is None:
        return None
    return int(params * per_param)


def evaluate_suitability(
    descriptor: LocalModelDescriptor, host: HostFacts
) -> SuitabilityVerdict:
    """Whether `descriptor` fits this real host's RAM, conservatively.

    `PASS` is earned: it requires a real estimate that fits within
    `_MAX_RAM_FRACTION` of the host's probed total RAM. Every other outcome is
    a determinate non-PASS state, never assumed either way.
    """
    estimated = estimate_memory_bytes(descriptor)
    if estimated is None:
        return SuitabilityVerdict(
            model_id=descriptor.model_id, state=HonestState.NOT_TESTED,
            reason=(
                f"parameter_size={descriptor.parameter_size!r} or "
                f"quantization={descriptor.quantization!r} is not in the known "
                "estimation table; suitability is not guessed"
            ),
        )
    if host.total_ram_bytes <= 0:
        return SuitabilityVerdict(
            model_id=descriptor.model_id, state=HonestState.NOT_TESTED,
            reason="host total RAM was not probed on this platform",
            estimated_memory_bytes=estimated,
        )
    budget = int(host.total_ram_bytes * _MAX_RAM_FRACTION)
    if estimated <= budget:
        return SuitabilityVerdict(
            model_id=descriptor.model_id, state=HonestState.PASS,
            reason=(
                f"estimated {estimated} bytes fits within {budget} bytes "
                f"({_MAX_RAM_FRACTION:.0%} of {host.total_ram_bytes} bytes total "
                "RAM); CPU inference alone is sufficient for suitability"
            ),
            estimated_memory_bytes=estimated,
        )
    return SuitabilityVerdict(
        model_id=descriptor.model_id, state=HonestState.NOT_CONFIGURED,
        reason=(
            f"estimated {estimated} bytes exceeds {budget} bytes "
            f"({_MAX_RAM_FRACTION:.0%} of {host.total_ram_bytes} bytes total RAM)"
        ),
        estimated_memory_bytes=estimated,
    )


__all__ = ["SuitabilityVerdict", "estimate_memory_bytes", "evaluate_suitability"]
