"""Real host probes for isolation backend availability (ARK-REQ-0123).

Owner: control.isolation (Protected Core).

THESE PROBES ARE READ-ONLY. Nothing here installs a Windows feature, elevates,
enables Hyper-V, changes system configuration or creates a sandbox. A probe that
changed the host to make itself pass would be the purest form of the
false-success defect the canonical set forbids.

A PYTHON CLASS IS NOT ISOLATION. Existence of an adapter proves nothing about the
host. Every probe reports one canonical `HonestState`:

  PASS                  the OS primitive is present and reachable from here
  NOT_CONFIGURED        the primitive exists on the platform but is not enabled,
                        or requires privileges this process does not hold
  UNSUPPORTED           the platform cannot provide it at all
  EXTERNAL_UNAVAILABLE  the probe itself could not run

`NOT_TESTED` is the default and is never upgraded by assumption. None of these
states is ever converted to PASS, and a non-PASS backend contributes no
properties to a composition.

Probe results describe *availability*, not enforcement. A PASS here means the
primitive can be obtained; it does not by itself constitute evidence that a
workload was actually confined. That evidence belongs to `execution.sandbox`,
whose implementation is a later phase.
"""

from __future__ import annotations

import ctypes
import os
import pathlib
import platform
from collections.abc import Callable
from typing import Any

from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
)
from arkali.kernel.contracts.results import HonestState

WINDOWS = "Windows"


def _windows_only() -> HonestState:
    """Probes below are Windows-first; elsewhere they are honestly UNSUPPORTED."""
    return HonestState.UNSUPPORTED


def _load(name: str) -> Any:
    """Load a system DLL, or None. Never raises into a probe."""
    loader = getattr(ctypes, "WinDLL", None)
    if loader is None:
        return None
    try:
        return loader(name)
    except OSError:
        return None


def _dll_present(name: str) -> bool:
    return _load(name) is not None


def probe_job_object() -> tuple[HonestState, str]:
    """Win32 Job Objects: PROCESS_CONTAINMENT, RESOURCE_LIMITS."""
    if platform.system() != WINDOWS:
        return _windows_only(), f"not Windows ({platform.system()})"
    kernel32 = _load("kernel32")
    if kernel32 is None:
        return HonestState.EXTERNAL_UNAVAILABLE, "kernel32 not loadable"
    if not hasattr(kernel32, "CreateJobObjectW"):
        return HonestState.UNSUPPORTED, "CreateJobObjectW absent"
    return HonestState.PASS, "kernel32!CreateJobObjectW present"


def probe_restricted_token() -> tuple[HonestState, str]:
    """Restricted / low-integrity tokens: FS_CONFINEMENT."""
    if platform.system() != WINDOWS:
        return _windows_only(), f"not Windows ({platform.system()})"
    advapi = _load("advapi32")
    if advapi is None:
        return HonestState.EXTERNAL_UNAVAILABLE, "advapi32 not loadable"
    if not hasattr(advapi, "CreateRestrictedToken"):
        return HonestState.UNSUPPORTED, "CreateRestrictedToken absent"
    return HonestState.PASS, "advapi32!CreateRestrictedToken present"


def probe_workspace_acl(repo_root: pathlib.Path) -> tuple[HonestState, str]:
    """Per-workspace ACLs: FS_CONFINEMENT. Requires an NTFS-capable volume."""
    if platform.system() != WINDOWS:
        return _windows_only(), f"not Windows ({platform.system()})"
    kernel32 = _load("kernel32")
    if kernel32 is None:
        return HonestState.EXTERNAL_UNAVAILABLE, "kernel32 not loadable"
    try:
        drive = os.path.splitdrive(str(repo_root.resolve()))[0] + "\\"
        buffer = ctypes.create_unicode_buffer(261)
        flags = ctypes.c_uint()
        ok = kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive), None, 0, None,
            ctypes.byref(ctypes.c_uint()), ctypes.byref(flags), buffer, 261,
        )
    except (OSError, AttributeError) as exc:
        return HonestState.EXTERNAL_UNAVAILABLE, str(exc)
    if not ok:
        return HonestState.EXTERNAL_UNAVAILABLE, "GetVolumeInformationW failed"
    filesystem = buffer.value
    if filesystem.upper() != "NTFS":
        return HonestState.UNSUPPORTED, f"volume filesystem is {filesystem}"
    return HonestState.PASS, f"{drive} is {filesystem}, ACLs supported"


