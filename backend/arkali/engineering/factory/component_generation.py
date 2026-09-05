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
`product_preflight.py`'s existing `_manifest_findings`,
`model_product_generation.py`'s `_json_payload` and
`backend_stage_preflight.py`'s/`product_ux_spec.py`'s own per-stage
validators exactly as written, rather than promoting them to public names
that no other bounded context will ever consume — promoting them was
tried first and mechanically measured to push the context over budget
(47/40) purely from added public names, with zero behavior difference
either way. Only one new name is actually public here:
`generate_staged_model_product`, the one entry point a real caller
(`scripts/run_staged_generation.py`) needs.

STAGE OUTPUT IS NEVER MORE THAN ITS DECLARED INPUTS. Each stage's prompt
embeds only the real, already-written bytes of the stage names
`generation_stages.StageVocabulary` declares as that stage's inputs — never
the whole accumulated candidate, never a paraphrase. A stage is accepted
only when its own narrow validation returns zero findings; "the model
returned parseable JSON" is necessary, never sufficient.
"""

from __future__ import annotations

import json
import platform
import re
import warnings
from collections.abc import Callable, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from arkali.control.specification.blueprint_contracts import RequirementBlueprint
from arkali.engineering.factory.backend_contract_preflight import _backend_contract_findings
from arkali.engineering.factory.backend_stage_preflight import (
    _backend_implementation_stage_findings,
    _backend_tests_stage_findings,
    _cors_boundary_stage_findings,
    _schema_only_findings,
)
from arkali.engineering.factory.dependency_resolution import _apply_missing_compatibility_cap_repair
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.frontend_client_call_preflight import (
    _client_call_missing_import_findings,
    _phantom_client_import_findings,
    _repair_missing_client_call_imports,
)
from arkali.engineering.factory.frontend_invented_mutation_preflight import (
    _invented_mutation_ui_findings,
    _repair_invented_mutation_ui,
)
from arkali.engineering.factory.frontend_manifest_preflight import (
    _missing_frontend_entry_point_findings,
    _frontend_local_import_findings,
    _react_router_missing_import_findings,
    _repair_missing_react_router_imports,
    _repair_react_router_version_mismatch,
)
from arkali.engineering.factory.frontend_root_route_preflight import (
    _missing_root_route_findings,
    _orphaned_router_root_findings,
    _repair_orphaned_router_root,
)
from arkali.engineering.factory.frontend_callback_arity_preflight import (
    _callback_prop_arity_mismatch_findings,
)
from arkali.engineering.factory.frontend_form_initial_state_preflight import (
    _form_initial_data_ignored_findings,
)
from arkali.engineering.factory.frontend_route_param_preflight import _unread_route_param_findings
from arkali.engineering.factory.frontend_route_shadowing_preflight import _repair_shadowed_routes
from arkali.engineering.factory.frontend_ux_preflight import (
    _missing_ui_state_findings,
    _split_client_and_ui,
    _unreachable_module_findings,
    _unused_client_export_findings,
    _ux_spec_mutation_findings,
    _ux_spec_shell_findings,
)
from arkali.engineering.factory.generation_stages import StageDeclaration, StageVocabulary
from arkali.engineering.factory.http_contract_preflight import frontend_contract_findings
from arkali.engineering.factory.manifest_context import _manifest_context
from arkali.engineering.factory.product_ux_spec import (
    _repair_flat_ux_spec_envelope,
    _ux_spec_stage_findings,
)
from arkali.engineering.factory.model_product_generation import (
    GeneratedFile,
    ModelProductResult,
    ModelSource,
    WorkspaceTarget,
    _json_payload,
    _normalise_python_transport,
)
from arkali.engineering.factory.product_preflight import (
    SemanticFinding, _manifest_findings, _manifests_stage_findings,
)
from arkali.engineering.factory.stage_prompting import _stage_prompt, _repair_strategy_for_attempt

MAX_STAGE_ATTEMPTS = 4

#: Real measured floor throughput for `qwen2.5-coder:14b` (Q4_K_M) against
#: this project's real development host (an 8GB-VRAM laptop GPU): two
#: independent, live, non-streaming `/api/generate` calls both measured
#: ~7.1 tokens/second (298 tokens/42.1s, then 424 tokens/59.4s). Real
#: evidence, not assumed: `golden-work-075` and `golden-work-076`, two
#: fresh candidates with ordinary-sized prior stage output, both genuinely
#: timed out at the `frontend_ui` stage -- the stage most likely to need a
#: generation close to `DEFAULT_MAX_OUTPUT_TOKENS` (it writes the most
#: files of any stage) -- because the prior default timeout (300s) could
#: not cover one full-budget generation at this real, hardware-bound
#: floor. Never lower `_MEASURED_MIN_TOKENS_PER_SECOND` without a new real
#: measurement on this same host.
_MEASURED_MIN_TOKENS_PER_SECOND = 7.0
DEFAULT_MAX_OUTPUT_TOKENS = 4096
#: One full generation at the measured floor, plus a 50% margin for
#: prompt evaluation and real host variance (thermal, background load).
DEFAULT_TIMEOUT_SECONDS = (DEFAULT_MAX_OUTPUT_TOKENS / _MEASURED_MIN_TOKENS_PER_SECOND) * 1.5


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


#: golden-work-065 (session evidence, frozen): a real qwen2.5-coder:14b
#: implemented a genuine empty-state branch three times over
#: (`students.length === 0 ? <p>No students found</p> : ...`) and every
#: one was a real false positive against a bare `"empty" in text`
#: check — the literal word never appears, only real, more specific
#: phrasing. Loading/error stay single-marker: real output overwhelmingly
#: uses those exact words, and no real evidence yet shows otherwise.
def _frontend_ui_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`frontend_ui`'s own narrow rule: it calls the client, renders states,
    and (golden-work-061, session evidence, frozen) provides the real
    entry point mounting its own component — required here, not at
    `manifests`, since only this stage actually knows the component's
    real file name. Mutation UI is `frontend_forms`'s own concern
    (golden-work-065, session evidence, frozen), not checked here."""
    client, ui = _split_client_and_ui(files)
    return (
        _unused_client_export_findings(client, ui)
        + _missing_ui_state_findings(ui)
        + _missing_frontend_entry_point_findings(files)
        + _unreachable_module_findings(files)
        + _react_router_missing_import_findings(files)
        + _frontend_local_import_findings(files)
        + _missing_root_route_findings(files)
        + _orphaned_router_root_findings(files)
        + _ux_spec_shell_findings(files)
    )


