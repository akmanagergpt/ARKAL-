from __future__ import annotations

import importlib.util
import pathlib
import sys
import threading
import urllib.request

import pytest

from arkali.engineering.candidate.ledger import (
    ACCEPTED,
    ACCEPTANCE_FAILED,
    CandidateLedger,
    file_manifest,
    GENERATING,
    GenerationProvenance,
    hash_text,
    INTERRUPTED,
    STAGE_FAILED,
    STAGED_GENERATION_PASS,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "run_golden_acceptance.py"


def _module():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("run_golden_acceptance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_candidate_path_rejects_traversal() -> None:
    runner = _module()
    with pytest.raises(ValueError, match="golden-work"):
        runner._candidate("../golden-work-090")


def test_candidate_path_rejects_a_missing_candidate() -> None:
    runner = _module()
    with pytest.raises(ValueError, match="does not exist"):
        runner._candidate("golden-work-999999")


def test_stop_owns_only_the_passed_process(monkeypatch) -> None:  # noqa: ANN001
    runner = _module()
    commands: list[list[str]] = []

    class Process:
        pid = 4321
        terminated = False

        def poll(self):  # noqa: ANN201
            return None

        def terminate(self) -> None:
            self.terminated = True

        def wait(self, timeout: float) -> int:
            assert timeout == 10
            return 0

    monkeypatch.setattr(
        runner.subprocess, "run",
        lambda command, **kwargs: commands.append(command),
    )
    process = Process()
    runner._stop(process)
    if runner.os.name == "nt":
        assert commands == [["taskkill", "/PID", "4321", "/T", "/F"]]
        assert not process.terminated
    else:
        assert process.terminated


def test_stopped_check_measures_a_listener_not_windows_bind_reuse(monkeypatch) -> None:  # noqa: ANN001
    runner = _module()

    class Socket:
        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def settimeout(self, timeout: float) -> None:
            assert timeout == 0.25

        def connect_ex(self, address: tuple[str, int]) -> int:
            assert address == ("127.0.0.1", 5000)
            return 10061  # connection refused; TIME_WAIT may still block bind

    monkeypatch.setattr(runner.socket, "socket", Socket)
    assert not runner._port_accepts_connections(5000)


def test_acceptance_uses_a_clean_copy_and_never_mutates_the_frozen_candidate(
    tmp_path: pathlib.Path,
) -> None:
    runner = _module()
    source = tmp_path / "source"
    (source / "frontend" / "node_modules").mkdir(parents=True)
    (source / "frontend" / "build").mkdir()
    (source / "frontend" / "src").mkdir()
    (source / "frontend" / "src" / "App.js").write_text("source", encoding="utf-8")
    (source / "backend.db").write_bytes(b"frozen")
    destination = tmp_path / "runtime-copy"
    runner._copy_candidate(source, destination)
    assert (destination / "frontend" / "src" / "App.js").read_text() == "source"
    assert not (destination / "frontend" / "node_modules").exists()
    assert not (destination / "frontend" / "build").exists()
    assert not (destination / "backend.db").exists()
    assert (source / "backend.db").read_bytes() == b"frozen"


def _provenance() -> GenerationProvenance:
    return GenerationProvenance(
        goal_hash=hash_text("goal"), source_commit="abc", runtime="ollama",
        endpoint="local", model="qwen",
    )


def _seed_verified_candidate(
    runner, monkeypatch, tmp_path: pathlib.Path, candidate_id: str,  # noqa: ANN001
) -> tuple[pathlib.Path, CandidateLedger]:
    """A real, isolated CANDIDATES/RUNTIMES root with one candidate whose
    ledger history is ALLOCATED -> GENERATING -> STAGED_GENERATION_PASS
    (the only state acceptance may begin from) and whose live content
    exactly matches the manifest recorded at that state."""
    candidates = tmp_path / "candidates"
    work = candidates / candidate_id
    work.mkdir(parents=True)
    (work / "App.js").write_text("// unmodified", encoding="utf-8")
    monkeypatch.setattr(runner, "CANDIDATES", candidates)
    monkeypatch.setattr(runner, "RUNTIMES", tmp_path / "runtime")

    ledger = CandidateLedger(candidates / "_ledger")
    ledger.allocate(candidate_id, provenance=_provenance())
    ledger.record_state(candidate_id, GENERATING, work)
    ledger.record_state(candidate_id, STAGED_GENERATION_PASS, work)
    return work, ledger


class _FakeProcess:
    """Stands in for both the backend and frontend `subprocess.Popen`
    handles -- `_stop` only ever needs `.poll()`/`.pid`/`.terminate()`/
    `.wait()`, never the real process."""

    def __init__(self) -> None:
        self.pid = 999999
        self._stopped = False

    def poll(self):  # noqa: ANN201
        return 0 if self._stopped else None

    def terminate(self) -> None:
        self._stopped = True

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
        self._stopped = True
        return 0


def _stub_a_full_successful_journey(runner, monkeypatch) -> None:  # noqa: ANN001
    """Replaces every real subprocess/network/browser step `_accept`
    takes with a fast, deterministic double -- proves the ledger/outcome
    wiring end-to-end without a real npm, flask, or Chromium install."""
    def fake_run(command, *, cwd, env=None, timeout_seconds=300.0):  # noqa: ANN001, ARG001
        if "run" in command and "build" in command:
            (cwd / "build").mkdir(parents=True, exist_ok=True)
            (cwd / "build" / "index.html").write_text("<html></html>", encoding="utf-8")
        return "ok\nok"

    def fake_json_request(method, url, payload=None):  # noqa: ANN001, ARG001
        if method == "POST" and url.endswith("/students"):
            return 201, {"id": 1}
        if method == "PUT" and "/students/" in url:
            return 200, {}
        if method == "POST" and url.endswith("/payments"):
            return 201, {"id": 1}
        if method == "GET" and url.endswith("/students"):
            return 200, [{"id": 1}]
        if method == "GET" and url.endswith("/payments"):
            return 200, [{"id": 1}]
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr(runner, "_run", fake_run)
    monkeypatch.setattr(runner, "_json_request", fake_json_request)
    monkeypatch.setattr(runner, "_wait_http", lambda *a, **k: None)
    monkeypatch.setattr(runner, "_port_is_free", lambda port: True)
    monkeypatch.setattr(runner, "_port_accepts_connections", lambda port: False)
    monkeypatch.setattr(runner, "_backend_process", lambda *a, **k: _FakeProcess())
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *a, **k: _FakeProcess())
    # `_stop`'s real Windows path shells out to `taskkill` via the (now
    # patched) `subprocess.Popen`; these tests aren't exercising `_stop`
    # itself (that's `test_stop_owns_only_the_passed_process`'s job), so
    # make it a no-op rather than fighting the patched Popen through it.
    monkeypatch.setattr(runner, "_stop", lambda process: None)


def test_1_staged_generation_pass_through_acceptance_running_to_accepted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate_id = "golden-work-pass"
    source, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)
    _stub_a_full_successful_journey(runner, monkeypatch)

    result = runner._accept(candidate_id, skip_browser=True)

    assert result["outcome"] == "GOLDEN_ACCEPTANCE_PASS"
    states = [entry["state"] for entry in ledger.history(candidate_id)]
    assert states == [
        "ALLOCATED", "GENERATING", "STAGED_GENERATION_PASS", "ACCEPTANCE_RUNNING", "ACCEPTED",
    ]
    assert ledger.classify(candidate_id) == ACCEPTED