def probe_wfp_egress() -> tuple[HonestState, str]:
    """Windows Filtering Platform egress control: NET_EGRESS_CONTROL.

    WFP filter installation requires administrative privilege. Without it the
    primitive exists but cannot be used from here, which is NOT_CONFIGURED - not
    UNSUPPORTED, and certainly not PASS.
    """
    if platform.system() != WINDOWS:
        return _windows_only(), f"not Windows ({platform.system()})"
    if not _dll_present("fwpuclnt"):
        return HonestState.UNSUPPORTED, "fwpuclnt.dll absent"
    shell32 = _load("shell32")
    if shell32 is None:
        return HonestState.EXTERNAL_UNAVAILABLE, "shell32 not loadable"
    try:
        elevated = bool(shell32.IsUserAnAdmin())
    except (OSError, AttributeError) as exc:
        return HonestState.EXTERNAL_UNAVAILABLE, str(exc)
    if not elevated:
        return (
            HonestState.NOT_CONFIGURED,
            "fwpuclnt.dll present but process is not elevated; WFP filters "
            "cannot be installed from here",
        )
    return HonestState.PASS, "fwpuclnt.dll present and process elevated"


def probe_vault_detach() -> tuple[HonestState, str]:
    """Credential isolation via OS key protection (DPAPI): CREDENTIAL_ISOLATION."""
    if platform.system() != WINDOWS:
        return _windows_only(), f"not Windows ({platform.system()})"
    crypt32 = _load("crypt32")
    if crypt32 is None:
        return HonestState.UNSUPPORTED, "crypt32.dll absent"
    if not hasattr(crypt32, "CryptProtectData"):
        return HonestState.UNSUPPORTED, "CryptProtectData absent"
    return HonestState.PASS, "crypt32!CryptProtectData (DPAPI) present"


def probe_windows_sandbox() -> tuple[HonestState, str]:
    """Windows Sandbox: KERNEL_ISOLATION + DISPOSABILITY. Optional feature."""
    if platform.system() != WINDOWS:
        return _windows_only(), f"not Windows ({platform.system()})"
    binary = pathlib.Path(os.environ.get("SystemRoot", r"C:\Windows"))
    candidate = binary / "System32" / "WindowsSandbox.exe"
    if candidate.is_file():
        return HonestState.PASS, f"{candidate} present"
    return (
        HonestState.NOT_CONFIGURED,
        "WindowsSandbox.exe absent; the optional feature is not enabled. "
        "Not enabled by this probe - enabling a Windows feature is a system "
        "configuration change.",
    )


def probe_hyperv() -> tuple[HonestState, str]:
    """Hyper-V containers: KERNEL_ISOLATION."""
    if platform.system() != WINDOWS:
        return _windows_only(), f"not Windows ({platform.system()})"
    binary = pathlib.Path(os.environ.get("SystemRoot", r"C:\Windows"))
    vmms = binary / "System32" / "vmms.exe"
    if vmms.is_file():
        return HonestState.PASS, f"{vmms} present"
    return (
        HonestState.NOT_CONFIGURED,
        "vmms.exe absent; Hyper-V platform is not enabled. Not enabled by "
        "this probe.",
    )


#: One probe: takes the repo root, returns a state and the evidence for it.
ProbeFn = Callable[[pathlib.Path], tuple[HonestState, str]]

#: backend name -> probe. Names must match AUTHORITY_MAP.yaml `isolation.backends`;
#: the reconciliation is asserted by a permanent test, never assumed here.
PROBES: dict[str, ProbeFn] = {
    "job_object": lambda root: probe_job_object(),
    "restricted_token": lambda root: probe_restricted_token(),
    "workspace_acl": probe_workspace_acl,
    "wfp_egress": lambda root: probe_wfp_egress(),
    "vault_detach": lambda root: probe_vault_detach(),
    "windows_sandbox": lambda root: probe_windows_sandbox(),
    "hyperv_container": lambda root: probe_hyperv(),
}


def probe_all(
    authority: IsolationAuthority, repo_root: pathlib.Path
) -> tuple[BackendDescriptor, ...]:
    """Probe every canonically declared backend. Unprobed backends stay NOT_TESTED."""
    found: list[BackendDescriptor] = []
    for name, provides in sorted(authority.declared_backends().items()):
        probe = PROBES.get(name)
        if probe is None:
            found.append(
                BackendDescriptor(
                    name=name,
                    provides=provides,
                    availability=HonestState.NOT_TESTED,
                    detail="no probe implemented; availability is not assumed",
                )
            )
            continue
        state, detail = probe(repo_root)
        found.append(
            BackendDescriptor(
                name=name, provides=provides, availability=state, detail=detail
            )
        )
    return tuple(found)
