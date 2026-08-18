"""Read-only host/runtime probes never mutate, never assume (ARK-REQ-0129)."""

from __future__ import annotations

import platform

from arkali.engineering.localai.adapter import HonestState, RuntimeProbeResult
from arkali.engineering.localai.host_probe import (
    HostFacts,
    probe_accelerator,
    probe_host,
    probe_local_ai_runtime,
    probe_logical_cores,
    probe_total_ram_bytes,
)


class _FakeAdapter:
    """A composition-root double, not a production adapter."""

    def __init__(self, state: HonestState) -> None:
        self._state = state

    @property
    def runtime(self) -> str:
        return "fake"

    def probe(self) -> RuntimeProbeResult:
        return RuntimeProbeResult(runtime="fake", state=self._state, detail="test")

    def list_models(self) -> tuple:
        return ()

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0):
        raise NotImplementedError


class TestHostFactsAreReallyProbed:
    def test_logical_cores_is_positive_on_a_real_host(self) -> None:
        assert probe_logical_cores() > 0

    def test_total_ram_is_probed_on_windows(self) -> None:
        if platform.system() != "Windows":
            assert probe_total_ram_bytes() == 0
            return
        assert probe_total_ram_bytes() > 0

    def test_probe_host_returns_a_frozen_model(self) -> None:
        facts = probe_host()
        assert isinstance(facts, HostFacts)
        assert facts.os_name == platform.system()

    def test_accelerator_probe_never_raises(self) -> None:
        present, detail = probe_accelerator()
        assert isinstance(present, bool)
        assert detail


class TestRuntimeProbeIsGenuinelyAsked:
    def test_a_passing_adapter_makes_the_runtime_available(self) -> None:
        assert probe_local_ai_runtime(_FakeAdapter(HonestState.PASS)) is True

    def test_a_not_configured_adapter_makes_the_runtime_unavailable(self) -> None:
        assert probe_local_ai_runtime(_FakeAdapter(HonestState.NOT_CONFIGURED)) is False

    def test_an_external_unavailable_adapter_is_not_upgraded_to_available(self) -> None:
        assert probe_local_ai_runtime(
            _FakeAdapter(HonestState.EXTERNAL_UNAVAILABLE)
        ) is False


class TestProbesAreReadOnly:
    def test_no_probe_function_takes_a_mutating_verb_name(self) -> None:
        import arkali.engineering.localai.host_probe as module

        forbidden = ("install", "download", "write", "delete", "create", "enable")
        for name in dir(module):
            lowered = name.lower()
            assert not any(word in lowered for word in forbidden), name
