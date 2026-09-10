"""D-037/D-039: one local task, at most one C-26 repair, no promotion.

Composition belongs here like run_product_change_worker, not in C-22/C-23.
Source and acceptance tests are explicitly selected by the human caller.
Only existing file updates are admitted. The model receives text, never tools,
and only trusted acceptance tests execute (not model commands). D-039 reuses
the C-26 fingerprint and ledger; no local counter or third call exists.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import difflib
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.secret_reference import assert_no_raw_secret, redact_raw_secrets
from arkali.engineering.agent.context_kinds import ContextKindAuthority
from arkali.engineering.agent.context_package import ContextItem, ContextPackage
from arkali.engineering.agent.harness_task import HarnessTask
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.candidate.campaign_budget import (
    CANDIDATE_DEFECT, INFRASTRUCTURE_FAILURE, MODEL_VARIANCE,
)
from arkali.engineering.factory.component_generation import DEFAULT_TIMEOUT_SECONDS
from arkali.engineering.localai.ollama_adapter import OllamaAdapter
from arkali.engineering.localai.host_probe import probe_host
from arkali.engineering.localai.suitability import LocalSelection, LocalSelectionRequest, select_local_model
from arkali.engineering.product_change.change_plan import ChangePlan
from arkali.engineering.product_change.errors import ModelPlanInvalidError
from arkali.engineering.product_change.inspection import _is_sensitive_path
from arkali.engineering.product_change.modification import _apply_changeset, _extract_json_object, _validate_changeset
from arkali.engineering.product_change.verification import verify_changeset
from arkali.engineering.repair.contracts import (
    RepairBudget, RepairBudgetLedger, RepairFingerprint, content_hash,
)
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.execution.durable.job_store import JobStore, JobSubmission
from arkali.execution.durable.job_state_machine import RUNNING, FAILED, SUCCEEDED
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

MAX_CONTEXT_BYTES = 16 * 1024
MAX_ACCEPTANCE_TEST_BYTES = 64 * 1024
MAX_SOURCE_FILES = 5
MAX_EDITABLE_FILES = 2
REPAIR_ELIGIBLE_FAILURES = frozenset((CANDIDATE_DEFECT, MODEL_VARIANCE))


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _source(root: Path, relative: str, *, max_bytes: int = MAX_CONTEXT_BYTES) -> bytes:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or _is_sensitive_path(relative):
        raise ValueError("excluded source path")
    target = root / path
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError("source containment refused")
    subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative],
                   cwd=root, check=True, capture_output=True)
    if target.stat().st_size > max_bytes:
        raise ValueError("source exceeds declared byte budget")
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


def _execute_attempt(prompt, source, workspace, model, acceptance_check, selection):
    result = model.infer(selection.model_id, prompt, timeout_seconds=DEFAULT_TIMEOUT_SECONDS)
    if result.state.value != "PASS":
        raise ValueError("local inference failed: " + redact_raw_secrets(result.detail))
    assert_no_raw_secret(result.output, sink="local engineering output")
    try:
        plan = ChangePlan.model_validate_json(_extract_json_object(result.output))
    except (ModelPlanInvalidError, ValidationError) as error:
        return {
            "plan": {"operations": []}, "changed_files": list(source),
            "verification_passed": False,
            "syntax_failures": ("invalid_change_plan: " + redact_raw_secrets(str(error)),),
            "acceptance": {"passed": False, "detail": "model output was not a valid ChangePlan"},
            "model_seconds": result.elapsed_seconds, "verification_seconds": 0.0,
            "local_model_calls": 1, "external_execution_calls": 0,
            "automatic_retries": 0, "promotion": "NOT_PROMOTED",
            "plan_invalid": True,
        }
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


def execute_once(task, package, prompt, source, workspace, model, acceptance_check, selection: LocalSelection | None = None):
    """One initial attempt, retained as the zero-repair Phase-1 seam."""
    if task.repair_budget != 0 or task.tools or task.permissions or model.runtime != "ollama":
        raise ValueError("local execution must be tool-free, zero-repair and Ollama-only")
    if task.context_package != package.context_hash or task.workspace != str(workspace.root):
        raise ValueError("task/package/workspace binding mismatch")
    selected = selection or LocalSelection(
        provider=model.runtime, model_id=getattr(model, "model_id", ""), complexity="low",
        reason="test-supplied local model", switch_required=False, candidates_considered=(),
    )
    if not selected.model_id:
        raise ValueError("no canonical local model selection supplied")
    return _execute_attempt(prompt, source, workspace, model, acceptance_check, selected)


def _classify_verification_failure(_report):
    """Reuse the canonical campaign vocabulary for generated-solution failure."""
    return MODEL_VARIANCE if _report.get("plan_invalid") else CANDIDATE_DEFECT


def _fingerprint(report, selection, failure_class, *, outcome):
    evidence = json.dumps({
        "acceptance": report.get("acceptance"),
        "syntax_failures": report.get("syntax_failures"),
    }, sort_keys=True, default=str).encode()
    return RepairFingerprint(
        failure_signature=content_hash(evidence), root_cause_class=failure_class,
        files=tuple(report["changed_files"]), strategy="bounded_local_change",
        provider_model=f"{selection.provider}:{selection.model_id}", outcome=outcome,
    )


def _repair_ledger(task_id):
    return RepairBudgetLedger(candidate_id=task_id, budget=RepairBudget(
        attempts=1, ai_calls=1, elapsed_seconds=int(DEFAULT_TIMEOUT_SECONDS) + 60,
        cost=Decimal("0"), touched_files=MAX_EDITABLE_FILES, regression_delta=0,
    ))


def _compile_repair_context(task, package, source, workspace, report, fingerprint, selection):
    proposed = {path: (workspace.snapshot / path).read_text(encoding="utf-8") for path in source}
    proposal_diffs = {
        path: "".join(difflib.unified_diff(
            data.decode("utf-8").splitlines(keepends=True),
            proposed[path].splitlines(keepends=True),
            fromfile=f"baseline/{path}", tofile=f"proposal/{path}", n=3,
        ))
        for path, data in source.items()
    }
    repair_contract = {
        "original_task": task.task_specification,
        "protected_constraints": "grounded updates only; no tools, new files, dependencies or promotion",
        "previous_operations": [
            {key: operation[key] for key in ("operation", "path", "rationale")}
            for operation in report["plan"]["operations"]
        ],
        "verification": {
            "acceptance": report["acceptance"], "syntax_failures": report["syntax_failures"],
        },
        "failure_fingerprint": fingerprint.model_dump(mode="json"),
    }
    items = package.items + (
        ContextItem(kind="failures", identifier=fingerprint.fingerprint,
                    origin="deterministic verification of the initial isolated proposal"),
    )
    repair_package = ContextPackage.compiled(
        ContextKindAuthority.load(ROOT), package_id=package.task_id + "-repair-context",
        task_id=package.task_id, items=items,
    )
    repair_task = HarnessTask(
        task_specification=task.task_specification, context_package=repair_package.context_hash,
        tools=(), permissions=(), workspace=task.workspace,
        environment=f"{selection.provider}:{selection.model_id}",
        acceptance_target=task.acceptance_target, repair_budget=1,
    )
    repair_prompt = (
        "Return only schema-valid ChangePlan JSON. Repair the prior proposed update using the "
        "deterministic failure evidence. Preserve contracts and update only the grounded files.\n"
        + json.dumps(repair_contract, ensure_ascii=False, sort_keys=True)
        + "\nC-22 REPAIR:\n" + repair_task.model_dump_json()
        + "\nC-23 REPAIR:\n" + repair_package.model_dump_json()
        + "\nAUTHORITATIVE BASE SOURCE:\n"
        + json.dumps({p: data.decode("utf-8") for p, data in source.items()}, ensure_ascii=False)
        + "\nPREVIOUS PROPOSAL DIFF:\n" + json.dumps(proposal_diffs, ensure_ascii=False)
    )
    assert_no_raw_secret(repair_prompt, sink="local engineering repair prompt")
    if len(repair_prompt.encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("repair context byte budget exceeded; no truncation")
    return repair_task, repair_package, repair_prompt


def _repair_execution_failure(source, error):
    return {
        "plan": {"operations": []}, "changed_files": list(source),
        "verification_passed": False,
        "syntax_failures": ("repair_execution_failure: " + redact_raw_secrets(str(error)),),
        "acceptance": {"passed": False, "detail": "repair execution failed safely"},
        "model_seconds": 0.0, "verification_seconds": 0.0,
        "local_model_calls": 1, "external_execution_calls": 0,
        "automatic_retries": 0, "promotion": "NOT_PROMOTED",
    }


def execute_bounded_repair(
    task, package, prompt, source, workspace, model, acceptance_check,
    initial_selection, descriptors, *, selector=select_local_model, selection_host=None,
    persist_initial_failure=None,
):
    """Initial attempt plus at most one C-26-ledger-authorized local repair."""
    initial = execute_once(
        task, package, prompt, source, workspace, model, acceptance_check, initial_selection,
    )
    initial.update(initial_provider_model=f"{initial_selection.provider}:{initial_selection.model_id}")
    if initial["verification_passed"]:
        return initial
    failure_class = _classify_verification_failure(initial)
    initial_fp = _fingerprint(initial, initial_selection, failure_class, outcome="rejected")
    if persist_initial_failure is None:
        raise ValueError("initial failure persistence is required before repair")
    initial_failure_ref = persist_initial_failure({
        "task_id": package.task_id, "phase": "initial_verification_failed",
        "verification_passed": False, "failure_class": failure_class,
        "initial_fingerprint": initial_fp.fingerprint,
        "fingerprint": initial_fp.model_dump(mode="json"),
        "repair_status": "NOT_STARTED", "promotion": "NOT_PROMOTED",
    })
    if not initial_failure_ref:
        raise ValueError("initial failure persistence returned no evidence reference")
    ledger = _repair_ledger(package.task_id)
    initial.update(initial_fingerprint=initial_fp.fingerprint,
                   initial_failure_ref=initial_failure_ref,
                   repair_eligible=failure_class in REPAIR_ELIGIBLE_FAILURES,
                   repair_invoked=False, repair_budget=ledger.model_dump(mode="json"))
    if not initial["repair_eligible"]:
        return initial
    try:
        repair_selection = selector(
            tuple(descriptors), LocalSelectionRequest(
                complexity="high", required_capabilities=("coding",),
                warm_model_id=initial_selection.model_id,
            ), host=selection_host,
        )
        repair_task, repair_package, repair_prompt = _compile_repair_context(
            task, package, source, workspace, initial, initial_fp, repair_selection,
        )
    except ValueError as error:
        initial["repair_stop_reason"] = redact_raw_secrets(str(error))
        return initial
    current = {path: (workspace.snapshot / path).read_bytes() for path in source}
    try:
        repair = _execute_attempt(
            repair_prompt, current, workspace, model, acceptance_check, repair_selection,
        )
        final_class = failure_class
    except Exception as error:
        repair = _repair_execution_failure(source, error)
        final_class = INFRASTRUCTURE_FAILURE
    final_fp = _fingerprint(
        repair, repair_selection, final_class,
        outcome="resolved" if repair["verification_passed"] else "rejected",
    )
    ledger = ledger.record(
        final_fp, ai_calls=1,
        elapsed_seconds=max(1, math.ceil(repair["model_seconds"] + repair["verification_seconds"])),
        cost=Decimal("0"), touched_files=len(repair["changed_files"]), regression_delta=0,
    )
    repair.update(
        initial_verification=False, initial_fingerprint=initial_fp.fingerprint,
        initial_failure_ref=initial_failure_ref,
        repair_eligible=True, repair_invoked=True,
        repair_provider_model=f"{repair_selection.provider}:{repair_selection.model_id}",
        repair_selection_reason=repair_selection.reason,
        repair_switch_required=repair_selection.switch_required,
        repair_context_hash=repair_package.context_hash,
        repair_context_items=len(repair_package.items),
        repair_context_bytes=len(repair_prompt.encode()),
        repair_fingerprint=final_fp.fingerprint,
        same_fingerprint=final_fp.fingerprint == initial_fp.fingerprint,
        repair_budget=ledger.model_dump(mode="json"),
        local_model_calls=2, automatic_retries=1,
        _repair_context_payload={"harness_task": repair_task.model_dump(),
                                 "context_package": repair_package.model_dump(),
                                 "prompt": repair_prompt},
    )
    return repair


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
    test_bytes = _source(ROOT, test_path, max_bytes=MAX_ACCEPTANCE_TEST_BYTES)
    if not sep or not node.isidentifier() or test_path in args.source:
        raise ValueError("a trusted acceptance node outside editable scope is required")
    model = OllamaAdapter(json_mode=True, max_output_tokens=4096)
    descriptors = model.list_models()
    selection_host = probe_host()
    selection = select_local_model(
        descriptors,
        LocalSelectionRequest(complexity=args.complexity, required_capabilities=("coding",),
                              warm_model_id=args.warm_model),
        host=selection_host,
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

        def persist_initial_failure(evidence):
            payload = json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode()
            initial_provenance = ProvenanceInput(
                producer_agent="local-engineering", provider_model=f"{selection.provider}:{selection.model_id}",
                task_id=args.task_id, specification_version="local-engineering-c26-initial/1",
                context_hash=package.context_hash,
            )
            with unit_of_work(create_session_factory(evidence_engine)) as session:
                artifacts = ArtifactStore(session, ArtifactBlobStore(
                    ROOT / "var/factory/evidence/blobs",
                    PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")))
                initial_ref = artifacts.register(payload, initial_provenance)
            with unit_of_work(create_session_factory(evidence_engine)) as session:
                artifacts = ArtifactStore(session, ArtifactBlobStore(
                    ROOT / "var/factory/evidence/blobs",
                    PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")))
                if artifacts.get(initial_ref) is None:
                    raise ValueError("initial failure artifact was not durable")
            with unit_of_work(factory) as session:
                jobs(session).checkpoint(args.task_id, {
                    "phase": "initial_verification_failed",
                    "initial_failure_ref": initial_ref,
                    "initial_fingerprint": evidence["initial_fingerprint"],
                    "failure_class": evidence["failure_class"],
                    "repair_status": "NOT_STARTED", "promotion": "NOT_PROMOTED",
                })
            with unit_of_work(factory) as session:
                persisted = jobs(session).checkpoints(args.task_id)[-1].payload
                if persisted.get("initial_failure_ref") != initial_ref:
                    raise ValueError("initial failure checkpoint was not durable")
            return initial_ref

        report = execute_bounded_repair(
            task, package, prompt, source, workspace, model, acceptance_check,
            selection, descriptors, selection_host=selection_host,
            persist_initial_failure=persist_initial_failure,
        )
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
            repair_payload = report.pop("_repair_context_payload", None)
            if repair_payload is not None:
                repair_provenance = ProvenanceInput(
                    producer_agent="local-engineering",
                    provider_model=report["repair_provider_model"], task_id=args.task_id,
                    specification_version="local-engineering-c26/1",
                    context_hash=report["repair_context_hash"],
                )
                report["repair_context_ref"] = artifacts.register(
                    json.dumps(repair_payload, ensure_ascii=False).encode(), repair_provenance,
                )
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
