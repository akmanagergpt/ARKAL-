"""Hardware-aware suitability, never assuming GPU support (ARK-REQ-0129)."""

from __future__ import annotations

from arkali.engineering.localai.adapter import HonestState, LocalModelDescriptor
from arkali.engineering.localai.host_probe import HostFacts
from arkali.engineering.localai.suitability import (
    estimate_memory_bytes,
    evaluate_suitability,
)

AMPLE_HOST = HostFacts(
    os_name="Windows", logical_cores=8, total_ram_bytes=32 * 1024**3,
    accelerator_present=False, accelerator_detail="none",
)
TIGHT_HOST = HostFacts(
    os_name="Windows", logical_cores=4, total_ram_bytes=4 * 1024**3,
    accelerator_present=True, accelerator_detail="RTX",
)
UNPROBED_HOST = HostFacts(
    os_name="Linux", logical_cores=4, total_ram_bytes=0,
    accelerator_present=False, accelerator_detail="not windows",
)


def descriptor(
    parameter_size: str = "7.6B", quantization: str = "Q4_K_M"
) -> LocalModelDescriptor:
    return LocalModelDescriptor(
        runtime="ollama", model_id="qwen2.5-coder:7b",
        parameter_size=parameter_size, quantization=quantization,
        context_length=32768,
    )


class TestEstimation:
    def test_a_known_quantization_yields_a_positive_estimate(self) -> None:
        estimate = estimate_memory_bytes(descriptor())
        assert estimate is not None
        assert estimate > 0

    def test_an_unknown_quantization_is_not_estimated(self) -> None:
        assert estimate_memory_bytes(descriptor(quantization="MYSTERY")) is None

    def test_an_unparseable_parameter_size_is_not_estimated(self) -> None:
        assert estimate_memory_bytes(descriptor(parameter_size="huge")) is None


class TestSuitabilityNeverAssumesGpu:
    def test_a_small_model_fits_an_ample_host_without_any_accelerator(self) -> None:
        verdict = evaluate_suitability(descriptor(), AMPLE_HOST)
        assert verdict.state is HonestState.PASS
        assert "CPU" in verdict.reason

    def test_the_verdict_is_identical_whether_or_not_an_accelerator_is_present(
        self,
    ) -> None:
        with_gpu = AMPLE_HOST.model_copy(update={"accelerator_present": True})
        without_gpu = AMPLE_HOST.model_copy(update={"accelerator_present": False})
        assert (
            evaluate_suitability(descriptor(), with_gpu).state
            == evaluate_suitability(descriptor(), without_gpu).state
        )

    def test_a_large_model_does_not_fit_a_tight_host(self) -> None:
        verdict = evaluate_suitability(descriptor(parameter_size="70B"), TIGHT_HOST)
        assert verdict.state is HonestState.NOT_CONFIGURED

    def test_an_unknown_quantization_is_honestly_not_tested(self) -> None:
        verdict = evaluate_suitability(descriptor(quantization="?"), AMPLE_HOST)
        assert verdict.state is HonestState.NOT_TESTED

    def test_an_unprobed_host_ram_is_honestly_not_tested(self) -> None:
        verdict = evaluate_suitability(descriptor(), UNPROBED_HOST)
        assert verdict.state is HonestState.NOT_TESTED

    def test_estimated_memory_is_carried_on_the_verdict(self) -> None:
        verdict = evaluate_suitability(descriptor(), AMPLE_HOST)
        assert verdict.estimated_memory_bytes is not None
        assert verdict.estimated_memory_bytes > 0
