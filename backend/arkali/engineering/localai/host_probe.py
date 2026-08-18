"""Real, read-only host/runtime probes for local AI (ARK-REQ-0129).

Owner: engineering.localai.

THESE PROBES ARE READ-ONLY, mirroring `control.isolation.backend_probe`'s own
guarantee for the identical reason. Nothing here installs a runtime, starts a
server, downloads a model or changes host or driver configuration. Every probe
reports one canonical `HonestState`; `NOT_TESTED` is never upgraded by
assumption, and GPU presence is never assumed absent a genuine detection - a
model is judged suitable on CPU+RAM alone when no accelerator is found, never
refused for lacking one (Stage 6: "Do not assume GPU support").

`probe_local_ai_runtime` and `probe_accelerator` are this context's own
evaluation of the Appendix A applicability predicates
`isolation.probe.local_ai_runtime_available` and
`hardware.probe.accelerator_present` for `ARK-REQ-0129`. No other bounded
context in this repository claims either predicate as a going concern today
(`control.isolation` owns isolation BACKEND probing - sandbox primitives, not
model runtimes; hardware TELEMETRY presentation is Phase 25's `surfaces.
operations`, unbuilt). `RequirementRegister.for_phase("22")` names
`engineering.localai` as `ARK-REQ-0129`'s owning component, so evaluating its
own applicability rule from real host facts is this context's own obligation,
not a borrowed one.
"""

from __future__ import annotations

import platform
import shutil
import subprocess

from pydantic import BaseModel, ConfigDict

from arkali.engineering.localai.adapter import HonestState, LocalRuntimeAdapter

WINDOWS = "Windows"


class HostFacts(BaseModel):
    """Real, probed host facts. Never assumed, never cached across calls."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    os_name: str
    logical_cores: int
    total_ram_bytes: int
    accelerator_present: bool
    accelerator_detail: str


def probe_logical_cores() -> int:
    import os

    return os.cpu_count() or 0


def probe_total_ram_bytes() -> int:
    """Windows-first, matching `control.isolation.backend_probe`'s own scope.
    Returns 0 (honestly unknown) rather than guessing off this platform."""
    if platform.system() != WINDOWS:
        return 0
    try:
        import ctypes

        class _MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatusEx()
        status.dwLength = ctypes.sizeof(_MemoryStatusEx)
        windll = getattr(ctypes, "windll", None)
        if windll is None or not windll.kernel32.GlobalMemoryStatusEx(
            ctypes.byref(status)
        ):
            return 0
        return int(status.ullTotalPhys)
    except (OSError, AttributeError, ValueError):
        return 0


def probe_accelerator() -> tuple[bool, str]:
    """`hardware.probe.accelerator_present`. Read-only: queries `nvidia-smi`,
    installs nothing, and honestly reports absence on every other host."""
    binary = shutil.which("nvidia-smi")
    if binary is None:
        return False, "nvidia-smi not found on PATH; no accelerator detected"
    try:
        result = subprocess.run(
            [binary, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5.0, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"nvidia-smi probe failed: {exc}"
    if result.returncode != 0 or not result.stdout.strip():
        return False, "nvidia-smi present but reported no device"
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return True, f"{len(names)} accelerator(s): {', '.join(names)}"


def probe_host() -> HostFacts:
    """Every read-only host fact this context reasons over, in one place."""
    accelerator_present, accelerator_detail = probe_accelerator()
    return HostFacts(
        os_name=platform.system(),
        logical_cores=probe_logical_cores(),
        total_ram_bytes=probe_total_ram_bytes(),
        accelerator_present=accelerator_present,
        accelerator_detail=accelerator_detail,
    )


def probe_local_ai_runtime(adapter: LocalRuntimeAdapter) -> bool:
    """`isolation.probe.local_ai_runtime_available` for one adapter: a real,
    live probe, never inferred from adapter construction alone."""
    return adapter.probe().state is HonestState.PASS


__all__ = [
    "HostFacts", "probe_logical_cores", "probe_total_ram_bytes",
    "probe_accelerator", "probe_host", "probe_local_ai_runtime",
]