def test_2_staged_generation_pass_through_acceptance_running_to_acceptance_failed(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate_id = "golden-work-checkfail"
    source, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)
    monkeypatch.setattr(runner, "_port_is_free", lambda port: False)  # the very first check fails

    result = runner._accept(candidate_id, skip_browser=True)

    assert result["outcome"] == "GOLDEN_ACCEPTANCE_FAILED"
    states = [entry["state"] for entry in ledger.history(candidate_id)]
    assert states == [
        "ALLOCATED", "GENERATING", "STAGED_GENERATION_PASS", "ACCEPTANCE_RUNNING",
        "ACCEPTANCE_FAILED",
    ]
    assert ledger.classify(candidate_id) == ACCEPTANCE_FAILED


def test_3_a_stage_failed_candidate_cannot_be_accepted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidates = tmp_path / "candidates"
    candidate_id = "golden-work-stagefailed"
    work = candidates / candidate_id
    work.mkdir(parents=True)
    (work / "App.js").write_text("// incomplete", encoding="utf-8")
    monkeypatch.setattr(runner, "CANDIDATES", candidates)
    monkeypatch.setattr(runner, "RUNTIMES", tmp_path / "runtime")
    ledger = CandidateLedger(candidates / "_ledger")
    ledger.allocate(candidate_id, provenance=_provenance())
    ledger.record_state(candidate_id, GENERATING, work)
    ledger.record_state(candidate_id, STAGE_FAILED, work)

    copied: list[object] = []
    monkeypatch.setattr(runner, "_copy_candidate", lambda *a, **k: copied.append(a))

    result = runner._accept(candidate_id, skip_browser=True)
    assert result["outcome"] == "CANDIDATE_INTEGRITY_FAILED"
    assert STAGE_FAILED in result["error"]
    assert copied == []
    assert ledger.classify(candidate_id) == STAGE_FAILED  # unchanged -- no transition recorded


