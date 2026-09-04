"""Prepare one real Managed Product modification: resolve the base
revision, materialize its immutable source into a fresh isolated
workspace, inspect it, ask the real provider for a structured change
plan, validate and apply the resulting changeset, and verify it — all
before anything is ever proposed for human promotion (D-030).

NO MODEL-TO-SHELL AUTHORITY. The provider's own output is parsed only as
a `ChangePlan` (Pydantic, `extra="forbid"`); nothing it returns is ever
passed to a shell, `exec`, or `eval`. This module decides every file
mutation itself, through `CandidateWorkspace.write`/`.delete`/`.rename`
only.

DOMAIN-GENERAL. No product-domain word (student, payment, course, ...)
appears anywhere in this file; the prompt is built entirely from the
real, inspected structure of whatever product this runs against.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import time
from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

from arkali.engineering.product_change.change_plan import ChangeOperation, ChangePlan
from arkali.engineering.product_change.errors import (
    ChangesetValidationError,
    ModelPlanInvalidError,
)
from arkali.engineering.product_change.inspection import inspect_source, render_for_prompt
from arkali.engineering.product_change.revision_resolution import (
    _CandidateSourceResolver,
    materialized_source,
    resolve_current_revision,
)
from arkali.engineering.product_change.verification import VerificationResult, verify_changeset
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput

CHANGE_JOB_TYPE = "managed_product.change"
PLAN_ARTIFACT_SPEC = "managed-product-change-plan/1.0.0"
CHANGESET_ARTIFACT_SPEC = "managed-product-changeset-evidence/1.0.0"

_PROMPT_TEMPLATE = """You modify the source of a real, already-running web application \
based on a user's plain-language request. Respond with ONLY one JSON object matching \
this exact shape, no prose, no markdown fences:

{{"schema_version": "1.0.0", "request_text": "...", "target_summary": "...", \
"operations": [{{"operation": "create|update|delete|rename", "path": "relative/path", \
"new_path": null, "content": "full new file content or null", "rationale": "..."}}]}}

Rules:
- "path" is always relative to the product source root shown below, never absolute.
- "update"/"create" MUST include the file's full intended content in "content".
- Only touch files that already exist in the inventory below, or genuinely new files \
your plan creates.
- Prefer the smallest real change that honestly satisfies the request.

User request:
{request_text}

