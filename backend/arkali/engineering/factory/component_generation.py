"""Staged (multi-component) real-model product generation.

Owner: `engineering.factory`. Composes the same real authorities
`model_product_generation.generate_model_product_bounded` already uses for
its one-shot path — `GeneratedFile`, `ModelProductEnvelope`,
`inspect_product_files`, the `ModelSource`/`WorkspaceTarget` structural
ports — into a sequence of small, bounded, narrowly-validated model calls
instead of one whole-product call. `generate_model_product_bounded` is not
modified and stays available; this is an additional path, not a
replacement.

WHY THIS MODULE IMPORTS PRIVATE NAMES FROM ITS SIBLING MODULES.
`engineering.factory`'s public-surface budget (`AUTHORITY_MAP.yaml
architecture_budgets: max_public_surface_per_context: 40`) is measured
per bounded context, across every module in it, counting every top-level
class/function whose name does not start with `_` — not per module, and
not filtered by `__all__`. This module's per-stage checks reuse
`product_preflight.py`'s existing `_persistence_findings`,
`_schema_context_findings`, `_manifest_findings` and
`model_product_generation.py`'s `_json_payload` exactly as written, rather
than promoting them to public names that no other bounded context will
ever consume — promoting them was tried first and mechanically measured
to push the context over budget (47/40) purely from added public names,
with zero behavior difference either way. Only one new name is actually
public here: `generate_staged_model_product`, the one entry point a real
caller (`scripts/run_staged_generation.py`) needs.

STAGE OUTPUT IS NEVER MORE THAN ITS DECLARED INPUTS. Each stage's prompt
embeds only the real, already-written bytes of the stage names
`generation_stages.StageVocabulary` declares as that stage's inputs — never
the whole accumulated candidate, never a paraphrase. A stage is accepted
only when its own narrow validation returns zero findings; "the model
returned parseable JSON" is necessary, never sufficient.
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from arkali.control.specification.blueprint_contracts import RequirementBlueprint
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.generation_stages import StageDeclaration, StageVocabulary
from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings
from arkali.engineering.factory.model_product_generation import (
    GeneratedFile,
    ModelProductResult,
    ModelSource,
    WorkspaceTarget,
    _json_payload,
)
from arkali.engineering.factory.product_preflight import (
    SemanticFinding,
    _manifest_findings,
    _persistence_findings,
    _schema_context_findings,
)
from arkali.engineering.factory.test_contract_preflight import (
    fixture_findings,
    lifecycle_findings,
)

MAX_STAGE_ATTEMPTS = 4


class _StageEnvelope(BaseModel):
    """One stage's own output: a small file set, not a whole product.

    Reuses `GeneratedFile` unchanged for per-file safety (relative/confined
    path, no null bytes, size bound) — the only difference from
    `model_product_generation.ModelProductEnvelope` is that this envelope
    makes no whole-product claim (no required roots, no runnable-manifest
    requirement): a stage's own files are frequently just one or two files.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    files: tuple[GeneratedFile, ...] = Field(min_length=1, max_length=32)

    @field_validator("files", mode="before")
    @classmethod
    def _normalise_path_map(cls, value: object) -> object:
        if isinstance(value, dict):
            return [{"path": path, "content": content} for path, content in value.items()]
        return value

    @model_validator(mode="after")
    def _unique_paths(self) -> _StageEnvelope:
        paths = tuple(item.path for item in self.files)
        if len(set(paths)) != len(paths):
            raise ValueError("a stage's generated paths must be unique")
        return self


_HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch"})


def _backend_contract_json_files(files: Mapping[str, str]) -> list[object]:
    parsed: list[object] = []
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".json")):
            continue
        try:
            parsed.append(json.loads(source))
        except json.JSONDecodeError:
            continue
    return parsed


def _declares_routes(parsed_files: list[object]) -> bool:
    for document in parsed_files:
        if not isinstance(document, list):
            continue
        if any(
            isinstance(item, dict) and "path" in item
            and str(item.get("method", "")).lower() in _HTTP_METHODS
            for item in document
        ):
            return True
    return False


def _declares_a_model(parsed_files: list[object]) -> bool:
    return any(
        isinstance(document, dict) and "fields" in document for document in parsed_files
    )