def test_4_a_legacy_unverified_candidate_cannot_be_accepted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """A candidate this ledger has no history for at all (never allocated
    through it) must refuse before acceptance ever copies or touches it."""
    runner = _module()
    candidates = tmp_path / "candidates"
    candidate_id = "golden-work-nohistory"
    (candidates / candidate_id).mkdir(parents=True)
    (candidates / candidate_id / "App.js").write_text("// no ledger history", encoding="utf-8")
    monkeypatch.setattr(runner, "CANDIDATES", candidates)
    monkeypatch.setattr(runner, "RUNTIMES", tmp_path / "runtime")

    copied: list[object] = []
    monkeypatch.setattr(runner, "_copy_candidate", lambda *a, **k: copied.append(a))

    result = runner._accept(candidate_id, skip_browser=True)
    assert result["outcome"] == "CANDIDATE_INTEGRITY_FAILED"
    assert copied == []


def test_5_a_candidate_whose_manifest_was_modified_cannot_be_accepted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate_id = "golden-work-tampered"
    work, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)

    (work / "App.js").write_text("// tampered after the terminal state", encoding="utf-8")
    copied: list[object] = []
    monkeypatch.setattr(runner, "_copy_candidate", lambda *a, **k: copied.append(a))

    result = runner._accept(candidate_id, skip_browser=True)
    assert result["outcome"] == "CANDIDATE_INTEGRITY_FAILED"
    assert "changed=" in result["error"]
    assert copied == []


def test_6_a_second_concurrent_acceptance_attempt_is_refused(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate_id = "golden-work-concurrent"
    source, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)

    # Simulate a first attempt already holding the lock.
    lock_path = (runner.CANDIDATES / "_ledger") / f"{candidate_id}.acceptance.lock"
    fd = runner.os.open(str(lock_path), runner.os.O_CREAT | runner.os.O_EXCL | runner.os.O_WRONLY)
    runner.os.close(fd)

    copied: list[object] = []
    monkeypatch.setattr(runner, "_copy_candidate", lambda *a, **k: copied.append(a))

    result = runner._accept(candidate_id, skip_browser=True)
    assert result["outcome"] == "ACCEPTANCE_ALREADY_IN_PROGRESS"
    assert copied == []
    assert ledger.classify(candidate_id) == STAGED_GENERATION_PASS  # untouched


def test_7_a_crash_during_acceptance_is_recorded_as_interrupted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """A crash that is NOT a classified named-check failure -- here, the
    venv-creation step itself blowing up -- is genuinely ambiguous, not a
    verdict any check reached."""
    runner = _module()
    candidate_id = "golden-work-crash"
    source, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)
    monkeypatch.setattr(runner, "_port_is_free", lambda port: True)

    def boom(*a, **k):  # noqa: ANN001, ANN202
        raise RuntimeError("venv creation exploded")

    monkeypatch.setattr(runner, "_run", boom)

    result = runner._accept(candidate_id, skip_browser=True)
    assert result["outcome"] == "ACCEPTANCE_INTERRUPTED"
    assert ledger.classify(candidate_id) == INTERRUPTED


def test_7_a_keyboard_interrupt_during_acceptance_is_recorded_as_interrupted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate_id = "golden-work-ctrlc"
    source, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)
    monkeypatch.setattr(runner, "_port_is_free", lambda port: True)

    def interrupted(*a, **k):  # noqa: ANN001, ANN202
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_run", interrupted)

    with pytest.raises(KeyboardInterrupt):
        runner._accept(candidate_id, skip_browser=True)
    # Ctrl+C still propagates (the process really stops), but the ledger
    # and evidence were written first -- never a silently unrecorded gap.
    assert ledger.classify(candidate_id) == INTERRUPTED


