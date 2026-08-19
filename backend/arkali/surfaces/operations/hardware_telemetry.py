"""C-34 hardware/host telemetry: CPU/RAM/disk/network (MANDATORY, ARK-REQ-0168)
and GPU/VRAM (CONDITIONAL, ARK-REQ-0356).

Owner: `surfaces.operations`.

REUSES `engineering.localai.host_probe`, NEVER RE-PROBES CPU/RAM/GPU
PRESENCE. That module already owns real, read-only `probe_logical_cores`/
`probe_total_ram_bytes`/`probe_accelerator` for `ARK-REQ-0129`; a second,
independent CPU/RAM/GPU probe here would be exactly the F-0013 shadow-model
defect (two implementations of the same fact, free to drift). This module
composes those three and adds only the two dimensions that module has no
reason to own: disk free space and a local network-interface check, plus one
VRAM query layered on `host_probe`'s own accelerator-presence result.

NO OUTBOUND NETWORK CALL IS MADE. "network telemetry" here means real local
interface enumeration (is there at least one non-loopback interface with an
address), never a reachability probe to an external host - that would be a
`NETWORK_EXTERNAL` operation and require its own PDP decision, which a
telemetry read has no standing to make for itself.

EVERY PROBE IS READ-ONLY. Nothing here installs a driver, changes disk
contents or opens a socket to any remote peer.
"""

from __future__ import annotations

import shutil
import socket
import subprocess

from arkali.engineering.localai import host_probe
from arkali.surfaces.operations.contracts import DimensionReading, HardwareSnapshot

_NO_ACCELERATOR = "no accelerator detected (engineering.localai.host_probe.probe_accelerator)"


def _probe_disk_free_bytes(path: str) -> DimensionReading:
    try:
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return DimensionReading.not_configured("disk_free_bytes", f"disk probe failed: {exc}")
    return DimensionReading.real(
        "disk_free_bytes", float(usage.free),
        f"{usage.free} of {usage.total} bytes free on the volume containing {path!r}",
    )


def _probe_network_interface() -> DimensionReading:
    """A real, local, non-loopback interface address - never an outbound call."""
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(socket.gethostname(), None)
            if info[4][0] not in ("127.0.0.1", "::1")
        }
    except OSError as exc:
        return DimensionReading.not_configured(
            "network_reachable", f"local interface enumeration failed: {exc}"
        )
    if not addresses:
        return DimensionReading.not_configured(
            "network_reachable", "no non-loopback local interface address found"
        )
    return DimensionReading.real(
        "network_reachable", float(len(addresses)),
        f"{len(addresses)} local non-loopback interface address(es) present",
    )


def _probe_vram_total_bytes(accelerator_present: bool) -> DimensionReading:
    """VRAM total, queried only when `host_probe` already found an
    accelerator - layered on that result, never a second presence check."""
    if not accelerator_present:
        return DimensionReading.not_applicable("vram_total_bytes", _NO_ACCELERATOR)
    binary = shutil.which("nvidia-smi")
    if binary is None:
        return DimensionReading.not_configured(
            "vram_total_bytes", "accelerator detected but nvidia-smi is absent"
        )
    try:
        result = subprocess.run(
            [binary, "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5.0, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DimensionReading.not_configured("vram_total_bytes", f"vram probe failed: {exc}")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or not lines:
        return DimensionReading.not_configured(
            "vram_total_bytes", "nvidia-smi present but reported no memory total"
        )
    total_mib = sum(int(line) for line in lines if line.isdigit())
    return DimensionReading.real(
        "vram_total_bytes", float(total_mib) * 1024 * 1024,
        f"{total_mib} MiB total VRAM across {len(lines)} device(s)",
    )


def observe_hardware(workspace_path: str) -> HardwareSnapshot:
    """The real, live hardware dimensions, re-derived on every call."""
    facts = host_probe.probe_host()
    return HardwareSnapshot(
        cpu_logical_cores=DimensionReading.real(
            "cpu_logical_cores", float(facts.logical_cores),
            f"{facts.logical_cores} logical core(s) (engineering.localai.host_probe)",
        ),
        ram_total_bytes=(
            DimensionReading.real(
                "ram_total_bytes", float(facts.total_ram_bytes),
                f"{facts.total_ram_bytes} bytes total RAM (engineering.localai.host_probe)",
            )
            if facts.total_ram_bytes > 0
            else DimensionReading.not_configured(
                "ram_total_bytes",
                f"RAM probe is Windows-first and this host reports {facts.os_name!r} "
                "(engineering.localai.host_probe.probe_total_ram_bytes)",
            )
        ),
        disk_free_bytes=_probe_disk_free_bytes(workspace_path),
        network_reachable=_probe_network_interface(),
        gpu_present=DimensionReading.real(
            "gpu_present", 1.0 if facts.accelerator_present else 0.0, facts.accelerator_detail,
        ),
        vram_total_bytes=_probe_vram_total_bytes(facts.accelerator_present),
    )


__all__ = ["observe_hardware"]
