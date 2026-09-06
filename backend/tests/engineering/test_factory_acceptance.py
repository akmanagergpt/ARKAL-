from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

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
SCRIPT = REPO / "scripts" / "factory_acceptance.py"
DEFAULT_SCENARIO_PATH = REPO / "golden" / "scenarios" / "student_fee_management.json"


def _module():  # noqa: ANN202
    """A fresh `factory_acceptance` module instance per test -- isolated
    the same way every prior test in this suite already isolated
    `run_golden_acceptance` before the F-00XX extraction split the one
    real acceptance engine (`_accept` and everything it calls) out of the
    CLI script into this importable module, so both the manual `run_
    golden_acceptance.py` CLI and `run_factory_worker.py`'s own real
    production composition call the exact same code, never a duplicate."""
    spec = importlib.util.spec_from_file_location("factory_acceptance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _accept(module, candidate_id: str, source_candidate: pathlib.Path, *, skip_browser: bool = True, scenario_path=None):  # noqa: ANN001, ANN202
    """Defaults to the Student/Fee Golden's own real scenario -- most of
    these tests exercise the engine's real lifecycle/ledger wiring, not
    scenario generality. `TestCoreRunnerIsDomainIndependent` below passes
    a different real scenario_path to prove the exact same engine code
    drives an unrelated domain identically."""
    path = scenario_path or DEFAULT_SCENARIO_PATH
    scenario = module._load_scenario(path)
    return module._accept(candidate_id, source_candidate, scenario, path, skip_browser=skip_browser)


def test_stop_owns_only_the_passed_process(monkeypatch) -> None:  # noqa: ANN001
    module = _module()
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
        module.subprocess, "run",
        lambda command, **kwargs: commands.append(command),
    )
    process = Process()
    module._stop(process)
    if module.os.name == "nt":
        assert commands == [["taskkill", "/PID", "4321", "/T", "/F"]]
        assert not process.terminated
    else:
        assert process.terminated


def test_stopped_check_measures_a_listener_not_windows_bind_reuse(monkeypatch) -> None:  # noqa: ANN001
    module = _module()

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

    import arkali.engineering.candidate.runtime_process as runtime_process

    monkeypatch.setattr(runtime_process.socket, "socket", Socket)
    assert not module._port_accepts_connections(5000)


def test_acceptance_uses_a_clean_copy_and_never_mutates_the_frozen_candidate(
    tmp_path: pathlib.Path,
) -> None:
    module = _module()
    source = tmp_path / "source"
    (source / "frontend" / "node_modules").mkdir(parents=True)
    (source / "frontend" / "build").mkdir()
    (source / "frontend" / "src").mkdir()
    (source / "frontend" / "src" / "App.js").write_text("source", encoding="utf-8")
    (source / "backend.db").write_bytes(b"frozen")
    destination = tmp_path / "runtime-copy"
    module._copy_candidate(source, destination)
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
    module, monkeypatch, tmp_path: pathlib.Path, candidate_id: str,  # noqa: ANN001
) -> tuple[pathlib.Path, CandidateLedger]:
    """A real, isolated CANDIDATES/RUNTIMES root with one candidate whose
    ledger history is ALLOCATED -> GENERATING -> STAGED_GENERATION_PASS
    (the only state acceptance may begin from) and whose live content
    exactly matches the manifest recorded at that state."""
    candidates = tmp_path / "candidates"
    work = candidates / candidate_id
    work.mkdir(parents=True)
    (work / "App.js").write_text("// unmodified", encoding="utf-8")
    monkeypatch.setattr(module, "CANDIDATES", candidates)
    monkeypatch.setattr(module, "RUNTIMES", tmp_path / "runtime")

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


