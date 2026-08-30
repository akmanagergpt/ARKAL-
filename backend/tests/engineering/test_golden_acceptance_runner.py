from __future__ import annotations

import importlib.util
import json
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
DEFAULT_SCENARIO_PATH = REPO / "golden" / "scenarios" / "student_fee_management.json"


def _module():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("run_golden_acceptance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _accept(runner, candidate_id: str, *, skip_browser: bool = True, scenario_path=None):  # noqa: ANN001, ANN202
    """Defaults to the Student/Fee Golden's own real scenario -- most of
    these tests exercise the runner's real lifecycle/ledger wiring, not
    scenario generality. `TestCoreRunnerIsDomainIndependent` below passes
    a different real scenario_path to prove the exact same runner code
    drives an unrelated domain identically."""
    path = scenario_path or DEFAULT_SCENARIO_PATH
    scenario = runner._load_scenario(path)
    return runner._accept(candidate_id, scenario, path, skip_browser=skip_browser)


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


def _stub_a_full_successful_journey(runner, monkeypatch, scenario=None) -> None:  # noqa: ANN001
    """Replaces every real subprocess/network/browser step `_accept`
    takes with a fast, deterministic double -- proves the ledger/outcome
    wiring end-to-end without a real npm, flask, or Chromium install.
    Route matching is derived from `scenario` itself (default: the
    Student/Fee Golden's own real scenario) -- never hardcoded to one
    domain's routes, so the same stub serves every domain's own tests."""
    if scenario is None:
        scenario = runner._load_scenario(DEFAULT_SCENARIO_PATH)
    primary = scenario.resource(scenario.primary_resource)
    related = scenario.resource(scenario.related_resource) if scenario.related_resource else None

    def fake_run(command, *, cwd, env=None, timeout_seconds=300.0):  # noqa: ANN001, ARG001
        if "run" in command and "build" in command:
            (cwd / "build").mkdir(parents=True, exist_ok=True)
            (cwd / "build" / "index.html").write_text("<html></html>", encoding="utf-8")
        return "ok\nok"

    def fake_json_request(method, url, payload=None):  # noqa: ANN001, ARG001
        if method == "POST" and url.endswith(primary.collection_route):
            return 201, {"id": 1}
        if method == "PUT" and f"{primary.collection_route}/" in url:
            return 200, {}
        if method == "GET" and url.endswith(primary.collection_route):
            return 200, [{"id": 1}]
        if related is not None:
            if method == "POST" and url.endswith(related.collection_route):
                return 201, {"id": 1}
            if method == "GET" and url.endswith(related.collection_route):
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

    result = _accept(runner, candidate_id)

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

    result = _accept(runner, candidate_id)

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

    result = _accept(runner, candidate_id)
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

    result = _accept(runner, candidate_id)
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

    result = _accept(runner, candidate_id)
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

    result = _accept(runner, candidate_id)
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

    result = _accept(runner, candidate_id)
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
        _accept(runner, candidate_id)
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

    first = _accept(runner, candidate_id)
    assert first["outcome"] == "GOLDEN_ACCEPTANCE_PASS"

    copied: list[object] = []
    monkeypatch.setattr(runner, "_copy_candidate", lambda *a, **k: copied.append(a))
    # `runtime` is named from `int(time.time())`; force a distinct second
    # so the two real, back-to-back calls don't collide on one directory.
    real_time = runner.time.time
    monkeypatch.setattr(runner.time, "time", lambda: real_time() + 1)
    second = _accept(runner, candidate_id)
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

    result = _accept(runner, candidate_id)
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

    _accept(runner, candidate_id)

    after = file_manifest(source)
    assert before == after


def test_skip_browser_can_never_report_acceptance(
    monkeypatch, capsys, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    runner = _module()
    candidate = tmp_path / "golden-work-090"
    candidate.mkdir()
    monkeypatch.setattr(runner, "_candidate", lambda candidate_id: candidate)
    monkeypatch.setattr(runner, "_candidate_contract_files", lambda candidate_dir: {})
    monkeypatch.setattr(
        runner, "_resolve_scenario",
        lambda candidate_id, files, override: (object(), tmp_path / "scenario.json"),
    )
    monkeypatch.setattr(
        runner, "_accept",
        lambda candidate_id, scenario, scenario_path, skip_browser: {
            "outcome": "GOLDEN_ACCEPTANCE_PASS", "candidate_id": candidate_id,
        },
    )
    assert runner.main(["runner", "--candidate-id", "golden-work-090", "--skip-browser"]) == 2
    assert "GOLDEN_ACCEPTANCE_INCOMPLETE" in capsys.readouterr().out


def test_browser_journey_receives_the_real_persisted_primary_id_and_scenario() -> None:
    """ARK-REQ-0074: the runner passes the real scenario file through to
    the browser journey rather than naming a resource of its own."""
    source = (REPO / "scripts" / "run_golden_acceptance.py").read_text(encoding="utf-8")
    assert '"--scenario", str(scenario_path)' in source
    assert '"--primary-id", str(primary_id)' in source


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
    """Every editable field's own label is checked visible, derived from
    the real scenario's own field names -- never a hardcoded field name
    or an assumed "create" heading (golden-work-113/119's own real gap
    (3): a shared form component reused for create and edit renders no
    "Edit" heading of any kind on either route)."""
    browser = (REPO / "scripts" / "run_golden_browser_journey.mjs").read_text(encoding="utf-8")
    assert "primary.editable_form_fields" in browser
    assert "getByLabel(fieldPattern(fieldName))" in browser
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


class TestCoreRunnerIsDomainIndependent:
    """ARK-REQ-0074 ("Golden domain logic must not enter ARKALI core"):
    the exact same `_accept()` code, unchanged, drives an inventory
    product and a task/reservation product exactly as it drives the
    Student/Fee Golden -- every resource, route, and payload comes from
    the real scenario file, never from the runner itself."""

    def _run_scenario(self, monkeypatch, tmp_path: pathlib.Path, scenario_name: str):  # noqa: ANN001, ANN202
        runner = _module()
        scenario_path = REPO / "golden" / "scenarios" / f"{scenario_name}.json"
        candidate_id = f"golden-work-{scenario_name.replace('_', '')}"
        _seed_verified_candidate(runner, monkeypatch, tmp_path, candidate_id)
        scenario = runner._load_scenario(scenario_path)
        _stub_a_full_successful_journey(runner, monkeypatch, scenario=scenario)
        result = _accept(runner, candidate_id, scenario_path=scenario_path)
        return runner, scenario, result

    def test_inventory_management_scenario_reaches_a_real_pass(
        self, monkeypatch, tmp_path: pathlib.Path,
    ) -> None:
        _runner, scenario, result = self._run_scenario(monkeypatch, tmp_path, "inventory_management")
        assert result["outcome"] == "GOLDEN_ACCEPTANCE_PASS"
        check_names = {c["name"] for c in result["checks"]}
        assert f"{scenario.primary_resource}_create" in check_names
        assert f"{scenario.primary_resource}_edit" in check_names
        assert f"{scenario.related_resource}_create" in check_names
        assert "students_create" not in check_names
        assert "payments_create" not in check_names

    def test_task_management_scenario_reaches_a_real_pass(
        self, monkeypatch, tmp_path: pathlib.Path,
    ) -> None:
        _runner, scenario, result = self._run_scenario(monkeypatch, tmp_path, "task_management")
        assert result["outcome"] == "GOLDEN_ACCEPTANCE_PASS"
        check_names = {c["name"] for c in result["checks"]}
        assert f"{scenario.primary_resource}_create" in check_names
        assert f"{scenario.related_resource}_create" in check_names
        assert "students_create" not in check_names
        assert "products_create" not in check_names

    def test_all_three_domain_scenarios_produce_the_same_check_shape(
        self, monkeypatch, tmp_path: pathlib.Path,
    ) -> None:
        """The set of check KINDS (create/edit/related-create/backend-
        stopped/persistence/etc.) is identical across all three domains
        -- only the resource-name prefixes differ."""
        shapes = []
        for scenario_name in ("student_fee_management", "inventory_management", "task_management"):
            _runner, scenario, result = self._run_scenario(monkeypatch, tmp_path, scenario_name)
            assert result["outcome"] == "GOLDEN_ACCEPTANCE_PASS"
            generic_kinds = {
                name.replace(scenario.primary_resource, "PRIMARY").replace(
                    scenario.related_resource or "\0", "RELATED",
                )
                for name in (c["name"] for c in result["checks"])
            }
            shapes.append(generic_kinds)
        assert shapes[0] == shapes[1] == shapes[2]


def test_browser_journey_is_driven_entirely_by_the_scenario_file() -> None:
    """ARK-REQ-0074: the browser journey script itself names no resource,
    field, or route -- every literal comes from --scenario at runtime."""
    browser = (REPO / "scripts" / "run_golden_browser_journey.mjs").read_text(encoding="utf-8")
    assert "--scenario" in browser
    assert "--primary-id" in browser
    assert "JSON.parse(readFileSync(scenarioPath" in browser
    # Only inside historical-evidence prose comments (frozen session
    # evidence explaining a real, already-fixed race condition), never in
    # executable logic -- checked line-by-line, skipping comment lines.
    domain_tokens = ("student", "payment")
    for line in browser.splitlines():
        stripped = line.strip()
        if stripped.startswith("*") or stripped.startswith("//") or stripped.startswith("/**"):
            continue
        lowered = stripped.lower()
        for token in domain_tokens:
            assert token not in lowered, f"domain literal {token!r} found in executable line: {line!r}"


_DESIGN_SYSTEM = {
    "typography_scale": ["14px", "16px", "24px"],
    "spacing_scale": ["4px", "8px", "16px"],
    "component_conventions": ["primary buttons are filled"],
}


def _widget_contract_files(work: pathlib.Path) -> None:
    """Writes a real, minimal `product/ux_spec.json` + `backend/*.json`
    pair for a single-resource "widgets" product -- enough for
    `_compile_acceptance_plan` to derive a real scenario from, and
    unrelated to every real Student/Fee literal this file's own domain-
    independence tests already cover."""
    (work / "product").mkdir(parents=True, exist_ok=True)
    (work / "backend").mkdir(parents=True, exist_ok=True)
    (work / "product" / "ux_spec.json").write_text(json.dumps({
        "product_title": "Widget Tracker", "primary_roles": ["Operator"],
        "modules": [{
            "name": "widgets", "navigation_label": "Widgets", "presentation": "table",
            "actions": ["create", "edit", "delete"],
            "forms": [{"name": "WidgetForm", "fields": ["id", "name", "price"]}],
        }],
        "navigation_destinations": ["Widgets"], "design_system": _DESIGN_SYSTEM,
    }), encoding="utf-8")
    (work / "backend" / "routes.json").write_text(json.dumps([
        {"path": "/widgets", "method": "GET"}, {"path": "/widgets", "method": "POST"},
        {"path": "/widgets/{id}", "method": "PUT"}, {"path": "/widgets/{id}", "method": "DELETE"},
    ]), encoding="utf-8")
    (work / "backend" / "data_model.json").write_text(json.dumps(
        {"fields": {"widgets": {"id": "integer", "name": "string", "price": "float"}}},
    ), encoding="utf-8")


class TestScenarioResolution:
    """`main()` compiles a real scenario by default (ARK-REQ-0074 Part A:
    ARKALI cannot ask an operator to hand-author one per generated
    product), and only ever trusts an explicit `--scenario` override after
    it reconciles against the SAME candidate's own real contracts."""

    def test_resolve_scenario_compiles_by_default(self, tmp_path: pathlib.Path) -> None:
        runner = _module()
        monkeypatch_dir = tmp_path / "candidate"
        _widget_contract_files(monkeypatch_dir)
        contract_files = runner._candidate_contract_files(monkeypatch_dir)

        resolved = runner._resolve_scenario("golden-work-widgets", contract_files, None)
        assert not isinstance(resolved, dict)
        scenario, scenario_path = resolved
        assert scenario.primary_resource == "widgets"
        assert scenario_path.is_file()
        assert json.loads(scenario_path.read_text(encoding="utf-8"))["primary_resource"] == "widgets"

    def test_resolve_scenario_refuses_when_compilation_is_incomplete(self, tmp_path: pathlib.Path) -> None:
        runner = _module()
        empty_dir = tmp_path / "empty-candidate"
        empty_dir.mkdir()
        resolved = runner._resolve_scenario("golden-work-empty", {}, None)
        assert isinstance(resolved, dict)
        assert resolved["outcome"] == "ACCEPTANCE_PLAN_INCOMPLETE"
        assert resolved["reasons"]

    def test_resolve_scenario_accepts_a_compatible_override(self, tmp_path: pathlib.Path) -> None:
        runner = _module()
        work = tmp_path / "candidate"
        _widget_contract_files(work)
        contract_files = runner._candidate_contract_files(work)
        compiled, _path = runner._resolve_scenario("golden-work-widgets", contract_files, None)

        override_path = tmp_path / "override.json"
        override_path.write_text(compiled.model_dump_json(), encoding="utf-8")
        resolved = runner._resolve_scenario("golden-work-widgets", contract_files, override_path)
        assert not isinstance(resolved, dict)
        scenario, scenario_path = resolved
        assert scenario.primary_resource == "widgets"
        assert scenario_path == override_path

    def test_resolve_scenario_rejects_an_incompatible_override(self, tmp_path: pathlib.Path) -> None:
        runner = _module()
        work = tmp_path / "candidate"
        _widget_contract_files(work)
        contract_files = runner._candidate_contract_files(work)

        override_path = tmp_path / "override.json"
        override_path.write_text(json.dumps({
            "scenario_id": "wrong", "resources": [{
                "name": "widgets", "collection_route": "/widgets", "navigation_label": "Widgets",
                "singular_label": "Widget", "editable_form_fields": ["name", "sku"],
            }],
            "primary_resource": "widgets", "create_payload": {"name": "A", "sku": "X"},
            "update_payload": {"name": "B"}, "navigation_destinations": ["Widgets"],
        }), encoding="utf-8")

        resolved = runner._resolve_scenario("golden-work-widgets", contract_files, override_path)
        assert isinstance(resolved, dict)
        assert resolved["outcome"] == "ACCEPTANCE_SCENARIO_INCOMPATIBLE"
        assert any("sku" in reason for reason in resolved["reasons"])

    def test_main_compiles_and_reaches_a_real_pass_with_no_scenario_flag(
        self, monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
    ) -> None:
        """End-to-end through `main()` itself (not `_accept()` directly):
        no `--scenario` flag at all, a real candidate directory carrying
        only its own real contracts -- the compiled path, not a fixture.
        The contract files must exist BEFORE the STAGED_GENERATION_PASS
        manifest is recorded (`_seed_verified_candidate` records it too
        early for this test's own purpose), so this seeds the ledger
        itself rather than reusing that helper."""
        runner = _module()
        candidate_id = "golden-work-widgetsmain"
        candidates = tmp_path / "candidates"
        work = candidates / candidate_id
        _widget_contract_files(work)
        monkeypatch.setattr(runner, "CANDIDATES", candidates)
        monkeypatch.setattr(runner, "RUNTIMES", tmp_path / "runtime")
        ledger = CandidateLedger(candidates / "_ledger")
        ledger.allocate(candidate_id, provenance=_provenance())
        ledger.record_state(candidate_id, GENERATING, work)
        ledger.record_state(candidate_id, STAGED_GENERATION_PASS, work)

        scenario = runner._compile_acceptance_plan(runner._candidate_contract_files(work))
        _stub_a_full_successful_journey(runner, monkeypatch, scenario=scenario)

        exit_code = runner.main(["run_golden_acceptance.py", "--candidate-id", candidate_id])
        assert exit_code == 0