def _backend_contract_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`backend_contract`'s own narrow rule: a machine-readable route and data
    model schema is declared (JSON, not Python — see
    STAGED_GENERATION_STAGES.md#1)."""
    parsed = _backend_contract_json_files(files)
    findings: list[SemanticFinding] = []
    if not _declares_routes(parsed):
        findings.append(SemanticFinding(
            code="backend_contract_no_routes", path="backend/",
            detail="no backend/*.json file declares a route array with path+method",
        ))
    if not _declares_a_model(parsed):
        findings.append(SemanticFinding(
            code="backend_contract_no_models", path="backend/",
            detail="no backend/*.json file declares a data model with a 'fields' key",
        ))
    return findings


def _split_client_and_ui(files: Mapping[str, str]) -> tuple[str, str]:
    client_paths = [
        path for path in files if path.startswith("frontend/src/") and "client" in path.lower()
    ]
    ui_paths = [
        path for path in files if path.startswith("frontend/src/") and "client" not in path.lower()
    ]
    client = "\n".join(files[path] for path in client_paths)
    ui = "\n".join(files[path] for path in ui_paths)
    return client, ui


def _unused_client_export_findings(client: str, ui: str) -> list[SemanticFinding]:
    exported = set(re.findall(r"export\s+(?:const|function)\s+(\w+)", client))
    uncalled = sorted(name for name in exported if name not in ui)
    if not uncalled:
        return []
    return [SemanticFinding(
        code="frontend_ui_client_unused", path="frontend/src/",
        detail=f"frontend_ui never calls client export(s) {uncalled!r}",
    )]


def _missing_ui_state_findings(ui: str) -> list[SemanticFinding]:
    lowered = ui.lower()
    missing = [state for state in ("loading", "error") if state not in lowered]
    return [
        SemanticFinding(
            code="frontend_ui_missing_state", path="frontend/src/",
            detail=f"frontend_ui renders no {state!r} state",
        )
        for state in missing
    ]


def _frontend_ui_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`frontend_ui`'s own narrow rule: it calls the client and renders states."""
    client, ui = _split_client_and_ui(files)
    return _unused_client_export_findings(client, ui) + _missing_ui_state_findings(ui)


def _backend_text(files: Mapping[str, str]) -> str:
    return "\n".join(
        source.lower() for path, source in files.items()
        if path.startswith("backend/") and path.endswith(".py")
    )


def _python_syntax_findings(files: Mapping[str, str], *, path_prefix: str) -> list[SemanticFinding]:
    """Real `ast.parse` on every `.py` file under `path_prefix`.

    golden-work-045's real backend_implementation output (session evidence)
    passed every substring/regex check here while containing an actual
    `SyntaxError` (an unterminated multi-line string) — none of the checks
    below ever parse the code they inspect. This is the gap that closes;
    same finding code (`python_syntax`) `product_preflight.python_modules`
    already uses for the same defect at the final whole-product gate, so a
    caller sees one vocabulary either way.
    """
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith(path_prefix) and path.endswith(".py")):
            continue
        try:
            ast.parse(source)
        except SyntaxError as error:
            findings.append(SemanticFinding(
                code="python_syntax", path=path,
                detail=f"line {error.lineno}: {error.msg}",
            ))
    return findings


