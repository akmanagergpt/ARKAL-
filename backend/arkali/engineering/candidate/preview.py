"""Start a real, already-ACCEPTED candidate so a person can look at it
running, then stop it. Nothing else.

THE ONE OWNER. This is the single real implementation of the
install/start/health/stop sequence a live candidate preview needs — the
exact shape `run_golden_acceptance.py` already proved real (clean venv,
`pip install -r backend/requirements.txt`, a production frontend build
with `NODE_OPTIONS=--openssl-legacy-provider`, then `serve_spa.py`).
`scripts/run_candidate_preview.py` (a synchronous CLI) and
`scripts/run_candidate_preview_worker.py` (a durable-job-driven worker)
both call `run_preview` unchanged; neither holds its own copy of this
logic. The process-lifecycle primitives (`_wait_tcp`, `wait_http`,
`stop_process`, `port_is_free`) come from `runtime_process`, which this
module's own caller (`run_golden_acceptance.py`) also imports — one
implementation, never two that can drift.

WHY THE SAME 3000/5000 PORTS AS ACCEPTANCE, NOT A DISTINCT PAIR. A real
live-proof run against `golden-work-129` first tried distinct ports
(4500/4501) to avoid any possible collision with a concurrent acceptance
run — and surfaced a real, honest finding: the generated frontend's
production build has its API base URL (`http://localhost:5000`) baked in
at build time, not parameterized. A preview on any other backend port is
provably broken. Reusing acceptance's exact ports is therefore not a
stylistic choice; it is the only port pair this candidate's own build can
actually talk to. The real cost is `port_is_free` refusing to start a
preview while a real acceptance run holds these same ports — an already
rare, short-lived, explicitly human-invoked action, and an honest refusal
beats a preview that looks ready but cannot load any data.

WHY THIS NEVER TOUCHES THE LEDGER'S ACCEPTANCE STATE MACHINE. Real
acceptance calls `ledger.begin_acceptance` and, in its `finally`,
`ledger.record_state(...)` — every acceptance run REWRITES the
candidate's real governance history. A preview is not a re-acceptance: it
must never be able to overwrite a real `ACCEPTED` verdict just because a
preview happened to hit a transient hiccup. This module therefore only
ever READS the ledger (`latest`) to check eligibility, and never calls
any state-mutating ledger method. Only a candidate whose latest real
state is exactly ACCEPTED may be started; nothing else is ever offered to
a normal user as "your running app."

WHY NO NEW REGISTRY. `run_preview` is the one authority for the
processes it starts, for exactly as long as its caller holds the context
open: it starts both processes, waits for real health, yields the two
real URLs, then — on every exit path, including an exception — stops
both processes, closes their log handles, and removes the isolated
workspace. There is nothing to remember once the context exits, because
nothing it started is still running. A caller that needs real progress
reporting (the durable-job worker) passes `on_phase`; this module records
no progress of its own.
"""

from __future__ import annotations

import contextlib
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from typing import TypedDict

from arkali.engineering.candidate.ledger import ACCEPTED, CandidateLedger
from arkali.engineering.candidate.runtime_process import (
    port_is_free,
    stop_process,
    _wait_tcp,
    wait_http,
)
from arkali.engineering.candidate.workspace import WorkspaceAuthority

_ROOT = pathlib.Path(__file__).resolve().parents[4]
_CANDIDATES = _ROOT / "var" / "factory" / "candidates"
_PREVIEWS = _ROOT / "var" / "factory" / "previews"
#: The SAME ports `run_golden_acceptance.py` uses — see module docstring.
_BACKEND_PORT = 5000
_FRONTEND_PORT = 3000

#: Real, measured phase names a caller's `on_phase` may receive, in order.
#: Not a second state vocabulary — these describe *sub-steps within one
#: durable-job RUNNING state*, exactly the granularity a checkpoint
#: payload already carries for `software_factory.production` (see
#: `scripts/run_factory_worker.py`'s own "phase" checkpoints).
_PHASE_WORKSPACE_ALLOCATED = "workspace_allocated"
_PHASE_BACKEND_INSTALLED = "backend_installed"
_PHASE_BACKEND_STARTED = "backend_started"
_PHASE_FRONTEND_INSTALLED = "frontend_installed"
_PHASE_FRONTEND_BUILT = "frontend_built"
_PHASE_READY = "ready"


