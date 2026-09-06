"""Production Factory -> canonical acceptance bridge. Real proof that
`scripts/run_factory_worker.py` -- the actual production Factory worker --
calls the exact same generic acceptance engine (`scripts/
factory_acceptance.py`'s `_accept`) the manual `run_golden_acceptance.py`
CLI already used, automatically, once a real candidate reaches its own real
`STAGED_GENERATION_PASS`. Never a second acceptance engine, never a
job-level state change: `main()` itself is not exercised here (it requires
a real Ollama endpoint and durable job store, exactly the reason
`test_run_factory_worker_observability.py` tests this same script's own
composition wiring directly rather than through `main()`), but the new
`_run_production_acceptance` composition function is proven directly with
every real subprocess/network call stubbed.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "run_factory_worker.py"


def _module():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("run_factory_worker", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_worker_imports_the_shared_acceptance_engine_not_a_copy() -> None:
    """REUSE, never CREATE: the worker must import `_accept`/`_resolve_
    scenario`/`_candidate_contract_files` from the one real
    `factory_acceptance` module, never reimplement or duplicate any of
    the acceptance orchestration itself."""
    module = _module()
    import factory_acceptance

    assert module._run_acceptance is factory_acceptance._accept
    assert module._resolve_scenario is factory_acceptance._resolve_scenario
    assert module._candidate_contract_files is factory_acceptance._candidate_contract_files


def test_production_acceptance_calls_the_shared_engine_with_the_real_workspace_root(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """`_run_production_acceptance` never re-resolves a candidate id string
    through any `_candidate()`-style identity gate -- it passes the
    worker's own already-real, already-trusted `workspace_root` straight
    through to `_accept`, exactly as a production candidate (never
    `golden-work-*`-shaped) requires."""
    module = _module()
    calls: dict[str, object] = {}
    sentinel_scenario = object()
    sentinel_path = tmp_path / "scenario.json"

    def fake_resolve(candidate_id, contract_files, override):  # noqa: ANN001, ANN202
        calls["resolve"] = (candidate_id, contract_files, override)
        return sentinel_scenario, sentinel_path

    def fake_accept(candidate_id, source_candidate, scenario, scenario_path, **kwargs):  # noqa: ANN001, ANN202
        calls["accept"] = (candidate_id, source_candidate, scenario, scenario_path, kwargs)
        return {"outcome": "GOLDEN_ACCEPTANCE_PASS", "candidate_id": candidate_id}

    monkeypatch.setattr(module, "_candidate_contract_files", lambda root: {"product/ux_spec.json": "{}"})
    monkeypatch.setattr(module, "_resolve_scenario", fake_resolve)
    monkeypatch.setattr(module, "_run_acceptance", fake_accept)

    workspace_root = tmp_path / "workspace"
    result = module._run_production_acceptance("factory-goal-x", workspace_root)

    assert result == {"outcome": "GOLDEN_ACCEPTANCE_PASS", "candidate_id": "factory-goal-x"}
    assert calls["resolve"] == ("factory-goal-x", {"product/ux_spec.json": "{}"}, None)
    assert calls["accept"][:4] == ("factory-goal-x", workspace_root, sentinel_scenario, sentinel_path)


def test_a_terminal_unaccepted_scenario_resolution_is_returned_unchanged(
    monkeypatch, tmp_path: pathlib.Path,  # noqa: ANN001
) -> None:
    """A real, disclosed, terminal `ACCEPTANCE_PLAN_INCOMPLETE` (or any
    other terminal dict `_resolve_scenario` itself returns) is passed
    straight through -- this bridge invents no new outcome vocabulary and
    never calls `_accept` at all when no real scenario was compiled."""
    module = _module()
    incomplete = {
        "outcome": "ACCEPTANCE_PLAN_INCOMPLETE", "candidate_id": "factory-goal-x",
        "error": "...", "reasons": ["..."], "checks": [],
    }
    monkeypatch.setattr(module, "_candidate_contract_files", lambda root: {})
    monkeypatch.setattr(module, "_resolve_scenario", lambda *a, **k: incomplete)

    def fail_if_called(*a, **k):  # noqa: ANN001, ANN202
        raise AssertionError("_accept must not be called when scenario resolution is terminal")

    monkeypatch.setattr(module, "_run_acceptance", fail_if_called)

    result = module._run_production_acceptance("factory-goal-x", tmp_path)
    assert result == incomplete


def test_generation_still_succeeds_even_if_the_acceptance_bridge_itself_crashes() -> None:
    """A bug inside the acceptance bridge must never be allowed to turn a
    real, already-recorded `STAGED_GENERATION_PASS` into a crashed worker
    or a lost job -- confirmed at the source level: the call site in
    `main()` is wrapped so any exception becomes a reported
    `ACCEPTANCE_BRIDGE_ERROR` outcome, never a propagated crash past the
    already-durable `STAGED_GENERATION_PASS` transition."""
    source = SCRIPT.read_text(encoding="utf-8")
    block = source[
        source.index("ledger.record_state(candidate_id, STAGED_GENERATION_PASS, workspace.root)"):
        source.index("_finish_job(JOB_SUCCEEDED, {")
    ]
    assert "try:" in block
    assert "_run_production_acceptance(candidate_id, workspace.root)" in block
    assert "ACCEPTANCE_BRIDGE_ERROR" in block


def test_job_success_is_never_redefined_by_acceptance_outcome() -> None:
    """`JobStore`'s own `SUCCEEDED` means exactly "generation completed" --
    preserved unconditionally regardless of whatever the acceptance bridge
    returns, since candidate acceptance is `CandidateLedger`'s own,
    separate, later lifecycle stage (never a second job-level truth)."""
    source = SCRIPT.read_text(encoding="utf-8")
    block = source[
        source.index("ledger.record_state(candidate_id, STAGED_GENERATION_PASS, workspace.root)"):
        source.index('print(json.dumps({\n        "outcome": "STAGED_GENERATION_PASS"')
    ]
    assert "_finish_job(JOB_SUCCEEDED, {" in block
    assert "\"acceptance\": acceptance," in block