def _frontend_forms_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`frontend_forms`'s own narrow rule: real, labelled, validated
    mutation UI for every product_ux_spec-declared create/edit action, a
    confirmation step before delete, and success feedback after a
    mutation. Split out from `frontend_ui` (golden-work-065, session
    evidence, frozen) — see `STAGED_GENERATION_STAGES.md#9`."""
    return (
        _ux_spec_mutation_findings(files)
        + _client_call_missing_import_findings(files)
        + _phantom_client_import_findings(files)
        + _invented_mutation_ui_findings(files)
        + _unread_route_param_findings(files)
        + _callback_prop_arity_mismatch_findings(files)
        + _form_initial_data_ignored_findings(files)
    )


#: One handler per stage that has its own narrow rule. A stage absent here
#: (currently none) has no per-stage check; the final whole-product
#: `inspect_product_files` gate still applies to every stage's output.
_STAGE_VALIDATORS: dict[str, Callable[[Mapping[str, str]], list[SemanticFinding]]] = {
    "backend_contract": _backend_contract_findings,
    "backend_schema": _schema_only_findings,
    "backend_implementation": _backend_implementation_stage_findings,
    "backend_cors_boundary": _cors_boundary_stage_findings,
    "backend_tests": _backend_tests_stage_findings,
    "product_ux_spec": _ux_spec_stage_findings,
    "frontend_client": frontend_contract_findings,
    "frontend_ui": _frontend_ui_findings,
    "frontend_forms": _frontend_forms_findings,
    "frontend_tests_config": _manifest_findings,
    "manifests": _manifests_stage_findings,
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


def _apply_deterministic_repairs(
    visible_files: Mapping[str, str], stage_files: dict[str, str],
) -> dict[str, str]:
    """Every deterministic repair this pipeline knows, applied in sequence
    before findings are computed — never another blind model guess once
    the exact, unambiguous fix for a real, verified defect is known
    (golden-work-050/051's own lesson). Extracted from `_generate_one_stage`
    itself (ADR-0008 decomposition, not a GATE 8 exception: adding a third
    repair pushed that function's own measured complexity over its
    ceiling) — each repair still owns its own real evidence citation and
    reasoning in its own module; this only sequences them. golden-work-060
    (frozen evidence): a real, unrelated second finding must never
    silently discard a working repair, so every repair here runs
    unconditionally regardless of what the others found."""
    repair_fns = (
        lambda sf: _apply_missing_compatibility_cap_repair(sf),
        lambda sf: _repair_react_router_version_mismatch({**visible_files, **sf}, sf),
        lambda sf: _repair_missing_react_router_imports(sf),
        lambda sf: _repair_missing_client_call_imports({**visible_files, **sf}, sf),
        lambda sf: _repair_shadowed_routes(sf),
        lambda sf: _repair_orphaned_router_root(visible_files, sf),
        lambda sf: _repair_invented_mutation_ui({**visible_files, **sf}, sf),
    )
    for repair_fn in repair_fns:
        repaired = repair_fn(stage_files)
        if repaired is not None:
            stage_files = repaired
    return stage_files


def _parse_stage_envelope(
    stage_name: str, raw_output: str,
) -> tuple[_StageEnvelope | None, str | None]:
    """Real stage output validated against `_StageEnvelope`, falling back
    to `product_ux_spec`'s own deterministic flat-envelope repair
    (golden-work-093/094, session evidence, frozen, byte-identical
    failure reproduced on two independent candidates) before treating a
    contract violation as final -- once the exact, unambiguous fix for a
    real, verified defect is known, applying it and re-validating is more
    honest than another blind model retry (golden-work-050/051's own
    lesson, the same one every other deterministic repair in this
    pipeline already follows)."""
    payload = _json_payload(raw_output)
    try:
        return _StageEnvelope.model_validate_json(payload), None
    except (ValueError, json.JSONDecodeError) as error:
        repaired = _repair_flat_ux_spec_envelope(stage_name, payload)
        if repaired is None:
            return None, f"stage response violates the contract: {error}"
    try:
        return _StageEnvelope.model_validate_json(repaired), None
    except (ValueError, json.JSONDecodeError) as error:
        return None, f"stage response violates the contract: {error}"


#: F-0070. `generate_staged_model_product` is already at its own real,
#: measured `max_parameters_per_public_function` ceiling (6 of 6) --
#: adding a seventh, `on_attempt`, would breach it the same way bundling
#: `model_factory` to return `(model, model_id)` together already avoided
#: a seventh parameter once before (this module's own docstring). Rather
#: than repeat that bundling trick awkwardly (a caller-supplied
#: `on_attempt` has no natural home inside `model_factory`'s own
#: per-stage `(model, model_id)` return shape), this reuses the one
#: object already flowing through the ENTIRE per-stage retry loop at
#: exactly attempt granularity: `model: ModelSource`. `ModelSource` is a
#: structural `Protocol` (`model_product_generation.py`) whose only
#: REQUIRED method is `infer` -- a caller's own real model object may
#: freely implement an ADDITIONAL, entirely optional `record_attempt`
#: method alongside it without widening the Protocol's own required
#: shape or touching any existing `ModelSource` implementation (every
#: test's own `_QueueModel`, which implements only `infer`, is completely
#: unaffected). `_generate_one_stage` (private, no public-parameter
#: budget) checks for it structurally; `run_staged_generation.py` is free
#: to wrap its own real model source with one that also freezes each
#: real attempt as diagnostic provenance via the same `ArtifactStore`/
#: `_freeze()` mechanism the terminal outcome already uses -- never a
#: second authoritative store, never a substitute for the candidate
#: ledger, terminal evidence, or campaign ledger.
def _notify_attempt(
    model: ModelSource, stage_name: str, attempt_number: int, repair_strategy: str,
    prompt: str, raw_output: str, findings: tuple[tuple[str, str, str], ...],
    fingerprint: str | None,
) -> None:
    observe = getattr(model, "record_attempt", None)
    if observe is None:
        return
    try:
        observe(stage_name, attempt_number, repair_strategy, prompt, raw_output, findings, fingerprint)
    except Exception as error:  # noqa: BLE001 -- diagnostic-only (F-0070): a
        # caller-supplied observability hook must never abort or alter a
        # real, in-progress generation attempt, regardless of what it
        # itself does internally; an explicit warning, never a silent
        # swallow and never a crash, is the honest degraded-evidence
        # signal (`KeyboardInterrupt`/`SystemExit` are BaseException, not
        # Exception, and still propagate normally).
        warnings.warn(
            f"F-0070 attempt-observability hook failed for stage {stage_name!r} "
            f"attempt {attempt_number}: {error}", RuntimeWarning, stacklevel=2,
        )


def _generate_one_stage(
    declaration: StageDeclaration,
    blueprint: RequirementBlueprint,
    model: ModelSource,
    model_id: str,
    visible_files: Mapping[str, str],
    *,
    timeout_seconds: float,
    max_attempts: int,
    target_runtime: str | None = None,
) -> dict[str, str]:
    from arkali.kernel.contracts.honest_state import HonestState

    failure: str | None = None
    previous_failure: str | None = None
    last_raw_output: str = ""
    #: F-0069. The most recent attempt's own real, structured findings, as
    #: plain `(code, path, detail)` facts -- never the real `SemanticFinding`
    #: type itself, so this module's own existing import of it is not
    #: duplicated into `stage_prompting.py` (whose own fan-in has no room
    #: for a new direct edge; routed through `product_preflight`'s
    #: established re-export once already, for the same reason, this
    #: session). Reset to empty whenever the most recent attempt produced no
    #: real findings at all (inference failure, contract violation) --
    #: mirrors `failure`'s own "always reflects the most recent attempt"
    #: semantics exactly, never carrying a stale attempt's own facts
    #: forward past one that produced none.
    last_findings: tuple[tuple[str, str, str], ...] = ()
    #: FACTORY RELIABILITY CONVERGENCE. `visible_files` is this stage's
    #: declared INPUTS (strictly-earlier stages) and never changes across
    #: attempts -- a retry's own prior REJECTED output was never shown back
    #: to the model, anywhere, for any stage. `prior_attempt_failure` named
    #: a code/path/location (e.g. "line 42: unterminated string literal")
    #: that pointed at a file the model could no longer see, since it had
    #: already been discarded; the model had to blindly regenerate the
    #: whole stage from scratch, guided only by a location it could not
    #: check against anything in front of it. Real, independently-
    #: reproduced evidence: `goal-mtm6qrdr-apus8c` (`backend_cors_boundary`,
    #: two consecutive real Python-syntax fingerprints) and
    #: `goal-mtolm3cv-ivuo9g` (`product_ux_spec`, two consecutive real
    #: `ux_spec_missing_module`/`ux_spec_invented_module` fingerprints) both
    #: hit `ARK-ERR-0116` this way. This is SUBJECT-GENERIC (every stage
    #: shares the same retry shape) and DOMAIN-INDEPENDENT (no stage/finding
    #: name is special-cased): once a stage's own output parses as a real
    #: `_StageEnvelope`, its per-file content is retained across attempts
    #: and threaded back into the next prompt, unconditionally.
    previous_attempt_files: dict[str, str] | None = None
    for attempt_number in range(1, max_attempts + 1):
        strategy = _repair_strategy_for_attempt(attempt_number)
        prompt = _stage_prompt(
            declaration, blueprint, visible_files, failure, target_runtime,
            repair_strategy=strategy, prior_findings=last_findings,
            previous_attempt_files=previous_attempt_files,
        )
        outcome = model.infer(model_id, prompt, timeout_seconds=timeout_seconds)
        last_raw_output = outcome.output
        if outcome.state is not HonestState.PASS or not outcome.output.strip():
            failure = f"stage inference did not pass: {outcome.state.value}: {outcome.detail}"
            last_findings = ()
        else:
            envelope, parse_failure = _parse_stage_envelope(declaration.name, outcome.output)
            if envelope is None:
                failure = parse_failure
                last_findings = ()
            else:
                stage_files = {item.path: item.content for item in envelope.files}
                # F-0080. The one-shot path (`write_model_product_output`)
                # already reuses this exact primitive at the identical point
                # in its own pipeline (right after parsing, before any
                # check) -- staged generation never called it. Real, live
                # evidence (`goal-mtow4gf9-84kplb`, `backend_cors_boundary`):
                # a real provider double-escapes an embedded newline as
                # `\\n` in its own raw JSON reply, which the one legitimate
                # `json.loads` above decodes to a literal two-character
                # `\n` -- never an actual line break -- collapsing an
                # entire real ".py" file onto one logical line and failing
                # `ast.parse` with the exact historical
                # "unexpected character after line continuation character"
                # error. `_normalise_python_transport` only ever touches a
                # ".py" file whose content does not already parse, and only
                # ever keeps the transformed candidate if THAT parses --
                # already-valid content (including a legitimate literal
                # `\n` inside a string, in an otherwise valid file) is
                # provably left untouched, never guessed into a different
                # meaning.
                stage_files = _normalise_python_transport(stage_files)
                stage_files = _apply_deterministic_repairs(visible_files, stage_files)
                findings = _stage_findings(declaration.name, {**visible_files, **stage_files})
                if not findings:
                    _notify_attempt(
                        model, declaration.name, attempt_number, strategy, prompt,
                        outcome.output, (), None,
                    )
                    return stage_files
                last_findings = tuple((f.code, f.path, f.detail) for f in findings)
                failure = "; ".join(f"{f.code}:{f.path}:{f.detail}" for f in findings)
                # A real, parseable (if rejected) attempt's own exact bytes
                # become the NEXT attempt's own visible prior output -- see
                # the retry-loop docstring above.
                previous_attempt_files = stage_files
        _notify_attempt(
            model, declaration.name, attempt_number, strategy, prompt,
            outcome.output, last_findings, failure,
        )
        # ANTI-LOOP, generic across every stage: two consecutive attempts
        # rejected for the identical normalized reason (same code, path
        # and detail) will not resolve on a blind third/fourth retry —
        # golden-work-047's manifests stage exhausted its full budget on
        # exactly this class of repeat, and this pipeline never even
        # detected it, since nothing before this compared attempts to one
        # another. This does not raise the bounded maximum; it stops
        # before spending it on a call already proven to repeat.
        if failure == previous_failure and attempt_number < max_attempts:
            error = ModelGenerationError(
                f"stage {declaration.name!r} repeated the identical failure fingerprint "
                f"on attempts {attempt_number - 1} and {attempt_number}, stopping before "
                f"exhausting the remaining bounded attempts: {failure}"
            )
            error.last_raw_output = last_raw_output  # type: ignore[attr-defined]
            raise error
        previous_failure = failure
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
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
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
        target_runtime: str | None = None
        if declaration.name == "manifests":
            # Only this stage's context is reduced; every other stage still
            # sees the real, full bytes of exactly its declared inputs.
            visible = _manifest_context(visible)
            # Only this stage's declared rule depends on the target
            # runtime (STAGED_GENERATION_STAGES.md); golden-work-047
            # (session evidence) showed the model was never told it.
            target_runtime = platform.python_version()
        model, model_id = model_factory(declaration.name)
        stage_files = _generate_one_stage(
            declaration, blueprint, model, model_id, visible,
            timeout_seconds=timeout_seconds, max_attempts=per_stage_max_attempts,
            target_runtime=target_runtime,
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