class _PreviewInfo(TypedDict):
    candidate_id: str
    backend_url: str
    frontend_url: str
    workspace_root: str


_OnPhase = Callable[[str, dict[str, object]], None]


class PreviewRefused(Exception):
    """A real, honest refusal — never a fake or degraded preview."""


class PreviewCancelled(Exception):
    """A real "Durdur" (`should_cancel` returning True) was honoured while
    still inside the slow install/build phase — before there was even a
    process to hand to `stop_process`. Distinct from `PreviewRefused`: this
    is not an eligibility refusal, it is an honoured user request."""


#: How often a long install/build step re-checks `should_cancel` — bounds
#: real cancellation latency to roughly this, not to however long the
#: remaining subprocess work would otherwise take.
_CANCEL_POLL_SECONDS = 2.0


def _candidate_dir(candidate_id: str) -> pathlib.Path:
    if not candidate_id.replace("-", "").isalnum():
        raise PreviewRefused(f"not a valid candidate id: {candidate_id!r}")
    path = (_CANDIDATES / candidate_id).resolve()
    if path.parent != _CANDIDATES.resolve() or not path.is_dir():
        raise PreviewRefused(f"candidate does not exist: {candidate_id}")
    return path


def _require_accepted(candidate_id: str) -> None:
    """Raise `PreviewRefused` unless the real ledger's latest state for this
    candidate is exactly ACCEPTED. Exposed so a caller (the worker, the API)
    can refuse before even submitting a durable job for a candidate that was
    never going to be runnable."""
    ledger = CandidateLedger(_CANDIDATES / "_ledger")
    latest = ledger.latest(candidate_id)
    state = latest.get("state") if latest is not None else None
    if state != ACCEPTED:
        raise PreviewRefused(
            f"candidate {candidate_id!r} is not ACCEPTED (real latest state: {state!r}); "
            "only a canonically accepted candidate may be shown to a user as a running app"
        )