def test_8_an_accepted_candidate_cannot_be_re_run(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate_id = "golden-work-noreplay"
    source, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)
    _stub_a_full_successful_journey(runner, monkeypatch)

    first = runner._accept(candidate_id, skip_browser=True)
    assert first["outcome"] == "GOLDEN_ACCEPTANCE_PASS"

    copied: list[object] = []
    monkeypatch.setattr(runner, "_copy_candidate", lambda *a, **k: copied.append(a))
    # `runtime` is named from `int(time.time())`; force a distinct second
    # so the two real, back-to-back calls don't collide on one directory.
    real_time = runner.time.time
    monkeypatch.setattr(runner.time, "time", lambda: real_time() + 1)
    second = runner._accept(candidate_id, skip_browser=True)
    assert second["outcome"] == "CANDIDATE_INTEGRITY_FAILED"
    assert "ACCEPTED" in second["error"]
    assert copied == []


def test_9_acceptance_evidence_dir_and_result_hash_are_recorded_in_the_ledger(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate_id = "golden-work-evidence"
    source, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)
    _stub_a_full_successful_journey(runner, monkeypatch)

    result = runner._accept(candidate_id, skip_browser=True)
    latest = ledger.latest(candidate_id)
    assert latest is not None
    detail = latest["detail"]
    assert detail["runtime_dir"]
    assert detail["evidence_dir"] == result["evidence_dir"]
    result_path = pathlib.Path(detail["evidence_dir"]) / "result.json"
    assert result_path.is_file()
    import hashlib
    assert detail["result_sha256"] == hashlib.sha256(result_path.read_bytes()).hexdigest()


def test_10_the_source_candidate_stays_byte_identical_across_acceptance(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate_id = "golden-work-untouched"
    source, ledger = _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)
    before = file_manifest(source)
    _stub_a_full_successful_journey(runner, monkeypatch)

    runner._accept(candidate_id, skip_browser=True)

    after = file_manifest(source)
    assert before == after


def test_skip_browser_can_never_report_acceptance(monkeypatch, capsys) -> None:  # noqa: ANN001
    runner = _module()
    monkeypatch.setattr(
        runner, "_accept",
        lambda candidate_id, skip_browser: {
            "outcome": "GOLDEN_ACCEPTANCE_PASS", "candidate_id": candidate_id,
        },
    )
    assert runner.main(["runner", "--candidate-id", "golden-work-090", "--skip-browser"]) == 2
    assert "GOLDEN_ACCEPTANCE_INCOMPLETE" in capsys.readouterr().out


def test_browser_journey_receives_the_real_persisted_student_id() -> None:
    source = (REPO / "scripts" / "run_golden_acceptance.py").read_text(encoding="utf-8")
    assert '"--student-id", str(student_id)' in source
    browser = (REPO / "scripts" / "run_golden_browser_journey.mjs").read_text(encoding="utf-8")
    assert "fillByLabel(page, /student.*id/i, studentId)" in browser


def test_run_kills_its_owned_process_tree_on_timeout(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    runner = _module()
    stopped: list[object] = []

    class Process:
        returncode = None

        def communicate(self, timeout: float):  # noqa: ANN202
            assert timeout == 7
            raise runner.subprocess.TimeoutExpired(["stuck"], timeout, output="partial")

    process = Process()
    monkeypatch.setattr(runner.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(runner, "_stop", lambda owned: stopped.append(owned))
    with pytest.raises(RuntimeError, match="timed out after 7s.*stuck"):
        runner._run(["stuck"], cwd=tmp_path, timeout_seconds=7)
    assert stopped == [process]


def test_frontend_install_has_a_finite_timeout() -> None:
    source = (REPO / "scripts" / "run_golden_acceptance.py").read_text(encoding="utf-8")
    assert '_run([npm, "install"], cwd=frontend_dir, timeout_seconds=600)' in source


def test_browser_journey_accepts_a_visible_accessible_form_without_a_heading() -> None:
    browser = (REPO / "scripts" / "run_golden_browser_journey.mjs").read_text(encoding="utf-8")
    assert "getByLabel(/name/i)" in browser
    assert "createHeading" not in browser


def test_production_server_returns_the_spa_for_a_browser_history_route(
    tmp_path: pathlib.Path,
) -> None:
    index = tmp_path / "index.html"
    index.write_text("spa-shell", encoding="utf-8")
    script = REPO / "scripts" / "serve_spa.py"
    spec = importlib.util.spec_from_file_location("serve_spa", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = lambda *values, **kwargs: module.SpaHandler(  # noqa: E731
        *values, directory=str(tmp_path), **kwargs,
    )
    server = module.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_port}/students", timeout=2,
        ) as response:
            assert response.status == 200
            assert response.read() == b"spa-shell"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
