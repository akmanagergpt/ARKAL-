#!/usr/bin/env python3
"""One isolated, real acceptance journey for a generated Golden candidate.

This runner owns every process it starts, disables Flask's debug reloader,
refuses occupied ports, and records one machine-readable result.  It never
edits the candidate and never turns a failed obligation into a PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

from arkali.engineering.candidate.ledger import (  # noqa: E402
    ACCEPTANCE_FAILED,
    ACCEPTED,
    CandidateAcceptanceInProgressError,
    CandidateIntegrityError,
    CandidateLedger,
    INTERRUPTED,
)
from arkali.engineering.factory.acceptance_scenario import _AcceptanceScenario  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "var" / "factory" / "candidates"
RUNTIMES = ROOT / "var" / "factory" / "runtime"
BACKEND_PORT = 5000
FRONTEND_PORT = 3000
#: ARK-REQ-0074 ("Golden domain logic must not enter ARKALI core"): the
#: runner itself names no resource, field, or route -- every real domain
#: fact (route, payload, relationship, navigation, editable field) comes
#: from a real `_AcceptanceScenario` loaded from here. A different Golden
#: family gets its own sibling JSON, never a change to this script.
DEFAULT_SCENARIO = ROOT / "golden" / "scenarios" / "student_fee_management.json"


def _load_scenario(path: pathlib.Path) -> _AcceptanceScenario:
    return _AcceptanceScenario.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _relationship_payload(
    related: object, related_create_payload: dict[str, object], created_ids: dict[str, int],
) -> dict[str, object]:
    """`related_create_payload` plus every relationship field this
    resource declares, resolved against ids real earlier resources in
    this same journey actually got back from the backend -- never a
    literal id this runner invented itself."""
    payload = dict(related_create_payload)
    for field_name, resource_name in related.relationship_fields.items():  # type: ignore[attr-defined]
        if resource_name in created_ids:
            payload[field_name] = created_ids[resource_name]
    return payload


class AcceptanceCheckFailed(RuntimeError):
    """One specific, named acceptance check (`Journey.record`) failed --
    a classified, evidenced GOLDEN_ACCEPTANCE_FAILED outcome, distinct
    from an unclassified crash or a Ctrl+C (ACCEPTANCE_INTERRUPTED):
    every check that ran before this one, and the one that failed, are
    all in `Journey.checks` either way."""


@dataclass
class Journey:
    candidate_id: str
    checks: list[dict[str, object]] = field(default_factory=list)

    def record(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            raise AcceptanceCheckFailed(f"{name}: {detail}")


def _candidate(candidate_id: str) -> pathlib.Path:
    if not candidate_id.startswith("golden-work-") or not candidate_id.replace("-", "").isalnum():
        raise ValueError("candidate id must be a golden-work-* identifier")
    path = (CANDIDATES / candidate_id).resolve()
    if path.parent != CANDIDATES.resolve() or not path.is_dir():
        raise ValueError(f"candidate does not exist: {candidate_id}")
    return path


def _port_is_free(port: int) -> bool:
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _port_accepts_connections(port: int) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _copy_candidate(source: pathlib.Path, destination: pathlib.Path) -> None:
    shutil.copytree(
        source, destination,
        ignore=shutil.ignore_patterns(
            "node_modules", "build", ".pytest_cache", "__pycache__",
            "*.pyc", "backend.db",
        ),
    )


def _run(
    command: list[str], *, cwd: pathlib.Path, env: dict[str, str] | None = None,
    timeout_seconds: float = 300.0,
) -> str:
    process = subprocess.Popen(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        output, _ = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired as error:
        _stop(process)
        partial = error.output or ""
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        raise RuntimeError(
            f"command timed out after {timeout_seconds:g}s: {' '.join(command)}\n{partial}"
        ) from error
    if process.returncode:
        raise RuntimeError(f"command failed ({process.returncode}): {' '.join(command)}\n{output}")
    return output


def _json_request(
    method: str, url: str, payload: dict[str, object] | None = None,
) -> tuple[int, object]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=body, method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode())


def _wait_http(url: str, process: subprocess.Popen[str], timeout: float = 20.0) -> None:
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


def _stop(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        # A venv python.exe is a launcher which can leave the real interpreter
        # alive after terminating only its wrapper. /T is deliberately scoped
        # to this runner's own PID; no process-name/global kill is permitted.
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


def _backend_process(python: pathlib.Path, candidate: pathlib.Path, log) -> subprocess.Popen[str]:  # noqa: ANN001
    # Import and run the generated app ourselves: no debug reloader, one PID,
    # and therefore no stale inherited listening socket on Windows.
    code = (
        "from backend.app import app; "
        f"app.run(host='127.0.0.1', port={BACKEND_PORT}, debug=False, use_reloader=False)"
    )
    return subprocess.Popen(
        [str(python), "-c", code], cwd=candidate, stdout=log, stderr=subprocess.STDOUT,
        text=True, env={**os.environ, "FLASK_DEBUG": "0"},
    )


def _accept(
    candidate_id: str, scenario: _AcceptanceScenario, scenario_path: pathlib.Path,
    *, skip_browser: bool = False,
) -> dict[str, object]:
    source_candidate = _candidate(candidate_id)
    ledger = CandidateLedger(CANDIDATES / "_ledger")
    journey = Journey(candidate_id)
    runtime = RUNTIMES / candidate_id / f"acceptance-{int(time.time())}"
    runtime.mkdir(parents=True, exist_ok=False)
    evidence = runtime / "evidence"
    evidence.mkdir()
    started = time.monotonic()

    # begin_acceptance is the strict, atomic, single gate: eligibility
    # (latest recorded state must be exactly STAGED_GENERATION_PASS -- a
    # STAGE_FAILED, ACCEPTANCE_FAILED, already-ACCEPTED, or LEGACY_
    # UNVERIFIED candidate is refused here just as surely as a tampered
    # one), integrity (live content must match the manifest recorded at
    # that state), and the ACCEPTANCE_RUNNING transition itself, all
    # behind one cross-platform file lock so a second concurrent
    # acceptance attempt for the same candidate_id is refused outright.
    # Nothing about the source candidate is touched before this passes.
    try:
        ledger.begin_acceptance(candidate_id, source_candidate)
    except CandidateIntegrityError as error:
        result = {
            "outcome": "CANDIDATE_INTEGRITY_FAILED", "candidate_id": candidate_id,
            "error": str(error), "elapsed_seconds": round(time.monotonic() - started, 1),
            "checks": [], "evidence_dir": str(evidence),
        }
        (evidence / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        return result
    except CandidateAcceptanceInProgressError as error:
        result = {
            "outcome": "ACCEPTANCE_ALREADY_IN_PROGRESS", "candidate_id": candidate_id,
            "error": str(error), "elapsed_seconds": round(time.monotonic() - started, 1),
            "checks": [], "evidence_dir": str(evidence),
        }
        (evidence / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        return result

    candidate = runtime / "candidate"
    _copy_candidate(source_candidate, candidate)
    backend: subprocess.Popen[str] | None = None
    frontend: subprocess.Popen[str] | None = None
    # A real placeholder, not left unbound: a KeyboardInterrupt or crash
    # before any check even runs must still leave `finally` something
    # real to persist -- the candidate must never end up in a recorded-
    # nowhere, truly ambiguous state.
    result: dict[str, object] = {
        "outcome": "ACCEPTANCE_INTERRUPTED", "candidate_id": candidate_id,
        "error": "acceptance ended before any check completed",
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "checks": journey.checks, "evidence_dir": str(evidence),
    }

    try:
        journey.record("ports_free", all(_port_is_free(p) for p in (BACKEND_PORT, FRONTEND_PORT)),
                       "ports 3000 and 5000 must be free before acceptance")
        venv = runtime / ".venv"
        _run([sys.executable, "-m", "venv", str(venv)], cwd=ROOT)
        python = venv / "Scripts" / "python.exe" if os.name == "nt" else venv / "bin" / "python"
        pip_output = _run(
            [str(python), "-m", "pip", "install", "-r", "backend/requirements.txt"],
            cwd=candidate,
        )
        journey.record("backend_clean_install", True, pip_output.splitlines()[-1])
        test_output = _run([str(python), "-m", "pytest", "tests", "-q"], cwd=candidate)
        journey.record("generated_backend_tests", True, test_output.strip().splitlines()[-1])

        primary = scenario.resource(scenario.primary_resource)
        backend_log = (evidence / "backend-first.log").open("w", encoding="utf-8")
        backend = _backend_process(python, candidate, backend_log)
        _wait_http(f"http://127.0.0.1:{BACKEND_PORT}{primary.collection_route}", backend)
        status, primary_obj = _json_request(
            "POST", f"http://127.0.0.1:{BACKEND_PORT}{primary.collection_route}",
            scenario.create_payload,
        )
        primary_id = int(primary_obj["id"])  # type: ignore[index]
        created_ids = {scenario.primary_resource: primary_id}
        journey.record(
            f"{scenario.primary_resource}_create", status == 201,
            f"POST {primary.collection_route} -> {status}, id={primary_id}",
        )
        status, _ = _json_request(
            "PUT", f"http://127.0.0.1:{BACKEND_PORT}{primary.collection_route}/{primary_id}",
            scenario.update_payload,
        )
        journey.record(
            f"{scenario.primary_resource}_edit", status == 200,
            f"PUT {primary.collection_route}/{primary_id} -> {status}",
        )
        related = scenario.resource(scenario.related_resource) if scenario.related_resource else None
        if related is not None and scenario.related_create_payload is not None:
            related_payload = _relationship_payload(
                related, scenario.related_create_payload, created_ids,
            )
            status, related_obj = _json_request(
                "POST", f"http://127.0.0.1:{BACKEND_PORT}{related.collection_route}", related_payload,
            )
            journey.record(
                f"{scenario.related_resource}_create", status == 201,
                f"POST {related.collection_route} -> {status}, body={related_obj}",
            )
        _stop(backend)
        backend = None
        journey.record(
            "backend_stopped", not _port_accepts_connections(BACKEND_PORT),
            "owned backend no longer accepts connections on port 5000",
        )

        backend_log.close()
        restart_log = (evidence / "backend-restart.log").open("w", encoding="utf-8")
        backend = _backend_process(python, candidate, restart_log)
        _wait_http(f"http://127.0.0.1:{BACKEND_PORT}{primary.collection_route}", backend)
        _, primary_rows = _json_request(
            "GET", f"http://127.0.0.1:{BACKEND_PORT}{primary.collection_route}",
        )
        primary_persisted = any(row.get("id") == primary_id for row in primary_rows)  # type: ignore[union-attr]
        related_persisted = True
        if related is not None:
            _, related_rows = _json_request(
                "GET", f"http://127.0.0.1:{BACKEND_PORT}{related.collection_route}",
            )
            related_persisted = bool(related_rows)
        journey.record(
            "sqlite_restart_persistence", primary_persisted and related_persisted,
            f"{scenario.primary_resource} and {scenario.related_resource} survived a real restart",
        )

        frontend_dir = candidate / "frontend"
        npm = "npm.cmd" if os.name == "nt" else "npm"
        install_output = _run([npm, "install"], cwd=frontend_dir, timeout_seconds=600)
        journey.record("frontend_clean_install", True, install_output.strip().splitlines()[-1])
        build_env = {**os.environ, "NODE_OPTIONS": "--openssl-legacy-provider"}
        build_output = _run(
            [npm, "run", "build"], cwd=frontend_dir, env=build_env,
            timeout_seconds=300,
        )
        journey.record("frontend_production_build", (frontend_dir / "build" / "index.html").is_file(),
                       build_output.strip().splitlines()[-1])

        frontend_log = (evidence / "frontend.log").open("w", encoding="utf-8")
        frontend = subprocess.Popen(
            [str(python), str(ROOT / "scripts" / "serve_spa.py"),
             "--directory", str(frontend_dir / "build"), "--port", str(FRONTEND_PORT)],
            cwd=ROOT, stdout=frontend_log, stderr=subprocess.STDOUT, text=True,
        )
        _wait_http(f"http://127.0.0.1:{FRONTEND_PORT}", frontend)
        if not skip_browser:
            browser_output = _run(
                ["node", str(ROOT / "scripts" / "run_golden_browser_journey.mjs"),
                 "--candidate", candidate_id, "--scenario", str(scenario_path),
                 "--primary-id", str(primary_id)], cwd=ROOT,
                timeout_seconds=120,
            )
            (evidence / "browser.json").write_text(browser_output, encoding="utf-8")
            journey.record("real_browser_journey", True, browser_output.strip().splitlines()[-1])

        result = {
            "outcome": "GOLDEN_ACCEPTANCE_PASS", "candidate_id": candidate_id,
            "elapsed_seconds": round(time.monotonic() - started, 1), "checks": journey.checks,
            "evidence_dir": str(evidence),
        }
    except AcceptanceCheckFailed as error:  # a classified, evidenced failure
        result = {
            "outcome": "GOLDEN_ACCEPTANCE_FAILED", "candidate_id": candidate_id,
            "error": str(error), "elapsed_seconds": round(time.monotonic() - started, 1),
            "checks": journey.checks, "evidence_dir": str(evidence),
        }
    except (KeyboardInterrupt, Exception) as error:
        # Anything NOT a classified named-check failure -- Ctrl+C, a
        # crashed subprocess, a bug -- is genuinely ambiguous, not a
        # verdict any check reached; record it as such rather than
        # silently reusing GOLDEN_ACCEPTANCE_FAILED for it. A real
        # KeyboardInterrupt is re-raised once the ledger/evidence below
        # are written (`finally` always runs first) -- Ctrl+C must still
        # actually stop the process.
        result = {
            "outcome": "ACCEPTANCE_INTERRUPTED", "candidate_id": candidate_id,
            "error": str(error), "elapsed_seconds": round(time.monotonic() - started, 1),
            "checks": journey.checks, "evidence_dir": str(evidence),
        }
        if isinstance(error, KeyboardInterrupt):
            raise
    finally:
        _stop(frontend)
        _stop(backend)
        result_path = evidence / "result.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        result_sha256 = hashlib.sha256(result_path.read_bytes()).hexdigest()
        # Recorded against the original candidate directory, not the
        # isolated runtime copy -- acceptance observes the source, it
        # never mutates it. The ACCEPTANCE_RUNNING -> {..} transition
        # itself is what `record_state` enforces; an outcome this
        # function did not expect would be refused here, not silently
        # accepted.
        state = {
            "GOLDEN_ACCEPTANCE_PASS": ACCEPTED,
            "GOLDEN_ACCEPTANCE_FAILED": ACCEPTANCE_FAILED,
            "ACCEPTANCE_INTERRUPTED": INTERRUPTED,
        }[result["outcome"]]
        ledger.record_state(
            candidate_id, state, source_candidate,
            detail={
                "outcome": result["outcome"], "elapsed_seconds": result["elapsed_seconds"],
                "runtime_dir": str(runtime), "evidence_dir": str(evidence),
                "result_sha256": result_sha256,
            },
        )
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--skip-browser", action="store_true", help="diagnostic only; can never accept")
    parser.add_argument(
        "--scenario", type=pathlib.Path, default=DEFAULT_SCENARIO,
        help="path to a real AcceptanceScenario JSON file (ARK-REQ-0074: this runner names no "
             "resource, field, or route of its own); defaults to the Student/Fee Golden's own "
             f"scenario ({DEFAULT_SCENARIO.relative_to(ROOT)})",
    )
    args = parser.parse_args(argv[1:])
    scenario = _load_scenario(args.scenario)
    result = _accept(args.candidate_id, scenario, args.scenario, skip_browser=args.skip_browser)
    if args.skip_browser and result["outcome"] == "GOLDEN_ACCEPTANCE_PASS":
        result["outcome"] = "GOLDEN_ACCEPTANCE_INCOMPLETE"
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["outcome"] == "GOLDEN_ACCEPTANCE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