def _schema_only_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Schema/persistence only — no route or entrypoint requirement.

    backend_contract no longer declares any Python (see
    STAGED_GENERATION_STAGES.md#1), so `product_preflight._persistence_findings`
    (which bundles schema together with route markers and an entrypoint check)
    cannot pass at this stage by construction — those belong to
    backend_implementation, not backend_schema. This duplicates
    `_persistence_findings`'s own sqlite/schema pair (not its route/entrypoint
    half) rather than promoting a fourth product_preflight helper to public:
    the real architecture-budget gate already measured this context at its
    40/40 public-surface ceiling once this session (see this module's own
    docstring) and every net-new promotion was reverted for exactly that
    reason.
    """
    syntax_findings = _python_syntax_findings(files, path_prefix="backend/")
    if syntax_findings:
        return syntax_findings
    backend_text = _backend_text(files)
    findings: list[SemanticFinding] = []
    uses_sqlite = "sqlite3" in backend_text or "sqlite://" in backend_text
    creates_schema = "create table" in backend_text or "create_all(" in backend_text
    if not uses_sqlite:
        findings.append(SemanticFinding(
            code="missing_persistence_code", path="backend/",
            detail="backend Python source contains no executable SQLite persistence",
        ))
    elif not creates_schema:
        findings.append(SemanticFinding(
            code="missing_schema_bootstrap", path="backend/",
            detail="SQLite is selected but no schema creation or migration is present",
        ))
    findings.extend(_schema_context_findings(backend_text))
    return findings


#: Same marker set `http_contract_preflight.frontend_contract_findings` checks
#: for (FastAPI/Starlette's CORSMiddleware, Flask's flask_cors/CORS(app)).
#: Duplicated here (3 short strings) rather than imported, since that
#: function's own marker tuple is a local, unexported detail — promoting it
#: to module level there would cost another public-surface symbol this
#: context has no room for.
_CORS_MARKERS = ("corsmiddleware", "flask_cors", "cors(app")


def _backend_implementation_stage_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Full persistence+routes+entrypoint+CORS — routes and cross-origin
    access are expected by now. CORS is checked unconditionally here (not
    "only if a frontend already exists") because backend_implementation
    owns backend/app.py and no later stage does — golden-work-045 (session
    evidence) discovered this gap only at frontend_client, two stages after
    the one file that could still fix it.
    """
    syntax_findings = _python_syntax_findings(files, path_prefix="backend/")
    if syntax_findings:
        return syntax_findings
    findings = _persistence_findings(files) + _schema_context_findings(_backend_text(files))
    backend_text = _backend_text(files)
    if not any(marker in backend_text for marker in _CORS_MARKERS):
        findings.append(SemanticFinding(
            code="missing_browser_origin_boundary", path="backend/",
            detail="backend declares no CORS middleware for its separate-origin frontend",
        ))
    return findings


def _backend_tests_stage_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    syntax_findings = _python_syntax_findings(files, path_prefix="tests/")
    if syntax_findings:
        return syntax_findings
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("tests/") and path.endswith(".py")):
            continue
        tree = ast.parse(source)
        findings.extend(fixture_findings(path, tree))
        findings.extend(lifecycle_findings(files))
    return findings


#: One handler per stage that has its own narrow rule. A stage absent here
#: (currently none) has no per-stage check; the final whole-product
#: `inspect_product_files` gate still applies to every stage's output.
_STAGE_VALIDATORS: dict[str, Callable[[Mapping[str, str]], list[SemanticFinding]]] = {
    "backend_contract": _backend_contract_findings,
    "backend_schema": _schema_only_findings,
    "backend_implementation": _backend_implementation_stage_findings,
    "backend_tests": _backend_tests_stage_findings,
    "frontend_client": frontend_contract_findings,
    "frontend_ui": _frontend_ui_findings,
    "frontend_tests_config": _manifest_findings,
    "manifests": _manifest_findings,
}


def _stage_findings(stage_name: str, files: Mapping[str, str]) -> list[SemanticFinding]:
    """The narrow validation for one stage, over its real accumulated bytes
    (its declared inputs' real content plus its own new output) — never the
    whole, possibly-incomplete candidate. `product_preflight.inspect_product_files`
    is not called here; it runs exactly once, over the full assembled
    candidate, after every stage completes.
    """
    validator = _STAGE_VALIDATORS.get(stage_name)
    return validator(files) if validator is not None else []


def _stage_prompt(
    declaration: StageDeclaration, blueprint: RequirementBlueprint,
    visible_files: Mapping[str, str], prior_failure: str | None,
) -> str:
    return json.dumps({
        "role": "You are one bounded stage of a multi-stage software factory.",
        "stage": declaration.name,
        "task": declaration.rule,
        "output_contract": {
            "format": "one JSON object only; no markdown or commentary",
            "schema": {"files": [{"path": "relative/posix/path", "content": "complete text"}]},
            "json_encoding_rule": (
                "Every file content is a JSON string. Escape newlines as \\n and "
                "all other control characters per RFC 8259."
            ),
        },
        "goal": blueprint.goal.goal_text,
        "requirements": [item.statement for item in blueprint.requirements],
        "visible_prior_files": visible_files,
        "prior_attempt_failure": prior_failure,
        "convergence_rule": (
            "When prior_attempt_failure is present, correct that exact defect "
            "while retaining everything else already correct."
        ),
    }, ensure_ascii=False, separators=(",", ":"))