def _stub_a_full_successful_journey(module, monkeypatch, scenario=None) -> None:  # noqa: ANN001
    """Replaces every real subprocess/network/browser step `_accept`
    takes with a fast, deterministic double -- proves the ledger/outcome
    wiring end-to-end without a real npm, flask, or Chromium install.
    Route matching is derived from `scenario` itself (default: the
    Student/Fee Golden's own real scenario) -- never hardcoded to one
    domain's routes, so the same stub serves every domain's own tests."""
    if scenario is None:
        scenario = module._load_scenario(DEFAULT_SCENARIO_PATH)
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

    monkeypatch.setattr(module, "_run", fake_run)
    monkeypatch.setattr(module, "_json_request", fake_json_request)
    monkeypatch.setattr(module, "_wait_http", lambda *a, **k: None)
    monkeypatch.setattr(module, "_port_is_free", lambda port: True)
    monkeypatch.setattr(module, "_port_accepts_connections", lambda port: False)
    monkeypatch.setattr(module, "_backend_process", lambda *a, **k: _FakeProcess())
    monkeypatch.setattr(module.subprocess, "Popen", lambda *a, **k: _FakeProcess())
    # `_stop`'s real Windows path shells out to `taskkill` via the (now
    # patched) `subprocess.Popen`; these tests aren't exercising `_stop`
    # itself (that's `test_stop_owns_only_the_passed_process`'s job), so
    # make it a no-op rather than fighting the patched Popen through it.
    monkeypatch.setattr(module, "_stop", lambda process: None)


def test_1_staged_generation_pass_through_acceptance_running_to_accepted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    module = _module()
    candidate_id = "golden-work-pass"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
    _stub_a_full_successful_journey(module, monkeypatch)

    result = _accept(module, candidate_id, source)

    assert result["outcome"] == "GOLDEN_ACCEPTANCE_PASS"
    states = [entry["state"] for entry in ledger.history(candidate_id)]
    assert states == [
        "ALLOCATED", "GENERATING", "STAGED_GENERATION_PASS", "ACCEPTANCE_RUNNING", "ACCEPTED",
    ]
    assert ledger.classify(candidate_id) == ACCEPTED


