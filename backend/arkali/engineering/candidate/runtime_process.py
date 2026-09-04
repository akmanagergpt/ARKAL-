"""Owning and stopping one real, local candidate process.

Extracted, behaviour-unchanged, from the process-lifecycle helpers
`scripts/run_golden_acceptance.py` has run every real acceptance journey
through: cross-platform, PID-scoped termination (a venv `python.exe` on
Windows is a launcher, so `/T` is required to also stop the interpreter
it spawned -- never a process-name or global kill) and a bounded HTTP
health wait that also detects the owned process exiting early rather
than spinning to the timeout. Nothing here starts a process, decides
what is safe to run, or records any state -- it only owns the process
handles it is given until told to stop them.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.error
import urllib.request


def port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def port_accepts_connections(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def wait_tcp(port: int, process: subprocess.Popen[str], timeout: float = 20.0) -> None:
    """Block until something listens on `port`, or `process` exits early, or
    `timeout` elapses. For a caller with no known-good HTTP route to poll --
    unlike `wait_http`, a 404 here is not mistaken for "not ready"."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"owned process exited early with {process.returncode}")
        if port_accepts_connections(port):
            return
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for a listener on port {port}")


def wait_http(url: str, process: subprocess.Popen[str], timeout: float = 20.0) -> None:
    """Block until `url` answers or `process` exits early or `timeout` elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"owned process exited early with {process.returncode}")
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {url}")


def stop_process(process: subprocess.Popen[str] | None) -> None:
    """Terminate an owned process and everything it spawned. Never raises."""
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            text=True, capture_output=True, check=False,
        )
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