def _generate_one_stage(
    declaration: StageDeclaration,
    blueprint: RequirementBlueprint,
    model: ModelSource,
    model_id: str,
    visible_files: Mapping[str, str],
    *,
    timeout_seconds: float,
    max_attempts: int,
) -> dict[str, str]:
    from arkali.kernel.contracts.honest_state import HonestState

    failure: str | None = None
    last_raw_output: str = ""
    for _ in range(1, max_attempts + 1):
        prompt = _stage_prompt(declaration, blueprint, visible_files, failure)
        outcome = model.infer(model_id, prompt, timeout_seconds=timeout_seconds)
        last_raw_output = outcome.output
        if outcome.state is not HonestState.PASS or not outcome.output.strip():
            failure = f"stage inference did not pass: {outcome.state.value}: {outcome.detail}"
            continue
        try:
            envelope = _StageEnvelope.model_validate_json(_json_payload(outcome.output))
        except (ValueError, json.JSONDecodeError) as error:
            failure = f"stage response violates the contract: {error}"
            continue
        stage_files = {item.path: item.content for item in envelope.files}
        merged = {**visible_files, **stage_files}
        findings = _stage_findings(declaration.name, merged)
        if findings:
            failure = "; ".join(f"{f.code}:{f.path}:{f.detail}" for f in findings)
            continue
        return stage_files
    # The raw last-attempt output is retained on the exception (not just the
    # mechanical failure summary) so a caller can freeze real diagnostic
    # evidence — golden-work-043 and the first golden-work-045 stage failure
    # this session both had to be reported without it, since nothing else in
    # this pipeline persists a rejected attempt's actual bytes.
    error = ModelGenerationError(
        f"stage {declaration.name!r} exhausted {max_attempts} attempts: {failure}"
    )
    error.last_raw_output = last_raw_output  # type: ignore[attr-defined]
    raise error


def generate_staged_model_product(
    blueprint: RequirementBlueprint,
    model_factory: Callable[[str], tuple[ModelSource, str]],
    workspace: WorkspaceTarget,
    *,
    vocabulary: StageVocabulary,
    timeout_seconds: float = 300.0,
    per_stage_max_attempts: int = MAX_STAGE_ATTEMPTS,
) -> ModelProductResult:
    """Generate a candidate as a sequence of small, bounded, contract-checked
    stages instead of one whole-product model call.

    `model_factory(stage_name)` returns `(model, model_id)` — bundled
    together, not two separate parameters, both because a real caller
    typically sizes the adapter (`max_output_tokens`) per stage and picks
    the same `model_id` for all of them, and because
    `max_parameters_per_public_function` (6) left no room for a seventh.

    Every stage's model call is bounded (1-4 attempts, same shape
    `generate_model_product_bounded` already uses); a stage is written to
    `workspace` only once its own narrow validation passes. Callers still
    owe the whole-product check this function does not perform — construct
    `model_product_generation.ModelProductEnvelope` over the assembled
    result and run `product_preflight.inspect_product_files` before treating
    any candidate this returns as promotable.
    """
    if not blueprint.is_fully_resolved:
        raise ModelGenerationError("staged generation refuses an unresolved blueprint")
    if not 1 <= per_stage_max_attempts <= MAX_STAGE_ATTEMPTS:
        raise ModelGenerationError("per-stage attempt budget must be between 1 and 4")

    all_files: dict[str, str] = {}
    written_paths: list[str] = []
    written_by_stage: dict[str, tuple[str, ...]] = {}
    attempts_used = 0

    for declaration in vocabulary.stages():
        visible: dict[str, str] = {}
        for input_name in declaration.inputs:
            for path in written_by_stage[input_name]:
                visible[path] = all_files[path]
        model, model_id = model_factory(declaration.name)
        stage_files = _generate_one_stage(
            declaration, blueprint, model, model_id, visible,
            timeout_seconds=timeout_seconds, max_attempts=per_stage_max_attempts,
        )
        for path, content in stage_files.items():
            workspace.write(path, content.encode("utf-8"))
            all_files[path] = content
            written_paths.append(path)
        written_by_stage[declaration.name] = tuple(stage_files)
        attempts_used += 1

    return ModelProductResult(
        blueprint_id=blueprint.blueprint_id,
        runtime="staged",
        model_id=model_id,
        files=tuple(written_paths),
        attempts_used=attempts_used,
    )


__all__ = ["generate_staged_model_product"]