Real source inventory:
{inventory}
"""


@runtime_checkable
class _ModelInferenceResult(Protocol):
    """Structural shape of `engineering.localai.adapter.InferenceResult`
    -- redeclared, not imported: `engineering.product_change ->
    engineering.localai` measures at orchestration depth 5 (over the 4
    ceiling) and is also a same-rank sibling edge with no declared
    `allowed_sibling_edges` entry, the identical reasoning already
    established for `_CandidateSourceResolver` in `revision_resolution.py`.
    A composition root injects the real adapter; only its shape is used
    here."""

    state: object
    detail: str
    output: str


@runtime_checkable
class _ModelAdapter(Protocol):
    """Structural shape of `engineering.localai.adapter.LocalRuntimeAdapter`
    -- see `_ModelInferenceResult` for why this is redeclared rather than
    imported."""

    def infer(
        self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0
    ) -> _ModelInferenceResult: ...


@runtime_checkable
class _WorkspaceHandle(Protocol):
    root: pathlib.Path
    snapshot: pathlib.Path

    def write(self, relative: str, payload: bytes) -> pathlib.Path: ...
    def delete(self, relative: str) -> None: ...
    def rename(self, relative: str, new_relative: str) -> pathlib.Path: ...


@runtime_checkable
class _WorkspaceAllocator(Protocol):
    def allocate(
        self, *, workspace_id: str, task_id: str, agent_id: str, stable_snapshot: pathlib.Path,
    ) -> _WorkspaceHandle: ...


@dataclass(frozen=True)
class ModificationWiring:
    """Everything a composition root must inject — every field is a real
    collaborator over an existing authority, structural or direct as the
    architecture budget allows; see the module docstrings of `revision_
    resolution.py` for why `candidate_source_resolver` is structural."""

    artifacts: ArtifactStore
    candidate_source_resolver: _CandidateSourceResolver
    workspace_allocator: _WorkspaceAllocator
    model: _ModelAdapter
    model_id: str


@dataclass(frozen=True)
class PreparedModification:
    """The real, complete result of applying and verifying one changeset
    — not yet promoted. `product_root` is the real directory a preview
    runtime primitive can be pointed at directly."""

    workspace: _WorkspaceHandle
    product_root: pathlib.Path
    base_revision_id: str
    plan: ChangePlan
    plan_ref: str
    changeset_ref: str
    verification: VerificationResult


_OnPhase = Callable[[str, dict[str, object]], None]


def _report(on_phase: _OnPhase | None, phase: str, detail: dict[str, object]) -> None:
    if on_phase is not None:
        on_phase(phase, detail)


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ModelPlanInvalidError("provider response contains no JSON object")
    return text[start : end + 1]


def _validate_changeset(operations: tuple[ChangeOperation, ...]) -> None:
    """Refuses before any write: a collision (two operations naming the
    same target path), an unsafe path shape, or a structurally incomplete
    operation. `CandidateWorkspace.path_for`'s own containment check is
    the SECOND, filesystem-level line of defence applied at apply time;
    this is the first, schema-level one."""
    seen_targets: set[str] = set()
    for op in operations:
        if op.path.startswith("/") or ".." in pathlib.PurePath(op.path).parts:
            raise ChangesetValidationError(f"unsafe path in changeset: {op.path!r}")
        target = op.new_path if op.operation == "rename" else op.path
        if target is None:
            raise ChangesetValidationError(f"rename operation for {op.path!r} names no new_path")
        if target in seen_targets:
            raise ChangesetValidationError(f"changeset names {target!r} more than once")
        seen_targets.add(target)
        if op.operation in ("create", "update") and not op.content:
            raise ChangesetValidationError(f"{op.operation} of {op.path!r} carries no content")


#: Every real path `ChangeOperation` names is relative to the PRODUCT root
#: (`prepare_modification`'s own prompt: "relative to the product source
#: root shown below"), which is `workspace.snapshot` -- but every real
#: `CandidateWorkspace.write`/`.delete`/`.rename` call is relative to
#: `workspace.root` (proven by `test_candidate_workspace_manifest.py`'s own
#: `workspace.write("snapshot/app.py", ...)` convention). Every apply call
#: below therefore re-roots through this prefix; skipping it silently
#: writes outside the real product tree while leaving the file verification
#: checks would have failed against untouched -- a false PASS this
#: session's own test suite caught for real.
_SNAPSHOT_PREFIX = "snapshot/"


def _apply_changeset(workspace: _WorkspaceHandle, operations: tuple[ChangeOperation, ...]) -> None:
    for op in operations:
        if op.operation == "create" or op.operation == "update":
            workspace.write(_SNAPSHOT_PREFIX + op.path, (op.content or "").encode("utf-8"))
        elif op.operation == "delete":
            workspace.delete(_SNAPSHOT_PREFIX + op.path)
        elif op.operation == "rename":
            workspace.rename(
                _SNAPSHOT_PREFIX + op.path, _SNAPSHOT_PREFIX + op.new_path,  # type: ignore[operator]
            )


def _register_plan(artifacts: ArtifactStore, project_id: str, plan: ChangePlan) -> str:
    payload = plan.model_dump_json().encode("utf-8")
    return artifacts.register(
        payload,
        ProvenanceInput(
            producer_agent="engineering.product_change", provider_model="local",
            task_id=project_id, specification_version=PLAN_ARTIFACT_SPEC,
            context_hash=hashlib.sha256(plan.request_text.encode("utf-8")).hexdigest(),
        ),
    )


def _register_changeset_evidence(
    artifacts: ArtifactStore, project_id: str, plan_ref: str, verification: VerificationResult,
) -> str:
    payload = json.dumps(
        {
            "schema": CHANGESET_ARTIFACT_SPEC, "plan_ref": plan_ref,
            "checked_paths": verification.checked_paths, "passed": verification.passed,
            "failures": verification.failures,
        },
        sort_keys=True,
    ).encode("utf-8")
    return artifacts.register(
        payload,
        ProvenanceInput(
            producer_agent="engineering.product_change", provider_model="local",
            task_id=project_id, specification_version=CHANGESET_ARTIFACT_SPEC,
            context_hash=hashlib.sha256(payload).hexdigest(), parents=(plan_ref,),
        ),
    )


def prepare_modification(
    project_id: str, request_text: str, *, registry: object, wiring: ModificationWiring,
    on_phase: _OnPhase | None = None,
) -> PreparedModification:
    """The whole real pipeline short of promotion: resolve base revision
    -> materialize immutable source -> isolated workspace -> real
    inspection -> real provider call -> validated changeset -> real apply
    -> real verification -> evidence registered. Raises a typed refusal
    (never a silent partial result) the moment any step's own real
    precondition is not met.
    """
    revision = resolve_current_revision(project_id, registry=registry)  # type: ignore[arg-type]
    _report(on_phase, "base_revision_resolved", {"base_revision_id": revision.revision_id})

    with materialized_source(
        revision, artifacts=wiring.artifacts,
        candidate_source_resolver=wiring.candidate_source_resolver,
    ) as source:
        workspace_id = f"change-{project_id}-{int(time.time())}"
        workspace = wiring.workspace_allocator.allocate(
            workspace_id=workspace_id, task_id="product-change", agent_id="command-center",
            stable_snapshot=source,
        )
    product_root = workspace.snapshot
    _report(on_phase, "workspace_allocated", {"workspace_root": str(workspace.root)})

    report = inspect_source(product_root)
    _report(on_phase, "source_inspected", {
        "python_files": len(report.python_files), "js_files": len(report.js_files),
    })

    prompt = _PROMPT_TEMPLATE.format(
        request_text=request_text, inventory=render_for_prompt(report),
    )
    result = wiring.model.infer(wiring.model_id, prompt, timeout_seconds=180.0)
    if result.state.value != "PASS":
        shutil.rmtree(workspace.root, ignore_errors=True)
        raise ModelPlanInvalidError(f"provider call did not succeed: {result.detail}")
    try:
        plan = ChangePlan.model_validate_json(_extract_json_object(result.output))
    except Exception as error:  # noqa: BLE001 -- any parse/validation failure is one honest refusal
        shutil.rmtree(workspace.root, ignore_errors=True)
        raise ModelPlanInvalidError(f"provider response is not a valid ChangePlan: {error}") from error
    _report(on_phase, "plan_ready", {"operations": len(plan.operations)})

    _validate_changeset(plan.operations)
    _apply_changeset(workspace, plan.operations)
    _report(on_phase, "changes_applied", {"operations": len(plan.operations)})

    _report(on_phase, "verification_running", {})
    verification = verify_changeset(product_root, plan.operations)
    _report(
        on_phase, "verification_passed" if verification.passed else "verification_failed",
        {"failures": verification.failures},
    )

    plan_ref = _register_plan(wiring.artifacts, project_id, plan)
    changeset_ref = _register_changeset_evidence(wiring.artifacts, project_id, plan_ref, verification)

    return PreparedModification(
        workspace=workspace, product_root=product_root, base_revision_id=revision.revision_id,
        plan=plan, plan_ref=plan_ref, changeset_ref=changeset_ref, verification=verification,
    )