def test_1b_a_real_production_factory_candidate_reaches_accepted_the_same_way(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """The exact same `_accept()` orchestration -- ledger transitions,
    scenario-driven checks, evidence -- for a `factory-<job_id>` candidate
    identity, never a second acceptance path or a renamed/aliased id. No
    `_candidate()` call happens inside `_accept()` at all any more: the
    caller (here, standing in for `run_factory_worker.py`'s own already-
    resolved `workspace.root`) passes `source` directly."""
    module = _module()
    candidate_id = "factory-goal-mtpnp9af-yeldck"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
    _stub_a_full_successful_journey(module, monkeypatch)

    result = _accept(module, candidate_id, source)

    assert result["outcome"] == "GOLDEN_ACCEPTANCE_PASS"
    assert result["candidate_id"] == candidate_id
    states = [entry["state"] for entry in ledger.history(candidate_id)]
    assert states == [
        "ALLOCATED", "GENERATING", "STAGED_GENERATION_PASS", "ACCEPTANCE_RUNNING", "ACCEPTED",
    ]
    assert ledger.classify(candidate_id) == ACCEPTED


def test_2_staged_generation_pass_through_acceptance_running_to_acceptance_failed(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    module = _module()
    candidate_id = "golden-work-checkfail"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
    monkeypatch.setattr(module, "_port_is_free", lambda port: False)  # the very first check fails

    result = _accept(module, candidate_id, source)

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
    module = _module()
    candidates = tmp_path / "candidates"
    candidate_id = "golden-work-stagefailed"
    work = candidates / candidate_id
    work.mkdir(parents=True)
    (work / "App.js").write_text("// incomplete", encoding="utf-8")
    monkeypatch.setattr(module, "CANDIDATES", candidates)
    monkeypatch.setattr(module, "RUNTIMES", tmp_path / "runtime")
    ledger = CandidateLedger(candidates / "_ledger")
    ledger.allocate(candidate_id, provenance=_provenance())
    ledger.record_state(candidate_id, GENERATING, work)
    ledger.record_state(candidate_id, STAGE_FAILED, work)

    copied: list[object] = []
    monkeypatch.setattr(module, "_copy_candidate", lambda *a, **k: copied.append(a))

    result = _accept(module, candidate_id, work)
    assert result["outcome"] == "CANDIDATE_INTEGRITY_FAILED"
    assert STAGE_FAILED in result["error"]
    assert copied == []
    assert ledger.classify(candidate_id) == STAGE_FAILED  # unchanged -- no transition recorded


def test_4_a_legacy_unverified_candidate_cannot_be_accepted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """A candidate this ledger has no history for at all (never allocated
    through it) must refuse before acceptance ever copies or touches it."""
    module = _module()
    candidates = tmp_path / "candidates"
    candidate_id = "golden-work-nohistory"
    work = candidates / candidate_id
    work.mkdir(parents=True)
    (work / "App.js").write_text("// no ledger history", encoding="utf-8")
    monkeypatch.setattr(module, "CANDIDATES", candidates)
    monkeypatch.setattr(module, "RUNTIMES", tmp_path / "runtime")

    copied: list[object] = []
    monkeypatch.setattr(module, "_copy_candidate", lambda *a, **k: copied.append(a))

    result = _accept(module, candidate_id, work)
    assert result["outcome"] == "CANDIDATE_INTEGRITY_FAILED"
    assert copied == []


def test_5_a_candidate_whose_manifest_was_modified_cannot_be_accepted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    module = _module()
    candidate_id = "golden-work-tampered"
    work, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)

    (work / "App.js").write_text("// tampered after the terminal state", encoding="utf-8")
    copied: list[object] = []
    monkeypatch.setattr(module, "_copy_candidate", lambda *a, **k: copied.append(a))

    result = _accept(module, candidate_id, work)
    assert result["outcome"] == "CANDIDATE_INTEGRITY_FAILED"
    assert "changed=" in result["error"]
    assert copied == []


def test_6_a_second_concurrent_acceptance_attempt_is_refused(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    module = _module()
    candidate_id = "golden-work-concurrent"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)

    # Simulate a first attempt already holding the lock.
    lock_path = (module.CANDIDATES / "_ledger") / f"{candidate_id}.acceptance.lock"
    fd = module.os.open(str(lock_path), module.os.O_CREAT | module.os.O_EXCL | module.os.O_WRONLY)
    module.os.close(fd)

    copied: list[object] = []
    monkeypatch.setattr(module, "_copy_candidate", lambda *a, **k: copied.append(a))

    result = _accept(module, candidate_id, source)
    assert result["outcome"] == "ACCEPTANCE_ALREADY_IN_PROGRESS"
    assert copied == []
    assert ledger.classify(candidate_id) == STAGED_GENERATION_PASS  # untouched


def test_7_a_crash_during_acceptance_is_recorded_as_interrupted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """A crash that is NOT a classified named-check failure -- here, the
    venv-creation step itself blowing up -- is genuinely ambiguous, not a
    verdict any check reached."""
    module = _module()
    candidate_id = "golden-work-crash"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
    monkeypatch.setattr(module, "_port_is_free", lambda port: True)

    def boom(*a, **k):  # noqa: ANN001, ANN202
        raise RuntimeError("venv creation exploded")

    monkeypatch.setattr(module, "_run", boom)

    result = _accept(module, candidate_id, source)
    assert result["outcome"] == "ACCEPTANCE_INTERRUPTED"
    assert ledger.classify(candidate_id) == INTERRUPTED


def test_7_a_keyboard_interrupt_during_acceptance_is_recorded_as_interrupted(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    module = _module()
    candidate_id = "golden-work-ctrlc"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
    monkeypatch.setattr(module, "_port_is_free", lambda port: True)

    def interrupted(*a, **k):  # noqa: ANN001, ANN202
        raise KeyboardInterrupt

    monkeypatch.setattr(module, "_run", interrupted)

    with pytest.raises(KeyboardInterrupt):
        _accept(module, candidate_id, source)
    # Ctrl+C still propagates (the process really stops), but the ledger
    # and evidence were written first -- never a silently unrecorded gap.
    assert ledger.classify(candidate_id) == INTERRUPTED


def test_8_an_accepted_candidate_cannot_be_re_run(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    module = _module()
    candidate_id = "golden-work-noreplay"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
    _stub_a_full_successful_journey(module, monkeypatch)

    first = _accept(module, candidate_id, source)
    assert first["outcome"] == "GOLDEN_ACCEPTANCE_PASS"

    copied: list[object] = []
    monkeypatch.setattr(module, "_copy_candidate", lambda *a, **k: copied.append(a))
    # `runtime` is named from `int(time.time())`; force a distinct second
    # so the two real, back-to-back calls don't collide on one directory.
    real_time = module.time.time
    monkeypatch.setattr(module.time, "time", lambda: real_time() + 1)
    second = _accept(module, candidate_id, source)
    assert second["outcome"] == "CANDIDATE_INTEGRITY_FAILED"
    assert "ACCEPTED" in second["error"]
    assert copied == []


def test_9_acceptance_evidence_dir_and_result_hash_are_recorded_in_the_ledger(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    module = _module()
    candidate_id = "golden-work-evidence"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
    _stub_a_full_successful_journey(module, monkeypatch)

    result = _accept(module, candidate_id, source)
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
    module = _module()
    candidate_id = "golden-work-untouched"
    source, ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
    before = file_manifest(source)
    _stub_a_full_successful_journey(module, monkeypatch)

    _accept(module, candidate_id, source)

    after = file_manifest(source)
    assert before == after


def test_run_kills_its_owned_process_tree_on_timeout(monkeypatch, tmp_path) -> None:  # noqa: ANN001
    module = _module()
    stopped: list[object] = []

    class Process:
        returncode = None

        def communicate(self, timeout: float):  # noqa: ANN202
            assert timeout == 7
            raise module.subprocess.TimeoutExpired(["stuck"], timeout, output="partial")

    process = Process()
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(module, "_stop", lambda owned: stopped.append(owned))
    with pytest.raises(RuntimeError, match="timed out after 7s.*stuck"):
        module._run(["stuck"], cwd=tmp_path, timeout_seconds=7)
    assert stopped == [process]


def test_browser_journey_receives_the_real_persisted_primary_id_and_scenario() -> None:
    """ARK-REQ-0074: the engine passes the real scenario file through to
    the browser journey rather than naming a resource of its own."""
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"--scenario", str(scenario_path)' in source
    assert '"--primary-id", str(primary_id)' in source


def test_frontend_install_has_a_finite_timeout() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '_run([npm, "install"], cwd=frontend_dir, timeout_seconds=600)' in source


class TestCoreRunnerIsDomainIndependent:
    """ARK-REQ-0074 ("Golden domain logic must not enter ARKALI core"):
    the exact same `_accept()` code, unchanged, drives an inventory
    product and a task/reservation product exactly as it drives the
    Student/Fee Golden -- every resource, route, and payload comes from
    the real scenario file, never from the engine itself."""

    def _run_scenario(self, monkeypatch, tmp_path: pathlib.Path, scenario_name: str):  # noqa: ANN001, ANN202
        module = _module()
        scenario_path = REPO / "golden" / "scenarios" / f"{scenario_name}.json"
        candidate_id = f"golden-work-{scenario_name.replace('_', '')}"
        source, _ledger = _seed_verified_candidate(module, monkeypatch, tmp_path, candidate_id)
        scenario = module._load_scenario(scenario_path)
        _stub_a_full_successful_journey(module, monkeypatch, scenario=scenario)
        result = _accept(module, candidate_id, source, scenario_path=scenario_path)
        return module, scenario, result

    def test_inventory_management_scenario_reaches_a_real_pass(
        self, monkeypatch, tmp_path: pathlib.Path,
    ) -> None:
        _module_, scenario, result = self._run_scenario(monkeypatch, tmp_path, "inventory_management")
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
        _module_, scenario, result = self._run_scenario(monkeypatch, tmp_path, "task_management")
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
            _module_, scenario, result = self._run_scenario(monkeypatch, tmp_path, scenario_name)
            assert result["outcome"] == "GOLDEN_ACCEPTANCE_PASS"
            generic_kinds = {
                name.replace(scenario.primary_resource, "PRIMARY").replace(
                    scenario.related_resource or "\0", "RELATED",
                )
                for name in (c["name"] for c in result["checks"])
            }
            shapes.append(generic_kinds)
        assert shapes[0] == shapes[1] == shapes[2]


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
    """`_resolve_scenario` compiles a real scenario by default (ARK-REQ-0074
    Part A: ARKALI cannot ask an operator to hand-author one per generated
    product), and only ever trusts an explicit override after it reconciles
    against the SAME candidate's own real contracts."""

    def test_resolve_scenario_compiles_by_default(self, tmp_path: pathlib.Path) -> None:
        module = _module()
        work = tmp_path / "candidate"
        _widget_contract_files(work)
        contract_files = module._candidate_contract_files(work)

        resolved = module._resolve_scenario("golden-work-widgets", contract_files, None)
        assert not isinstance(resolved, dict)
        scenario, scenario_path = resolved
        assert scenario.primary_resource == "widgets"
        assert scenario_path.is_file()
        assert json.loads(scenario_path.read_text(encoding="utf-8"))["primary_resource"] == "widgets"

    def test_resolve_scenario_refuses_when_compilation_is_incomplete(self, tmp_path: pathlib.Path) -> None:
        module = _module()
        resolved = module._resolve_scenario("golden-work-empty", {}, None)
        assert isinstance(resolved, dict)
        assert resolved["outcome"] == "ACCEPTANCE_PLAN_INCOMPLETE"
        assert resolved["reasons"]

    def test_resolve_scenario_accepts_a_compatible_override(self, tmp_path: pathlib.Path) -> None:
        module = _module()
        work = tmp_path / "candidate"
        _widget_contract_files(work)
        contract_files = module._candidate_contract_files(work)
        compiled, _path = module._resolve_scenario("golden-work-widgets", contract_files, None)

        override_path = tmp_path / "override.json"
        override_path.write_text(compiled.model_dump_json(), encoding="utf-8")
        resolved = module._resolve_scenario("golden-work-widgets", contract_files, override_path)
        assert not isinstance(resolved, dict)
        scenario, scenario_path = resolved
        assert scenario.primary_resource == "widgets"
        assert scenario_path == override_path

    def test_resolve_scenario_rejects_an_incompatible_override(self, tmp_path: pathlib.Path) -> None:
        module = _module()
        work = tmp_path / "candidate"
        _widget_contract_files(work)
        contract_files = module._candidate_contract_files(work)

        override_path = tmp_path / "override.json"
        override_path.write_text(json.dumps({
            "scenario_id": "wrong", "resources": [{
                "name": "widgets", "collection_route": "/widgets", "navigation_label": "Widgets",
                "singular_label": "Widget", "editable_form_fields": ["name", "sku"],
            }],
            "primary_resource": "widgets", "create_payload": {"name": "A", "sku": "X"},
            "update_payload": {"name": "B"}, "navigation_destinations": ["Widgets"],
        }), encoding="utf-8")

        resolved = module._resolve_scenario("golden-work-widgets", contract_files, override_path)
        assert isinstance(resolved, dict)
        assert resolved["outcome"] == "ACCEPTANCE_SCENARIO_INCOMPATIBLE"
        assert any("sku" in reason for reason in resolved["reasons"])
