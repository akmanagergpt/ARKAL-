from __future__ import annotations

import importlib.util
import pathlib
import sys
import threading
import urllib.request

import pytest

from arkali.engineering.candidate.ledger import (
    CandidateLedger,
    GENERATING,
    GenerationProvenance,
    hash_text,
    STAGED_GENERATION_PASS,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "run_golden_acceptance.py"


def _module():  # noqa: ANN202
    """The thin CLI wrapper only -- `_candidate()`'s own golden-work-*/
    factory-* identity gate and `main()`'s argparse/orchestration. The
    real, generic acceptance engine (`_accept` and everything it calls)
    lives in `scripts/factory_acceptance.py` and is exercised by
    `test_factory_acceptance.py`; this script's own `sys.path.insert` +
    `from factory_acceptance import ...` resolves that module by a real
    import when this loads, exactly as it does for a real invocation."""
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


def test_candidate_path_accepts_a_real_production_factory_id(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """`scripts/run_factory_worker.py`'s own real candidate identity shape
    (`candidate_id = f"factory-{job_id}"`) resolves through the exact same
    `_candidate()` identity gate as `golden-work-*` -- both are real
    directories under the exact same `CANDIDATES` root."""
    runner = _module()
    candidates = tmp_path / "candidates"
    candidate_id = "factory-goal-mtpnp9af-yeldck"
    (candidates / candidate_id).mkdir(parents=True)
    monkeypatch.setattr(runner, "CANDIDATES", candidates)

    resolved = runner._candidate(candidate_id)

    assert resolved == (candidates / candidate_id).resolve()


def test_candidate_path_rejects_a_missing_factory_candidate() -> None:
    runner = _module()
    with pytest.raises(ValueError, match="does not exist"):
        runner._candidate("factory-goal-doesnotexist")


def test_candidate_path_still_rejects_a_shape_that_is_neither_prefix() -> None:
    runner = _module()
    with pytest.raises(ValueError, match="golden-work-\\* or factory-\\*"):
        runner._candidate("unrelated-work-001")


def _provenance() -> GenerationProvenance:
    return GenerationProvenance(
        goal_hash=hash_text("goal"), source_commit="abc", runtime="ollama",
        endpoint="local", model="qwen",
    )


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
        lambda candidate_id, source_candidate, scenario, scenario_path, skip_browser: {
            "outcome": "GOLDEN_ACCEPTANCE_PASS", "candidate_id": candidate_id,
        },
    )
    assert runner.main(["runner", "--candidate-id", "golden-work-090", "--skip-browser"]) == 2
    assert "GOLDEN_ACCEPTANCE_INCOMPLETE" in capsys.readouterr().out


def test_main_compiles_and_reaches_a_real_pass_with_no_scenario_flag(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """End-to-end through `main()` itself (not `_accept()` directly):
    no `--scenario` flag at all, a real candidate directory carrying
    only its own real contracts -- the compiled path, not a fixture.
    Every real subprocess/network/browser step `_accept` itself takes is
    stubbed on the SAME `factory_acceptance` module instance `main()`'s
    own `from factory_acceptance import _accept` already bound, proving
    the CLI wrapper and the generic engine are wired together correctly,
    not just independently correct."""
    runner = _module()
    acceptance = sys.modules["factory_acceptance"]
    candidate_id = "golden-work-widgetsmain"
    candidates = tmp_path / "candidates"
    work = candidates / candidate_id
    (work / "product").mkdir(parents=True)
    (work / "backend").mkdir(parents=True)
    (work / "product" / "ux_spec.json").write_text(
        '{"product_title": "Widgets", "primary_roles": ["Operator"], "modules": '
        '[{"name": "widgets", "navigation_label": "Widgets", "presentation": "table", '
        '"actions": ["create", "edit", "delete"], "forms": [{"name": "WidgetForm", '
        '"fields": ["id", "name", "price"]}]}], "navigation_destinations": ["Widgets"], '
        '"design_system": {"typography_scale": ["14px"], "spacing_scale": ["4px"], '
        '"component_conventions": ["primary buttons are filled"]}}',
        encoding="utf-8",
    )
    (work / "backend" / "routes.json").write_text(
        '[{"path": "/widgets", "method": "GET"}, {"path": "/widgets", "method": "POST"}, '
        '{"path": "/widgets/{id}", "method": "PUT"}, {"path": "/widgets/{id}", "method": "DELETE"}]',
        encoding="utf-8",
    )
    (work / "backend" / "data_model.json").write_text(
        '{"fields": {"widgets": {"id": "integer", "name": "string", "price": "float"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(runner, "CANDIDATES", candidates)
    monkeypatch.setattr(acceptance, "CANDIDATES", candidates)
    monkeypatch.setattr(acceptance, "RUNTIMES", tmp_path / "runtime")
    ledger = CandidateLedger(candidates / "_ledger")
    ledger.allocate(candidate_id, provenance=_provenance())
    ledger.record_state(candidate_id, GENERATING, work)
    ledger.record_state(candidate_id, STAGED_GENERATION_PASS, work)

    scenario, _path = runner._resolve_scenario(
        candidate_id, runner._candidate_contract_files(work), None,
    )
    primary = scenario.resource(scenario.primary_resource)

    class _FakeProcess:
        pid = 999999

        def poll(self):  # noqa: ANN201
            return None

        def terminate(self) -> None:
            return None

        def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002
            return 0

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
        raise AssertionError(f"unexpected request {method} {url}")

    monkeypatch.setattr(acceptance, "_run", fake_run)
    monkeypatch.setattr(acceptance, "_json_request", fake_json_request)
    monkeypatch.setattr(acceptance, "_wait_http", lambda *a, **k: None)
    monkeypatch.setattr(acceptance, "_port_is_free", lambda port: True)
    monkeypatch.setattr(acceptance, "_port_accepts_connections", lambda port: False)
    monkeypatch.setattr(acceptance, "_backend_process", lambda *a, **k: _FakeProcess())
    monkeypatch.setattr(acceptance.subprocess, "Popen", lambda *a, **k: _FakeProcess())
    monkeypatch.setattr(acceptance, "_stop", lambda process: None)

    exit_code = runner.main(["run_golden_acceptance.py", "--candidate-id", candidate_id])
    assert exit_code == 0
    assert ledger.classify(candidate_id) == "ACCEPTED"


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


def test_browser_journey_accepts_native_confirmation_dialogs() -> None:
    """golden-work-127 (real evidence, frozen): a real, valid, idiomatic
    candidate frontend gated its destructive confirmation behind a native
    `window.confirm()` rather than a custom in-page control. Playwright
    auto-dismisses any dialog with no registered handler, so the real
    DELETE request this candidate's own code would otherwise have sent
    never fired -- reproduced live, and confirmed fixed live (a real
    Playwright page with the identical `if (window.confirm(...)) {...}`
    shape: the delete branch never runs with no handler registered, and
    always runs once `page.on('dialog', ...)` accepts it). Not a candidate
    defect: the journey must accept a dialog exactly as a real user would."""
    browser = (REPO / "scripts" / "run_golden_browser_journey.mjs").read_text(encoding="utf-8")
    assert "page.on('dialog'" in browser
    assert "dialog.accept()" in browser


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
