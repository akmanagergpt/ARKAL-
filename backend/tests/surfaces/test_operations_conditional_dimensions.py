"""C-34 CONDITIONAL dimensions (ARK-REQ-0356, ARK-REQ-0395): real
applicability evaluation, never silently skipped.
"""

from __future__ import annotations

import pathlib

from arkali.engineering.knowledge.contracts import EvidenceKind, EvidenceReference
from arkali.engineering.knowledge.outcome_statistics import VerifiedOutcome
from arkali.engineering.localai import host_probe
from arkali.kernel.contracts.content_address import address_of
from arkali.kernel.contracts.honest_state import HonestState
from arkali.surfaces.operations.conditional_dimensions import (
    observe_hardware_cost_dimensions,
    observe_quality_latency_dimensions,
)
from arkali.surfaces.operations.hardware_telemetry import observe_hardware


def _observe(path: str):  # noqa: ANN201
    return observe_hardware(path, host_probe.probe_host)


class TestHardwareCostDimensionsArk0356:
    def test_gpu_and_vram_reflect_the_real_hardware_reading(
        self, tmp_path: pathlib.Path,
    ) -> None:
        hardware = _observe(str(tmp_path))
        dims = observe_hardware_cost_dimensions(hardware)
        assert dims.gpu == hardware.gpu_present
        assert dims.vram == hardware.vram_total_bytes

    def test_cost_and_token_usage_are_honestly_not_applicable_with_no_provider(
        self, tmp_path: pathlib.Path,
    ) -> None:
        hardware = _observe(str(tmp_path))
        dims = observe_hardware_cost_dimensions(hardware)
        assert dims.cost.state is HonestState.NOT_APPLICABLE
        assert dims.token_usage.state is HonestState.NOT_APPLICABLE
        assert dims.cost.value is None


class TestQualityLatencyDimensionsArk0395:
    def test_quality_is_not_applicable_with_no_verified_outcomes_supplied(self) -> None:
        dims = observe_quality_latency_dimensions()
        assert dims.quality.state is HonestState.NOT_APPLICABLE

    def test_quality_becomes_real_the_moment_a_real_outcome_is_supplied(self) -> None:
        evidence = EvidenceReference(
            kind=EvidenceKind.ACCEPTANCE_RESULT, content_address=address_of(b"outcome-fixture"),
        )
        outcome = VerifiedOutcome(
            model_id="test-model", task_class="unit-test", succeeded=True, evidence=evidence,
        )
        dims = observe_quality_latency_dimensions([outcome])
        assert dims.quality.state is HonestState.PASS
        assert dims.quality.value == 1.0

    def test_latency_is_honestly_not_applicable_with_no_live_execution_loop(self) -> None:
        dims = observe_quality_latency_dimensions()
        assert dims.latency.state is HonestState.NOT_APPLICABLE
