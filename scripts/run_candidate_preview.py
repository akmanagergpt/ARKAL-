#!/usr/bin/env python3
"""Start a real, already-ACCEPTED candidate so a person can look at it running,
then stop it. Nothing else.

V1 SCOPE ONLY: DISCOVER -> INSPECT -> RUN -> VIEW -> STOP. No edit, no
regenerate, no auto-repair, no deploy, no conversation -- see
`docs/build/OPEN_BLOCKERS.md` (DEF-009) for why a persistent, editable
live-preview is a materially larger obligation than this.

REUSE, NOT A SECOND RUNTIME ENGINE. The install/start/health/stop shape
here is the exact one `run_golden_acceptance.py` already proved real:
clean venv, `pip install -r backend/requirements.txt`, a production
frontend build (`NODE_OPTIONS=--openssl-legacy-provider` -- required on
this host, see the frontend build memory), then `scripts/serve_spa.py`.
The process-lifecycle primitives (`wait_http`, `stop_process`) are the
SAME functions that script now imports too, from
`engineering.candidate.runtime_process` -- not a duplicate copy that can
drift. Isolation reuses `WorkspaceAuthority.allocate`, the same
authority `engineering.candidate.workspace` already gives every other
isolated candidate copy in this repository -- not a second workspace
mechanism.

WHY THE SAME 3000/5000 PORTS AS ACCEPTANCE, NOT A DISTINCT PAIR. A real
live-proof run against `golden-work-129` first tried distinct ports
(4500/4501) to avoid any possible collision with a concurrent acceptance
run -- and surfaced a real, honest finding: the generated frontend's
production build has its API base URL (`http://localhost:5000`) baked in
at build time, not parameterized. A preview on any other backend port is
provably broken -- every request the real UI makes fails with
CONNECTION_REFUSED, no matter how healthy the backend itself is. Reusing
acceptance's exact ports is therefore not a stylistic choice; it is the
only port pair this candidate's own build can actually talk to. The real
cost is `port_is_free` refusing to start a preview while a real
acceptance run holds these same ports -- an already-rare, short-lived,
explicitly human-invoked action, and an honest refusal beats a preview
that looks ready but cannot load any data.

WHY THIS NEVER TOUCHES THE LEDGER'S ACCEPTANCE STATE MACHINE. Real
acceptance (`run_golden_acceptance.py`) calls `ledger.begin_acceptance`
and, in its `finally`, `ledger.record_state(...)` -- every acceptance
run REWRITES the candidate's real governance history. A preview is not
a re-acceptance: it must never be able to overwrite a real `ACCEPTED`
verdict just because a preview happened to hit a transient hiccup. This
script therefore only ever READS the ledger (`latest`) to check
eligibility, and never calls any state-mutating ledger method. Only a
candidate whose latest real state is exactly ACCEPTED may be started;
nothing else is ever offered to a normal user as "your running app" --
see ARK-REQ concerning honest state representation and this turn's own
directive (Part B, item 11).

WHY NO NEW REGISTRY. This script IS the one authority for the processes
it starts, for exactly as long as it is running: it starts both
processes, waits for real HTTP health, prints the two real URLs, then
blocks until interrupted (Ctrl+C, or the parent process it was spawned
from being told to stop) and *always* stops both processes and removes
the isolated workspace in `finally`, on every exit path including an
exception. No PID file, no RuntimeRegistry, no PreviewRegistry, no
second truth store -- there is nothing to remember once this process
exits, because nothing it started is still running.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

from arkali.engineering.candidate.ledger import ACCEPTED, CandidateLedger  # noqa: E402
from arkali.engineering.candidate.runtime_process import (  # noqa: E402
    port_is_free,
    stop_process,
    wait_http,
    wait_tcp,
)
from arkali.engineering.candidate.workspace import WorkspaceAuthority  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "var" / "factory" / "candidates"
PREVIEWS = ROOT / "var" / "factory" / "previews"
#: The SAME ports `run_golden_acceptance.py` uses -- required, not a
#: preference: a golden candidate's frontend production build has this
#: exact backend origin baked in (see module docstring). A concurrent
#: acceptance run and a concurrent preview cannot both hold these ports;
#: `port_is_free` below refuses honestly rather than starting a preview
#: that can never load real data.
BACKEND_PORT = 5000
FRONTEND_PORT = 3000


class PreviewRefused(Exception):
    """A real, honest refusal -- never a fake or degraded preview."""


def _candidate_dir(candidate_id: str) -> pathlib.Path:
    if not candidate_id.replace("-", "").isalnum():
        raise PreviewRefused(f"not a valid candidate id: {candidate_id!r}")
    path = (CANDIDATES / candidate_id).resolve()
    if path.parent != CANDIDATES.resolve() or not path.is_dir():
        raise PreviewRefused(f"candidate does not exist: {candidate_id}")
    return path


def _require_accepted(candidate_id: str) -> None:
    ledger = CandidateLedger(CANDIDATES / "_ledger")
    latest = ledger.latest(candidate_id)
    state = latest.get("state") if latest is not None else None
    if state != ACCEPTED:
        raise PreviewRefused(
            f"candidate {candidate_id!r} is not ACCEPTED (real latest state: {state!r}); "
            "only a canonically accepted candidate may be shown to a user as a running app"
        )


def _npm() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _run(command: list[str], *, cwd: pathlib.Path, env: dict[str, str] | None = None,
          timeout_seconds: float = 300.0) -> str:
    process = subprocess.Popen(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        stop_process(process)
        raise RuntimeError(f"command timed out: {' '.join(command)}") from error
    if process.returncode:
        raise RuntimeError(f"command failed ({process.returncode}): {' '.join(command)}\n{output}")
    return output


@contextlib.contextmanager
def run_preview(candidate_id: str):  # noqa: ANN201
    """Start `candidate_id`'s backend+frontend and yield their real URLs.
    Always stops both processes and removes the isolated workspace on the
    way out, on every exit path."""
    _require_accepted(candidate_id)
    source = _candidate_dir(candidate_id)

    if not port_is_free(BACKEND_PORT) or not port_is_free(FRONTEND_PORT):
        raise PreviewRefused(
            f"preview ports {BACKEND_PORT}/{FRONTEND_PORT} are not both free; "
            "only one live preview may run on this host at a time (V1 scope)"
        )

    PREVIEWS.mkdir(parents=True, exist_ok=True)
    workspace_id = f"{candidate_id}-{int(time.time())}"
    workspace = WorkspaceAuthority(PREVIEWS).allocate(
        workspace_id=workspace_id, task_id="candidate-preview",
        agent_id="command-center", stable_snapshot=source,
    )
    candidate = workspace.snapshot
    backend = None
    frontend = None
    backend_log = None
    frontend_log = None
    try:
        venv = workspace.root / ".venv"
        _run([sys.executable, "-m", "venv", str(venv)], cwd=ROOT)
        python = venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
        _run([str(python), "-m", "pip", "install", "-r", "backend/requirements.txt"], cwd=candidate)

        backend_log = (workspace.root / "backend.log").open("w", encoding="utf-8")
        code = (
            "from backend.app import app; "
            f"app.run(host='127.0.0.1', port={BACKEND_PORT}, debug=False, use_reloader=False)"
        )
        backend = subprocess.Popen(
            [str(python), "-c", code], cwd=candidate, stdout=backend_log,
            stderr=subprocess.STDOUT, text=True, env={**os.environ, "FLASK_DEBUG": "0"},
        )
        #: A generated candidate's backend has no known-good route this
        #: script can name without loading its scenario/contracts (ARK-
        #: REQ-0074: this script names no candidate domain resource of its
        #: own) -- a TCP listener is the honest, domain-independent signal
        #: that Flask is actually up, without mistaking a real 404 for "not
        #: ready yet" the way polling an assumed HTTP route would.
        wait_tcp(BACKEND_PORT, backend, timeout=30.0)

        frontend_dir = candidate / "frontend"
        _run([_npm(), "install"], cwd=frontend_dir, timeout_seconds=600)
        build_env = {**os.environ, "NODE_OPTIONS": "--openssl-legacy-provider"}
        _run([_npm(), "run", "build"], cwd=frontend_dir, env=build_env, timeout_seconds=300)

        frontend_log = (workspace.root / "frontend.log").open("w", encoding="utf-8")
        frontend = subprocess.Popen(
            [str(python), str(ROOT / "scripts" / "serve_spa.py"),
             "--directory", str(frontend_dir / "build"), "--port", str(FRONTEND_PORT)],
            cwd=ROOT, stdout=frontend_log, stderr=subprocess.STDOUT, text=True,
        )
        wait_http(f"http://127.0.0.1:{FRONTEND_PORT}", frontend, timeout=30.0)

        yield {
            "candidate_id": candidate_id,
            "backend_url": f"http://127.0.0.1:{BACKEND_PORT}",
            "frontend_url": f"http://127.0.0.1:{FRONTEND_PORT}",
            "workspace_root": str(workspace.root),
        }
    finally:
        stop_process(frontend)
        stop_process(backend)
        #: Both processes are dead by now, but the log files this function
        #: opened are still held open by THIS process until explicitly
        #: closed -- and `shutil.rmtree` cannot remove an open file on
        #: Windows. Skipping this step is exactly how the workspace
        #: directory (though never .venv/snapshot, already the bulk of it)
        #: was left behind in this capability's first real proof run.
        if backend_log is not None:
            backend_log.close()
        if frontend_log is not None:
            frontend_log.close()
        shutil.rmtree(workspace.root, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument(
        "--max-seconds", type=float, default=180.0,
        help="hard ceiling; the preview always stops itself by then even if never interrupted",
    )
    args = parser.parse_args()

    try:
        with run_preview(args.candidate_id) as info:
            print(json.dumps({**info, "status": "READY"}), flush=True)
            deadline = time.monotonic() + args.max_seconds
            try:
                while time.monotonic() < deadline:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
            print(json.dumps({"status": "STOPPING"}), flush=True)
    except PreviewRefused as error:
        print(json.dumps({"status": "REFUSED", "reason": str(error)}), flush=True)
        return 1
    print(json.dumps({"status": "STOPPED"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
