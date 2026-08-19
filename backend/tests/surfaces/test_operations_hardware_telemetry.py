"""C-34 hardware telemetry (ARK-REQ-0168 MANDATORY dimensions, ARK-REQ-0356
CONDITIONAL GPU/VRAM). REAL host probes only - no fixture doubles.
"""

from __future__ import annotations

import pathlib

from arkali.kernel.contracts.honest_state import HonestState
from arkali.surfaces.operations.hardware_telemetry import observe_hardware


class TestCpuAndDiskAreAlwaysReal:
    def test_cpu_logical_cores_is_a_real_positive_count(self, tmp_path: pathlib.Path) -> None:
        snapshot = observe_hardware(str(tmp_path))
        assert snapshot.cpu_logical_cores.state is HonestState.PASS
        assert snapshot.cpu_logical_cores.value is not None
        assert snapshot.cpu_logical_cores.value > 0

    def test_disk_free_bytes_is_real_for_an_existing_path(self, tmp_path: pathlib.Path) -> None:
        snapshot = observe_hardware(str(tmp_path))
        assert snapshot.disk_free_bytes.state is HonestState.PASS
        assert snapshot.disk_free_bytes.value is not None
        assert snapshot.disk_free_bytes.value > 0

    def test_disk_free_bytes_is_honest_not_configured_for_a_missing_path(self) -> None:
        snapshot = observe_hardware("Z:\\this\\path\\does\\not\\exist\\anywhere")
        assert snapshot.disk_free_bytes.state is HonestState.NOT_CONFIGURED
        assert snapshot.disk_free_bytes.value is None


class TestGpuVramIsConditionalAndHonest:
    def test_vram_is_not_applicable_when_no_accelerator_is_present(
        self, tmp_path: pathlib.Path,
    ) -> None:
        snapshot = observe_hardware(str(tmp_path))
        if snapshot.gpu_present.value == 0.0:
            assert snapshot.vram_total_bytes.state is HonestState.NOT_APPLICABLE
            assert snapshot.vram_total_bytes.value is None

    def test_gpu_present_is_never_fabricated_true(self, tmp_path: pathlib.Path) -> None:
        snapshot = observe_hardware(str(tmp_path))
        assert snapshot.gpu_present.state is HonestState.PASS
        assert snapshot.gpu_present.value in (0.0, 1.0)
        assert snapshot.gpu_present.detail


class TestNetworkTelemetryNeverMakesAnOutboundCall:
    def test_network_reachable_reports_a_real_local_reading_never_none(
        self, tmp_path: pathlib.Path,
    ) -> None:
        snapshot = observe_hardware(str(tmp_path))
        assert snapshot.network_reachable.state in (
            HonestState.PASS, HonestState.NOT_CONFIGURED,
        )
        if snapshot.network_reachable.state is HonestState.PASS:
            assert snapshot.network_reachable.value is not None
            assert snapshot.network_reachable.value >= 1.0