def _npm() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _run(
    command: list[str], *, cwd: pathlib.Path, env: dict[str, str] | None = None,
    timeout_seconds: float = 300.0, should_cancel: Callable[[], bool] | None = None,
) -> str:
    """Run one setup command to completion, honouring a real cancel request
    within `_CANCEL_POLL_SECONDS` instead of only after it finishes on its
    own. Output is redirected to a real file rather than `PIPE`: polling
    `process.poll()` without draining a pipe risks the classic deadlock
    once the child fills its output buffer, and `npm install`/`npm run
    build` write far more than fits in one."""
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as capture:
        process = subprocess.Popen(
            command, cwd=cwd, env=env, text=True, stdout=capture, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + timeout_seconds
        next_cancel_check = time.monotonic() + _CANCEL_POLL_SECONDS
        while process.poll() is None:
            now = time.monotonic()
            if now >= deadline:
                stop_process(process)
                raise RuntimeError(f"command timed out: {' '.join(command)}")
            if should_cancel is not None and now >= next_cancel_check:
                if should_cancel():
                    stop_process(process)
                    raise PreviewCancelled(f"cancelled while running: {' '.join(command)}")
                next_cancel_check = now + _CANCEL_POLL_SECONDS
            time.sleep(0.2)
        capture.seek(0)
        output = capture.read()
    if process.returncode:
        raise RuntimeError(f"command failed ({process.returncode}): {' '.join(command)}\n{output}")
    return output


@contextlib.contextmanager
def run_preview(
    candidate_id: str, *, on_phase: _OnPhase | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[_PreviewInfo]:
    """Start `candidate_id`'s backend+frontend and yield their real URLs.
    Always stops both processes and removes the isolated workspace on the
    way out, on every exit path.

    `on_phase(name, detail)`, if given, is called synchronously right
    after each real milestone below actually completes — never before,
    never speculatively. A caller with no use for progress reporting (the
    plain CLI) simply omits it.

    `should_cancel`, if given, is polled roughly every
    `_CANCEL_POLL_SECONDS` during the slow install/build steps below —
    bounded cooperative cancellation, not a promise of instant response,
    but nowhere close to "wait for npm to finish on its own" either. Raises
    `PreviewCancelled` (caught here, cleanup still runs in `finally`
    exactly as any other exit does) rather than returning a sentinel, so a
    caller cannot forget to check it.
    """
    def _report(phase: str, detail: dict[str, object]) -> None:
        if on_phase is not None:
            on_phase(phase, detail)

    _require_accepted(candidate_id)
    source = _candidate_dir(candidate_id)

    if not port_is_free(_BACKEND_PORT) or not port_is_free(_FRONTEND_PORT):
        raise PreviewRefused(
            f"preview ports {_BACKEND_PORT}/{_FRONTEND_PORT} are not both free; "
            "only one live preview may run on this host at a time (V1 scope)"
        )

    _PREVIEWS.mkdir(parents=True, exist_ok=True)
    workspace_id = f"{candidate_id}-{int(time.time())}"
    workspace = WorkspaceAuthority(_PREVIEWS).allocate(
        workspace_id=workspace_id, task_id="candidate-preview",
        agent_id="command-center", stable_snapshot=source,
    )
    _report(_PHASE_WORKSPACE_ALLOCATED, {"workspace_root": str(workspace.root)})
    candidate = workspace.snapshot
    backend = None
    frontend = None
    backend_log = None
    frontend_log = None
    try:
        venv = workspace.root / ".venv"
        _run([sys.executable, "-m", "venv", str(venv)], cwd=_ROOT, should_cancel=should_cancel)
        python = venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
        _run(
            [str(python), "-m", "pip", "install", "-r", "backend/requirements.txt"],
            cwd=candidate, should_cancel=should_cancel,
        )
        _report(_PHASE_BACKEND_INSTALLED, {})

        backend_log = (workspace.root / "backend.log").open("w", encoding="utf-8")
        code = (
            "from backend.app import app; "
            f"app.run(host='127.0.0.1', port={_BACKEND_PORT}, debug=False, use_reloader=False)"
        )
        backend = subprocess.Popen(
            [str(python), "-c", code], cwd=candidate, stdout=backend_log,
            stderr=subprocess.STDOUT, text=True, env={**os.environ, "FLASK_DEBUG": "0"},
        )
        #: A generated candidate's backend has no known-good route this
        #: module can name without loading its scenario/contracts (ARK-
        #: REQ-0074: this module names no candidate domain resource of its
        #: own) — a TCP listener is the honest, domain-independent signal
        #: that Flask is actually up, without mistaking a real 404 for "not
        #: ready yet" the way polling an assumed HTTP route would.
        _wait_tcp(_BACKEND_PORT, backend, timeout=30.0)
        _report(_PHASE_BACKEND_STARTED, {"backend_url": f"http://127.0.0.1:{_BACKEND_PORT}"})

        frontend_dir = candidate / "frontend"
        _run(
            [_npm(), "install"], cwd=frontend_dir, timeout_seconds=600,
            should_cancel=should_cancel,
        )
        _report(_PHASE_FRONTEND_INSTALLED, {})
        build_env = {**os.environ, "NODE_OPTIONS": "--openssl-legacy-provider"}
        _run(
            [_npm(), "run", "build"], cwd=frontend_dir, env=build_env, timeout_seconds=300,
            should_cancel=should_cancel,
        )
        _report(_PHASE_FRONTEND_BUILT, {})

        frontend_log = (workspace.root / "frontend.log").open("w", encoding="utf-8")
        frontend = subprocess.Popen(
            [str(python), str(_ROOT / "scripts" / "serve_spa.py"),
             "--directory", str(frontend_dir / "build"), "--port", str(_FRONTEND_PORT)],
            cwd=_ROOT, stdout=frontend_log, stderr=subprocess.STDOUT, text=True,
        )
        wait_http(f"http://127.0.0.1:{_FRONTEND_PORT}", frontend, timeout=30.0)

        info: _PreviewInfo = {
            "candidate_id": candidate_id,
            "backend_url": f"http://127.0.0.1:{_BACKEND_PORT}",
            "frontend_url": f"http://127.0.0.1:{_FRONTEND_PORT}",
            "workspace_root": str(workspace.root),
        }
        _report(_PHASE_READY, dict(info))
        yield info
    finally:
        stop_process(frontend)
        stop_process(backend)
        #: Both processes are dead by now, but the log files this function
        #: opened are still held open by THIS process until explicitly
        #: closed — and `shutil.rmtree` cannot remove an open file on
        #: Windows. Skipping this step is exactly how the workspace
        #: directory (though never .venv/snapshot, already the bulk of it)
        #: was left behind in this capability's first real proof run.
        if backend_log is not None:
            backend_log.close()
        if frontend_log is not None:
            frontend_log.close()
        shutil.rmtree(workspace.root, ignore_errors=True)
