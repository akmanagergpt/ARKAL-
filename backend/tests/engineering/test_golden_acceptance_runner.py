from __future__ import annotations

import importlib.util
import pathlib
import sys
import threading
import urllib.request

import pytest

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
