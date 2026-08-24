#!/usr/bin/env python3
"""One isolated, real acceptance journey for a generated Golden candidate.

This runner owns every process it starts, disables Flask's debug reloader,
refuses occupied ports, and records one machine-readable result.  It never
edits the candidate and never turns a failed obligation into a PASS.
"""

from __future__ import annotations

import argparse
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

ROOT = pathlib.Path(__file__).resolve().parents[1]
CANDIDATES = ROOT / "var" / "factory" / "candidates"
RUNTIMES = ROOT / "var" / "factory" / "runtime"
BACKEND_PORT = 5000
FRONTEND_PORT = 3000


@dataclass
class Journey:
    candidate_id: str
    checks: list[dict[str, object]] = field(default_factory=list)

    def record(self, name: str, passed: bool, detail: str) -> None:
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            raise RuntimeError(f"{name}: {detail}")


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


def _run(command: list[str], *, cwd: pathlib.Path, env: dict[str, str] | None = None) -> str:
    completed = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, check=False,
    )
    output = completed.stdout + completed.stderr
    if completed.returncode:
        raise RuntimeError(f"command failed ({completed.returncode}): {' '.join(command)}\n{output}")
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


def _accept(candidate_id: str, *, skip_browser: bool = False) -> dict[str, object]:
    source_candidate = _candidate(candidate_id)
    journey = Journey(candidate_id)
    runtime = RUNTIMES / candidate_id / f"acceptance-{int(time.time())}"
    runtime.mkdir(parents=True, exist_ok=False)
    evidence = runtime / "evidence"
    evidence.mkdir()
    candidate = runtime / "candidate"
    _copy_candidate(source_candidate, candidate)
    backend: subprocess.Popen[str] | None = None
    frontend: subprocess.Popen[str] | None = None
    started = time.monotonic()
    result: dict[str, object]

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

        backend_log = (evidence / "backend-first.log").open("w", encoding="utf-8")
        backend = _backend_process(python, candidate, backend_log)
        _wait_http(f"http://127.0.0.1:{BACKEND_PORT}/students", backend)
        status, student = _json_request("POST", f"http://127.0.0.1:{BACKEND_PORT}/students", {
            "name": "Acceptance Student", "email": "acceptance@example.com",
        })
        student_id = int(student["id"])  # type: ignore[index]
        journey.record("student_create", status == 201, f"POST /students -> {status}, id={student_id}")
        status, _ = _json_request("PUT", f"http://127.0.0.1:{BACKEND_PORT}/students/{student_id}", {
            "name": "Acceptance Student Edited", "email": "edited@example.com",
        })
        journey.record("student_edit", status == 200, f"PUT /students/{student_id} -> {status}")
        status, payment = _json_request("POST", f"http://127.0.0.1:{BACKEND_PORT}/payments", {
            "student_id": student_id, "amount": 125.5, "due_date": "2030-01-15",
        })
        journey.record("payment_create", status == 201, f"POST /payments -> {status}, body={payment}")
        _stop(backend)
        backend = None
        journey.record(
            "backend_stopped", not _port_accepts_connections(BACKEND_PORT),
            "owned backend no longer accepts connections on port 5000",
        )

        backend_log.close()
        restart_log = (evidence / "backend-restart.log").open("w", encoding="utf-8")
        backend = _backend_process(python, candidate, restart_log)
        _wait_http(f"http://127.0.0.1:{BACKEND_PORT}/students", backend)
        _, students = _json_request("GET", f"http://127.0.0.1:{BACKEND_PORT}/students")
        _, payments = _json_request("GET", f"http://127.0.0.1:{BACKEND_PORT}/payments")
        persisted = any(row.get("id") == student_id for row in students) and bool(payments)  # type: ignore[union-attr]
        journey.record("sqlite_restart_persistence", persisted, "student and payment survived a real restart")

        frontend_dir = candidate / "frontend"
        npm = "npm.cmd" if os.name == "nt" else "npm"
        install_output = _run([npm, "install"], cwd=frontend_dir)
        journey.record("frontend_clean_install", True, install_output.strip().splitlines()[-1])
        build_env = {**os.environ, "NODE_OPTIONS": "--openssl-legacy-provider"}
        build_output = _run([npm, "run", "build"], cwd=frontend_dir, env=build_env)
        journey.record("frontend_production_build", (frontend_dir / "build" / "index.html").is_file(),
                       build_output.strip().splitlines()[-1])

        frontend_log = (evidence / "frontend.log").open("w", encoding="utf-8")
        frontend = subprocess.Popen(
            [str(python), "-m", "http.server", str(FRONTEND_PORT), "--bind", "127.0.0.1"],
            cwd=frontend_dir / "build", stdout=frontend_log, stderr=subprocess.STDOUT, text=True,
        )
        _wait_http(f"http://127.0.0.1:{FRONTEND_PORT}", frontend)
        if not skip_browser:
            browser_output = _run(
                ["node", str(ROOT / "scripts" / "run_golden_browser_journey.mjs"),
                 "--candidate", candidate_id, "--student-id", str(student_id)], cwd=ROOT,
            )
            (evidence / "browser.json").write_text(browser_output, encoding="utf-8")
            journey.record("real_browser_journey", True, browser_output.strip().splitlines()[-1])

        result = {
            "outcome": "GOLDEN_ACCEPTANCE_PASS", "candidate_id": candidate_id,
            "elapsed_seconds": round(time.monotonic() - started, 1), "checks": journey.checks,
            "evidence_dir": str(evidence),
        }
    except Exception as error:  # evidence must survive every real first failure
        result = {
            "outcome": "GOLDEN_ACCEPTANCE_FAILED", "candidate_id": candidate_id,
            "error": str(error), "elapsed_seconds": round(time.monotonic() - started, 1),
            "checks": journey.checks, "evidence_dir": str(evidence),
        }
    finally:
        _stop(frontend)
        _stop(backend)
        result_path = evidence / "result.json"
        result_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--skip-browser", action="store_true", help="diagnostic only; can never accept")
    args = parser.parse_args(argv[1:])
    result = _accept(args.candidate_id, skip_browser=args.skip_browser)
    if args.skip_browser and result["outcome"] == "GOLDEN_ACCEPTANCE_PASS":
        result["outcome"] = "GOLDEN_ACCEPTANCE_INCOMPLETE"
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["outcome"] == "GOLDEN_ACCEPTANCE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
