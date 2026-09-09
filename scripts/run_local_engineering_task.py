"""D-037: one local task, existing contracts/owners, no retry or promotion.

Composition belongs here like run_product_change_worker, not in C-22/C-23.
Source and acceptance tests are explicitly selected by the human caller.
Only existing file updates are admitted in Phase 1. The model receives text,
never tools, and only trusted acceptance tests execute (not model commands).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.secret_reference import assert_no_raw_secret, redact_raw_secrets
from arkali.engineering.agent.context_kinds import ContextKindAuthority
from arkali.engineering.agent.context_package import ContextItem, ContextPackage
from arkali.engineering.agent.harness_task import HarnessTask
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.factory.component_generation import DEFAULT_TIMEOUT_SECONDS
from arkali.engineering.localai.ollama_adapter import OllamaAdapter
from arkali.engineering.localai.host_probe import probe_host
from arkali.engineering.localai.suitability import LocalSelection, LocalSelectionRequest, select_local_model
from arkali.engineering.product_change.change_plan import ChangePlan
from arkali.engineering.product_change.inspection import _is_sensitive_path
from arkali.engineering.product_change.modification import _apply_changeset, _extract_json_object, _validate_changeset
from arkali.engineering.product_change.verification import verify_changeset
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.execution.durable.job_store import JobStore, JobSubmission
from arkali.execution.durable.job_state_machine import RUNNING, FAILED, SUCCEEDED
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

MAX_CONTEXT_BYTES = 16 * 1024
MAX_SOURCE_FILES = 5
MAX_EDITABLE_FILES = 2


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _source(root: Path, relative: str) -> bytes:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or _is_sensitive_path(relative):
        raise ValueError("excluded source path")
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError("source containment refused")
    subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative],
                   cwd=root, check=True, capture_output=True)
    if target.stat().st_size > MAX_CONTEXT_BYTES:
        raise ValueError("source exceeds context budget")
    data = target.read_bytes()
    # Never rewrite a source from a redacted approximation of its real bytes.
    if redact_raw_secrets(data.decode("utf-8")) != data.decode("utf-8"):
        raise ValueError("source contains excluded secret material")
    return data


def compile_task(root, task_id, request, paths, acceptance, workspace, *, selection: LocalSelection | None = None):
    paths = tuple(sorted(set(paths)))
    if not 1 <= len(paths) <= MAX_SOURCE_FILES:
        raise ValueError("source file-count budget exceeded")
    source = {path: _source(root, path) for path in paths}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    spec = redact_raw_secrets(request)
    contract = json.dumps({"request": spec, "acceptance": acceptance,
                           "constraints": "update grounded files only; no tools; no repair; no promotion"}, sort_keys=True)
    items = tuple(ContextItem(kind="files", identifier=path,
                             origin=f"git:{head}:{path}@{_digest(data)}") for path, data in source.items())
    items += (ContextItem(kind="contracts", identifier=_digest(contract.encode()),
                          origin="human bounded task and acceptance target"),)
    package = ContextPackage.compiled(ContextKindAuthority.load(root), package_id=task_id + "-context",
                                      task_id=task_id, items=items)
    environment = f"{selection.provider}:{selection.model_id}" if selection else "local"
    task = HarnessTask(task_specification=spec, context_package=package.context_hash, tools=(),
                       permissions=(), workspace=str(workspace), environment=environment,
                       acceptance_target=acceptance, repair_budget=0)
    prompt = ('Return only ChangePlan JSON: {"schema_version":"1.0.0","request_text":"...",'
              '"target_summary":"...","operations":[{"operation":"update","path":"...",'
              '"content":"full replacement content","rationale":"..."}]}. '
              'Keep every existing contract and all unrelated content. Maximum two file updates. '
              'No commands, new files, dependencies, deletions or renames.\n'
              + contract + "\nC-22:\n" + task.model_dump_json()
              + "\nC-23:\n" + package.model_dump_json()
              + "\nAUTHORITATIVE CURRENT SOURCE:\n"
              + json.dumps({p: b.decode("utf-8") for p, b in source.items()}, ensure_ascii=False))
    assert_no_raw_secret(prompt, sink="local engineering prompt")
    if len(prompt.encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("context byte budget exceeded; no truncation")
    return task, package, prompt, source


def execute_once(task, package, prompt, source, workspace, model, acceptance_check, selection: LocalSelection | None = None):
    """No loop. The caller persists the result through existing truth owners."""
    if task.repair_budget != 0 or task.tools or task.permissions or model.runtime != "ollama":
        raise ValueError("Phase 1 permits only tool-free, zero-repair local execution")
    if task.context_package != package.context_hash or task.workspace != str(workspace.root):
        raise ValueError("task/package/workspace binding mismatch")
    selected_model = selection.model_id if selection else getattr(model, "model_id", "")
    if not selected_model:
        raise ValueError("no canonical local model selection supplied")
    result = model.infer(selected_model, prompt, timeout_seconds=DEFAULT_TIMEOUT_SECONDS)
    if result.state.value != "PASS":
        raise ValueError("local inference failed: " + redact_raw_secrets(result.detail))
    assert_no_raw_secret(result.output, sink="local engineering output")
    plan = ChangePlan.model_validate_json(_extract_json_object(result.output))
    if len(plan.operations) > MAX_EDITABLE_FILES or any(
        op.operation != "update" or op.path not in source for op in plan.operations
    ):
        raise ValueError("plan escapes authorized update scope")
    _validate_changeset(plan.operations, grounded_paths=frozenset(source))
    for path, data in source.items():
        if (workspace.snapshot / path).read_bytes() != data:
            raise ValueError("stale isolated base")
    _apply_changeset(workspace, plan.operations)
    started = time.monotonic()
    verification = verify_changeset(workspace.snapshot, plan.operations)
    acceptance = acceptance_check() if verification.passed else {"passed": False, "detail": "syntax failed"}
    return {"plan": plan.model_dump(), "changed_files": [o.path for o in plan.operations],
            "verification_passed": verification.passed and acceptance["passed"],
            "syntax_failures": verification.failures, "acceptance": acceptance,
            "model_seconds": result.elapsed_seconds, "verification_seconds": time.monotonic() - started,
            "local_model_calls": 1, "external_execution_calls": 0, "automatic_retries": 0,
            "promotion": "NOT_PROMOTED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--request", required=True)
    parser.add_argument("--source", action="append", required=True)
    parser.add_argument("--acceptance-test", required=True, help="trusted tracked pytest file::node")
    parser.add_argument("--complexity", choices=("low", "medium", "high"), default="low")
    parser.add_argument("--warm-model", default=None)
    args = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
        raise ValueError("main must be clean before the local attempt")
    test_path, sep, node = args.acceptance_test.partition("::")
    test_bytes = _source(ROOT, test_path)
    if not sep or not node.isidentifier() or test_path in args.source:
        raise ValueError("a trusted acceptance node outside editable scope is required")
    model = OllamaAdapter(json_mode=True, max_output_tokens=4096)
    selection = select_local_model(
        model.list_models(),
        LocalSelectionRequest(complexity=args.complexity, required_capabilities=("coding",),
                              warm_model_id=args.warm_model),
        host=probe_host(),
    )
    pdp = PolicyDecisionPoint.load(ROOT)
    engine = create_persistence_engine(sqlite_url(ROOT / "var/command_center.db"))
    evidence_engine = create_persistence_engine(sqlite_url(ROOT / "var/factory/evidence/repair-evidence.db"))
    factory = create_session_factory(engine)

    def jobs(session):
        return JobStore(session, PolicyEnforcementPoint(pdp, "execution.durable.job_store"))

    # Identity is durable: repeating this command cannot create a second attempt.
    with unit_of_work(factory) as session:
        if jobs(session).get(args.task_id) is not None:
            raise ValueError("task already exists; automatic retry is forbidden")
        jobs(session).submit(JobSubmission(job_id=args.task_id, job_type="local_engineering.task",
            idempotency_key=args.task_id, payload={"request": redact_raw_secrets(args.request)}))
        jobs(session).transition(args.task_id, RUNNING)
    try:
        with tempfile.TemporaryDirectory() as empty_seed:
            workspace = WorkspaceAuthority(ROOT / "var/factory/changes").allocate(
                workspace_id=args.task_id, task_id=args.task_id, agent_id="local-engineering",
                stable_snapshot=Path(empty_seed))
        task, package, prompt, source = compile_task(ROOT, args.task_id, args.request, args.source,
                                                    args.acceptance_test, workspace.root, selection=selection)
        for path, data in source.items():
            workspace.write("snapshot/" + path, data)
            workspace.write("baseline/" + path, data)
        workspace.write("snapshot/acceptance_test.py", test_bytes)
        with unit_of_work(create_session_factory(evidence_engine)) as session:
            artifacts = ArtifactStore(session, ArtifactBlobStore(ROOT / "var/factory/evidence/blobs",
                PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")))
            provenance = ProvenanceInput(producer_agent="local-engineering", provider_model=f"{selection.provider}:{selection.model_id}",
                task_id=args.task_id, specification_version="local-engineering-phase1/1",
                context_hash=package.context_hash)
            context_ref = artifacts.register(json.dumps({"harness_task": task.model_dump(),
                "context_package": package.model_dump(), "prompt": prompt}, ensure_ascii=False).encode(), provenance)
        with unit_of_work(factory) as session:
            jobs(session).checkpoint(args.task_id, {"phase": "planning", "context_ref": context_ref,
                "context_hash": package.context_hash, "workspace": str(workspace.root)})

        def acceptance_check():
            env = dict(os.environ, ARKALI_REVIEW_WORKSPACE=str(workspace.root))
            check = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                "--confcutdir", str(workspace.snapshot), f"acceptance_test.py::{node}"],
                cwd=workspace.snapshot, env=env, capture_output=True, text=True, timeout=60)
            return {"passed": check.returncode == 0,
                    "detail": redact_raw_secrets((check.stdout + check.stderr)[-4000:])}

        report = execute_once(task, package, prompt, source, workspace, model, acceptance_check, selection)
        report.update(task_id=args.task_id, context_hash=package.context_hash, context_ref=context_ref,
                      context_items=len(package.items), context_bytes=len(prompt.encode()),
                      source_files=list(source), workspace=str(workspace.root), provider_model=f"{selection.provider}:{selection.model_id}",
                      selection_reason=selection.reason, switch_required=selection.switch_required,
                      warm_model_id=selection.warm_model_id, candidates_considered=selection.candidates_considered,
                      task_complexity=selection.complexity)
        if any((ROOT / p).read_bytes() != data for p, data in source.items()):
            raise ValueError("main source changed during execution")
        with unit_of_work(create_session_factory(evidence_engine)) as session:
            artifacts = ArtifactStore(session, ArtifactBlobStore(ROOT / "var/factory/evidence/blobs",
                PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")))
            report_ref = artifacts.register(json.dumps(report, ensure_ascii=False).encode(), provenance)
        with unit_of_work(factory) as session:
            jobs(session).checkpoint(args.task_id, {"phase": "reviewable" if report["verification_passed"] else "verification_failed",
                "report_ref": report_ref, "promotion": "NOT_PROMOTED"})
            jobs(session).transition(args.task_id, SUCCEEDED if report["verification_passed"] else FAILED)
        print(json.dumps({k: v for k, v in report.items() if k != "plan"}, ensure_ascii=False))
        return 0 if report["verification_passed"] else 1
    except Exception as error:
        with unit_of_work(factory) as session:
            jobs(session).checkpoint(args.task_id, {"phase": "failed", "reason": redact_raw_secrets(str(error)),
                                                   "automatic_retries": 0, "promotion": "NOT_PROMOTED"})
            jobs(session).transition(args.task_id, FAILED)
        raise
    finally:
        engine.dispose()
        evidence_engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
