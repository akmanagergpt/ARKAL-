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

THE BUILD CACHE IS A DISPOSABLE DERIVED ARTIFACT, NEVER A SECOND TRUTH
STORE. `npm install`/`npm run build` measured 250+ of a real ~277s cold
run — install/build outputs but not the venv or PID, port, log or job
state, none of which is reproducible-input-derived. The cache key is
`file_manifest` (`engineering.candidate.ledger`, already the same real,
deterministic, sorted, symlink-safe hash this context uses to verify a
candidate's real content at acceptance) over the candidate's own source
tree — REUSED unchanged, not re-derived — folded through the same
`content_identity.address_of` `evidence.artifact` already uses for its
own content addresses, plus one explicit `_CACHE_SCHEMA_VERSION` constant
so changing what this function caches or how invalidates every existing
entry deterministically, the same way changing a candidate's own source,
`requirements.txt`, `package.json` or lockfile does (all real files
`file_manifest` already walks — nothing about them is special-cased).
A cache entry is populated only by an atomic rename from a temp directory
after a real successful build, so a crash or a cancel mid-populate never
leaves a partial entry an unlucky later hit could restore. Deleting the
whole cache directory at any time only ever costs the next preview a slow
cold build — `CandidateLedger`'s real ACCEPTED verdict, the real source
tree, and every other real fact this module reads are untouched by its
presence, absence, or content.

CACHE PUBLICATION NEVER BLOCKS USER-FACING READY. A real, measured cold
run (this turn's own live benchmark) proved `_populate_cache` sitting
directly in front of the frontend server start and `wait_http` cost the
user a real, avoidable ~20s beyond the moment the runtime was already
genuinely usable — the cache is a disposable optimization for the *next*
preview, never a precondition of *this* one being real. Population now
runs on a plain `threading.Thread` this function starts right after a
cold build succeeds and always joins in its own `finally`, before the
workspace those copies read from can be removed — never a background
daemon, scheduler or persistent authority: its entire life is bounded by
and owned by one `run_preview` call, exactly the same shape the durable-
job *worker* already is for the *preview* call itself, one level up.
`_populate_cache` takes the same `should_cancel` contract `_run` already
does and checks it between its three real copy steps (never mid-copy,
`shutil.copytree` cannot be interrupted partway through) — bounded
cooperative cancellation, reused, not reinvented: a real "Durdur" arriving
while the runtime is already up and population is still running stops it
within about one copy step, discards its temp directory, and never
promotes a partial entry.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from typing import TypedDict

from arkali.engineering.candidate.content_identity import address_of
from arkali.engineering.candidate.ledger import ACCEPTED, CandidateLedger, file_manifest
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

#: Disposable derived build artifacts only -- see the module docstring's
#: "THE BUILD CACHE" section. Deleting this whole directory at any time is
#: always safe; the next preview just builds cold again.
_BUILD_CACHE = _ROOT / "var" / "factory" / "preview-build-cache"
#: Bump this to invalidate every existing cache entry deterministically
#: when what gets cached, or how, ever changes -- the one build-recipe
#: input `file_manifest` (a pure function of the candidate's own source
#: tree) cannot see for itself.
_CACHE_SCHEMA_VERSION = "1"
_CACHE_VENV_DIR = "venv"
_CACHE_NODE_MODULES_DIR = "node_modules"
_CACHE_FRONTEND_BUILD_DIR = "frontend_build"

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
#: Reported instead of the install/build phases above when a real prior
#: build's cached output was restored -- never a claim that install or
#: build ran again, since neither did.
_PHASE_RESTORED_FROM_CACHE = "restored_from_cache"


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


def _cache_key_for(source: pathlib.Path) -> str:
    """The candidate's real, deterministic content identity -- REUSED,
    never re-derived: `file_manifest` is the same sorted, symlink-safe hash
    `CandidateLedger.verify_integrity` already trusts for this exact
    candidate directory. Source content, `requirements.txt`, `package.json`
    and any lockfile are all real files under `source` this already walks;
    nothing about a build input is special-cased. `_CACHE_SCHEMA_VERSION`
    is folded in so a change to what this module caches, independent of
    the candidate's own content, still invalidates deterministically.
    """
    manifest = file_manifest(source)
    canonical = json.dumps(
        {"schema": _CACHE_SCHEMA_VERSION, "manifest": manifest},
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return address_of(canonical)


def _restore_from_cache(cache_dir: pathlib.Path, workspace_root: pathlib.Path, candidate: pathlib.Path) -> bool:
    """True and restored if a complete prior build exists for this exact
    content identity; False (nothing touched) otherwise. Copies, not
    moves or links -- the cache entry must survive being read from
    repeatedly, and this preview's own workspace is disposable regardless
    of whether it came from a cache hit or a cold build."""
    venv_src = cache_dir / _CACHE_VENV_DIR
    node_modules_src = cache_dir / _CACHE_NODE_MODULES_DIR
    build_src = cache_dir / _CACHE_FRONTEND_BUILD_DIR
    if not (venv_src.is_dir() and node_modules_src.is_dir() and build_src.is_dir()):
        return False
    shutil.copytree(venv_src, workspace_root / ".venv")
    frontend_dir = candidate / "frontend"
    shutil.copytree(node_modules_src, frontend_dir / "node_modules")
    shutil.copytree(build_src, frontend_dir / "build")
    return True


def _populate_cache(
    cache_dir: pathlib.Path, workspace_root: pathlib.Path, candidate: pathlib.Path,
    *, should_cancel: Callable[[], bool] | None = None,
) -> None:
    """Called only after a real successful cold build. Builds the entry in
    a temp directory and `os.replace`s it into place as the last step, so
    a crash, a cancel, or two previews racing on the same content identity
    can never leave -- or restore from -- a half-written entry. If another
    process already completed this exact entry first, this one's own temp
    copy is simply discarded rather than raising: same content identity
    means the two builds are interchangeable by construction.

    `should_cancel`, if given, is checked between each of the three real
    copies below (never mid-copy -- `shutil.copytree` has no interruption
    point of its own) and simply returns, abandoning the temp directory
    for `finally` to remove, rather than ever promoting a partial entry.
    Runs on a background thread (see `run_preview`); this function itself
    is oblivious to that -- it is plain, sequential, synchronous code.
    """
    def _cancelled() -> bool:
        return should_cancel is not None and should_cancel()

    _BUILD_CACHE.mkdir(parents=True, exist_ok=True)
    temp_dir = _BUILD_CACHE / f".tmp-{uuid.uuid4().hex}"
    try:
        temp_dir.mkdir()
        if _cancelled():
            return
        shutil.copytree(workspace_root / ".venv", temp_dir / _CACHE_VENV_DIR)
        if _cancelled():
            return
        frontend_dir = candidate / "frontend"
        shutil.copytree(frontend_dir / "node_modules", temp_dir / _CACHE_NODE_MODULES_DIR)
        if _cancelled():
            return
        shutil.copytree(frontend_dir / "build", temp_dir / _CACHE_FRONTEND_BUILD_DIR)
        if cache_dir.exists():
            return  # a concurrent populate for the identical content identity won the race
        os.replace(temp_dir, cache_dir)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)  # a no-op once `os.replace` has moved it


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
    """Start `candidate_id`'s backend+frontend and yield their real URLs;
    always stops both and removes the workspace on every exit path.
    `on_phase`/`should_cancel` behave exactly as `_run_preview_over_source`
    documents. Thin wrapper: the only candidate-specific work here is
    eligibility (`_require_accepted`) and source resolution
    (`_candidate_dir`) -- everything else is `_run_preview_over_source`,
    the subject-generic runtime primitive a future Managed Product
    proposed-revision preview reuses unchanged (D-030).
    """
    _require_accepted(candidate_id)
    source = _candidate_dir(candidate_id)
    with _run_preview_over_source(
        candidate_id, source, on_phase=on_phase, should_cancel=should_cancel,
    ) as info:
        yield info


@contextlib.contextmanager
def _run_preview_over_source(
    identity: str, source: pathlib.Path, *, on_phase: _OnPhase | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> Iterator[_PreviewInfo]:
    """The real install/start/health/stop/cache sequence, over ANY real
    resolved source directory -- candidate eligibility already decided by
    the caller. `identity` is a plain label (workspace naming, the
    `candidate_id` field of the yielded info) -- this function attaches no
    lifecycle meaning to it and never reads `CandidateLedger` itself.
    `on_phase(name, detail)`, if given, is called synchronously right
    after each real milestone below completes. `should_cancel`, if given,
    is polled roughly every `_CANCEL_POLL_SECONDS` during the slow
    install/build steps and raises `PreviewCancelled` (cleanup still runs
    in `finally`) rather than returning a sentinel.
    """
    def _report(phase: str, detail: dict[str, object]) -> None:
        if on_phase is not None:
            on_phase(phase, detail)

    if not port_is_free(_BACKEND_PORT) or not port_is_free(_FRONTEND_PORT):
        raise PreviewRefused(
            f"preview ports {_BACKEND_PORT}/{_FRONTEND_PORT} are not both free; "
            "only one live preview may run on this host at a time (V1 scope)"
        )

    _PREVIEWS.mkdir(parents=True, exist_ok=True)
    workspace_id = f"{identity}-{int(time.time())}"
    workspace = WorkspaceAuthority(_PREVIEWS).allocate(
        workspace_id=workspace_id, task_id="candidate-preview",
        agent_id="command-center", stable_snapshot=source,
    )
    _report(_PHASE_WORKSPACE_ALLOCATED, {"workspace_root": str(workspace.root)})
    candidate = workspace.snapshot
    #: Computed once, up front, over the real source this workspace was
    #: just snapshotted from -- never over the workspace copy itself,
    #: which `WorkspaceAuthority` already proved identical to `source`.
    cache_key = _cache_key_for(source)
    cache_dir = _BUILD_CACHE / cache_key.replace(":", "_")
    backend = None
    frontend = None
    backend_log = None
    frontend_log = None
    cache_thread: threading.Thread | None = None
    try:
        venv = workspace.root / ".venv"
        python = venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
        cache_hit = _restore_from_cache(cache_dir, workspace.root, candidate)
        if cache_hit:
            _report(_PHASE_RESTORED_FROM_CACHE, {"cache_key": cache_key})
            _report(_PHASE_BACKEND_INSTALLED, {})
        else:
            _run([sys.executable, "-m", "venv", str(venv)], cwd=_ROOT, should_cancel=should_cancel)
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
        if cache_hit:
            _report(_PHASE_FRONTEND_INSTALLED, {})
            _report(_PHASE_FRONTEND_BUILT, {})
        else:
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
            #: Only a real, just-succeeded cold build is ever cached --
            #: never a restored one (would just copy the cache onto
            #: itself) and never a failed one (an exception above skips
            #: this line entirely, `finally` still cleans up the workspace).
            #: Started here, on a background thread, so it never delays the
            #: frontend server start, `wait_http`, or user-facing READY
            #: below by even one second -- joined in `finally`, always
            #: before the workspace it reads from can be removed.
            cache_thread = threading.Thread(
                target=_populate_cache,
                args=(cache_dir, workspace.root, candidate),
                kwargs={"should_cancel": should_cancel},
                daemon=True,
            )
            cache_thread.start()

        frontend_log = (workspace.root / "frontend.log").open("w", encoding="utf-8")
        frontend = subprocess.Popen(
            [str(python), str(_ROOT / "scripts" / "serve_spa.py"),
             "--directory", str(frontend_dir / "build"), "--port", str(_FRONTEND_PORT)],
            cwd=_ROOT, stdout=frontend_log, stderr=subprocess.STDOUT, text=True,
        )
        wait_http(f"http://127.0.0.1:{_FRONTEND_PORT}", frontend, timeout=30.0)

        info: _PreviewInfo = {
            "candidate_id": identity,
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
        if cache_thread is not None:
            #: A real cancel (`should_cancel` true) makes `_populate_cache`
            #: itself return within about one copy step -- this join is a
            #: bound against something unforeseen hanging, not the real
            #: mechanism cancellation relies on. With no cancel, this simply
            #: waits for a real population that is usually already done or
            #: nearly done by the time a session ends.
            cache_thread.join(timeout=180.0)
        shutil.rmtree(workspace.root, ignore_errors=True)
