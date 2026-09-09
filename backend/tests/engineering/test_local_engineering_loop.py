"""D-037 targeted controls plus the trusted, non-executing live acceptance test.

The acceptance node parses the proposed Python; it never imports model code.
All other tests use synthetic source and a counted local-adapter double.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def loop():
    path = Path(__file__).resolve().parents[3] / "scripts/run_local_engineering_task.py"
    spec = importlib.util.spec_from_file_location("local_loop", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def prepared(loop, monkeypatch, tmp_path):
    source = b'def describe():\n    """Old description."""\n    return 1\n'
    monkeypatch.setattr(loop, "_source", lambda root, path: source)
    seed = tmp_path / "seed"
    seed.mkdir()
    workspace = loop.WorkspaceAuthority(tmp_path / "work").allocate(
        workspace_id="bounded", task_id="bounded", agent_id="test", stable_snapshot=seed)
    task, package, prompt, sources = loop.compile_task(
        loop.ROOT, "bounded", "Improve the function documentation", ["sample.py"], "trusted-test", workspace.root)
    workspace.write("snapshot/sample.py", source)
    return task, package, prompt, sources, workspace


def _model(content, *, runtime="ollama", state="PASS"):
    plan = {"request_text": "Improve documentation", "target_summary": "Description",
            "operations": [{"operation": "update", "path": "sample.py", "content": content,
                            "rationale": "Requested documentation"}]}
    model = SimpleNamespace(runtime=runtime, model_id="sample-model", calls=0, timeout=None)
    def infer(model_id, prompt, *, timeout_seconds):
        model.calls += 1
        model.timeout = timeout_seconds
        return SimpleNamespace(state=SimpleNamespace(value=state), detail="bounded failure",
                               output=json.dumps(plan), elapsed_seconds=0.125)
    model.infer = infer
    return model


def test_context_binds_exact_source_and_provenance(loop, prepared):
    task, package, prompt, sources, workspace = prepared
    assert task.context_package == package.context_hash
    assert task.repair_budget == 0 and task.tools == task.permissions == ()
    assert task.workspace == str(workspace.root)
    assert loop._digest(sources["sample.py"]) in package.items[0].origin
    assert sources["sample.py"].decode() in json.loads(prompt.split("AUTHORITATIVE CURRENT SOURCE:\n")[1]).values()
    assert len(prompt.encode()) <= loop.MAX_CONTEXT_BYTES


def test_context_deterministic_and_source_change_changes_hash(loop, monkeypatch, prepared):
    args = (loop.ROOT, "same", "Document", ["z.py", "a.py"], "test", prepared[-1].root)
    first = loop.compile_task(*args)
    second = loop.compile_task(*args)
    assert first[1].context_hash == second[1].context_hash
    assert list(first[3]) == ["a.py", "z.py"]
    monkeypatch.setattr(loop, "_source", lambda *a: b"different source")
    assert loop.compile_task(*args)[1].context_hash != first[1].context_hash


def test_file_and_byte_limits_refuse(loop, prepared, monkeypatch):
    with pytest.raises(ValueError, match="file-count"):
        loop.compile_task(loop.ROOT, "x", "x", [f"f{i}.py" for i in range(6)], "test", prepared[-1].root)
    monkeypatch.setattr(loop, "_source", lambda *a: b"x" * loop.MAX_CONTEXT_BYTES)
    with pytest.raises(ValueError, match="byte budget"):
        loop.compile_task(loop.ROOT, "x", "x", ["x.py"], "test", prepared[-1].root)


def test_request_secrets_scrubbed(loop, prepared):
    secret = "sk-" + "a" * 24
    task, package, prompt, _ = loop.compile_task(loop.ROOT, "x", "Document " + secret,
                                                ["sample.py"], "test", prepared[-1].root)
    assert secret not in prompt and "[REDACTED-SECRET]" in task.task_specification


@pytest.mark.parametrize("path", [".env", "private.key", "../outside.py", ".hidden/config.py"])
def test_sensitive_paths_refuse_before_read(loop, path):
    with pytest.raises(ValueError):
        loop._source(loop.ROOT, path)


def test_editable_secret_source_refused(loop, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "source.py").write_text('value = "sk-' + 'a' * 24 + '"')
    subprocess.run(["git", "add", "source.py"], cwd=tmp_path, check=True)
    with pytest.raises(ValueError, match="secret material"):
        loop._source(tmp_path, "source.py")


def test_single_success_is_isolated_verified_unpromoted(loop, prepared):
    model = _model('def describe():\n    """Clear description."""\n    return 1\n')
    base = prepared[3]["sample.py"]
    result = loop.execute_once(*prepared, model, lambda: {"passed": True})
    assert result["verification_passed"] and result["promotion"] == "NOT_PROMOTED"
    assert model.calls == 1 and 0 < model.timeout < float("inf")
    assert result["automatic_retries"] == result["external_execution_calls"] == 0
    assert prepared[3]["sample.py"] == base
    assert (prepared[-1].snapshot / "sample.py").read_bytes() != base


@pytest.mark.parametrize("content,acceptance", [("broken python!", True), ("x = 1\n", False)])
def test_verification_failure_has_no_retry_or_promotion(loop, prepared, content, acceptance):
    model = _model(content)
    result = loop.execute_once(*prepared, model, lambda: {"passed": acceptance})
    assert not result["verification_passed"] and model.calls == 1
    assert result["promotion"] == "NOT_PROMOTED" and result["automatic_retries"] == 0


def test_provider_failure_does_not_mutate(loop, prepared):
    model = _model("x = 1", state="FAIL")
    with pytest.raises(ValueError, match="inference failed"):
        loop.execute_once(*prepared, model, lambda: {"passed": True})
    assert model.calls == 1
    assert (prepared[-1].snapshot / "sample.py").read_bytes() == prepared[3]["sample.py"]


def test_external_provider_refused(loop, prepared):
    model = _model("x = 1", runtime="external")
    with pytest.raises(ValueError, match="local execution"):
        loop.execute_once(*prepared, model, lambda: {"passed": True})
    assert model.calls == 0


def test_local_selector_prefers_smallest_for_low_and_warm_for_medium():
    from arkali.engineering.localai.adapter import LocalModelDescriptor
    from arkali.engineering.localai.suitability import LocalSelectionRequest, select_local_model
    descriptors = (
        LocalModelDescriptor(runtime="ollama", model_id="large", parameter_size="14B"),
        LocalModelDescriptor(runtime="ollama", model_id="small", parameter_size="7B"),
    )
    low = select_local_model(descriptors, LocalSelectionRequest(complexity="low"))
    medium = select_local_model(descriptors, LocalSelectionRequest(complexity="medium", warm_model_id="large"))
    high = select_local_model(descriptors, LocalSelectionRequest(complexity="high"))
    assert low.model_id == "small" and low.switch_required is False
    assert medium.model_id == "large" and medium.switch_required is False
    assert high.model_id == "large"


def test_local_selector_never_selects_unavailable_empty_set():
    from arkali.engineering.localai.suitability import LocalSelectionRequest, select_local_model
    with pytest.raises(ValueError, match="no suitable local model"):
        select_local_model((), LocalSelectionRequest(complexity="low"))


@pytest.mark.parametrize("operation,path", [("create", "extra.py"), ("update", "unseen.py"),
                                           ("delete", "sample.py"), ("rename", "sample.py")])
def test_out_of_scope_plan_refused_without_mutation(loop, prepared, operation, path):
    model = _model("x = 1")
    original = model.infer
    def infer(*args, **kwargs):
        result = original(*args, **kwargs)
        payload = json.loads(result.output)
        payload["operations"][0].update(operation=operation, path=path)
        result.output = json.dumps(payload)
        return result
    model.infer = infer
    with pytest.raises(ValueError, match="scope"):
        loop.execute_once(*prepared, model, lambda: {"passed": True})
    assert model.calls == 1
    assert list(prepared[-1].snapshot.iterdir()) == [prepared[-1].snapshot / "sample.py"]
    assert (prepared[-1].snapshot / "sample.py").read_bytes() == prepared[3]["sample.py"]


def test_wrong_context_and_stale_base_refused(loop, prepared):
    model = _model("x = 1")
    task, package, prompt, source, workspace = prepared
    with pytest.raises(ValueError, match="binding"):
        loop.execute_once(task.model_copy(update={"context_package": "wrong"}), package,
                          prompt, source, workspace, model, lambda: {"passed": True})
    assert model.calls == 0
    workspace.write("snapshot/sample.py", b"changed")
    with pytest.raises(ValueError, match="stale"):
        loop.execute_once(*prepared, model, lambda: {"passed": True})
    assert (workspace.snapshot / "sample.py").read_bytes() == b"changed"


def test_live_slug_documentation_acceptance():
    """Trusted demonstration criteria, never a production special case."""
    location = os.environ.get("ARKALI_REVIEW_WORKSPACE")
    if not location:
        pytest.skip("only runs on the real isolated proposal")
    root = Path(location)
    path = "backend/arkali/engineering/agent/context_kinds.py"
    before = ast.parse((root / "baseline" / path).read_text(encoding="utf-8"))
    after = ast.parse((root / "snapshot" / path).read_text(encoding="utf-8"))
    old = next(n for n in before.body if isinstance(n, ast.FunctionDef) and n.name == "slug")
    new = next(n for n in after.body if isinstance(n, ast.FunctionDef) and n.name == "slug")
    documentation = ast.get_docstring(new)
    assert documentation != ast.get_docstring(old)
    assert "lowercase" in documentation.lower()
    assert "underscore" in documentation.lower()
    assert "empty" in documentation.lower()
    # Only this docstring may differ; model code is never executed.
    new.body[0] = old.body[0]
    assert ast.dump(before, include_attributes=False) == ast.dump(after, include_attributes=False)
