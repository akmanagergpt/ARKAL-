"""frontend_forms's own stage checker and bounded, per-module generation.

Owner: `engineering.factory`. Split out of `component_generation.py` (same
ADR-0008 decomposition shape `backend_stage_preflight.py` already used) --
FRONTEND_FORMS_OUTPUT_BOUNDARY (real evidence, this session:
`factory-garden-1790744835`'s own real qwen/qwen3.5-9b response hit the
exact 4096-token output ceiling, `finish_reason: "length"`, mid-way through
a second module's own create form, after backend_contract through
frontend_ui all genuinely passed) needed this fix, and `component_
generation.py` was already at its own measured 400/400 logical-line
ceiling with zero room for it.

WHY THIS BOUNDS GENERATION INSTEAD OF RAISING THE TOKEN CEILING. A normal
multi-entity CRUD product's frontend_forms output grows roughly linearly
with the number of create/edit-declaring modules -- two modules' forms
already exhausted the shared per-call `DEFAULT_MAX_OUTPUT_TOKENS` budget
every other stage also shares; a fixed ceiling can never scale past
whatever entity count first exhausts it, and unconditionally raising it
only postpones the same failure to a larger candidate.
`product/ux_spec.json` -- already frontend_forms's own real, authoritative,
already-declared input -- names every module product_ux_spec itself
requires create/edit forms for; generating one module's own forms per
bounded model call, the same size call every other stage already makes,
scales by adding calls, not by growing any one call's own output size.

WHY THIS REUSES `_generate_one_stage` FOR EACH UNIT, NEVER A SECOND
GENERATION LOOP. `component_generation._generate_one_stage` already owns
the full real per-attempt contract this pipeline depends on: bounded
retries, the anti-loop fingerprint check, structured repair hints,
`previous_attempt_output` threading, and every deterministic repair
already wired into it. A per-module "unit" is simply one more real call
into that exact same function, with a narrower `visible_files` view (this
stage's own real declared inputs, plus every earlier unit's own already-
accepted files) and a new, additive `unit_scope` prompt field naming which
module this particular call must -- and must not -- cover. Nothing about
retries, hints or repairs is reimplemented. Imported lazily (inside the
function, not at module load) to avoid a real import cycle:
`component_generation.py` imports this module's own dispatch function at
its own top level.

WHY THE PER-UNIT CHECK NARROWS `product/ux_spec.json` RATHER THAN
FILTERING FINDINGS. `_frontend_forms_findings`'s own real checks (via
`_ux_spec_mutation_findings`) validate that EVERY product_ux_spec-declared
create/edit module has real forms -- correct for the final, fully-merged
candidate, but if run against a single unit's own in-progress output it
would always report every not-yet-attempted module as missing its forms.
Substituting a real `_ProductUxSpec` copy whose own `modules` tuple holds
only the units already targeted (this one, plus every earlier one) lets
the exact same, unmodified checker function see only the modules that
genuinely should already have forms at that point -- never a second
checker, never a finding-filtering hack. After every unit succeeds, the
real, complete, unnarrowed spec is used for one final, authoritative check
over the fully merged frontend -- identical to what ran before this fix
for a single-unit product.
"""

from __future__ import annotations

from collections.abc import Mapping

from arkali.control.specification.blueprint_contracts import RequirementBlueprint
from arkali.engineering.factory.errors import _model_generation_error
from arkali.engineering.factory.frontend_callback_arity_preflight import (
    _callback_prop_arity_mismatch_findings,
)
from arkali.engineering.factory.frontend_client_call_preflight import (
    _client_call_missing_import_findings,
    _phantom_client_import_findings,
)
from arkali.engineering.factory.frontend_form_initial_state_preflight import (
    _form_initial_data_ignored_findings,
)
from arkali.engineering.factory.frontend_invented_mutation_preflight import (
    _invented_mutation_ui_findings,
)
from arkali.engineering.factory.frontend_route_param_preflight import _unread_route_param_findings
from arkali.engineering.factory.frontend_ux_preflight import _ux_spec_mutation_findings
from arkali.engineering.factory.generation_stages import StageDeclaration
from arkali.engineering.factory.model_product_generation import ModelSource
from arkali.engineering.factory.product_preflight import SemanticFinding
from arkali.engineering.factory.product_ux_spec import _UX_SPEC_PATH, _parse_ux_spec


def _frontend_forms_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`frontend_forms`'s own narrow rule: real, labelled, validated
    mutation UI for every product_ux_spec-declared create/edit action, a
    confirmation step before delete, and success feedback after a
    mutation. Split out from `frontend_ui` (golden-work-065, session
    evidence, frozen) -- see `STAGED_GENERATION_STAGES.md#9`."""
    return (
        _ux_spec_mutation_findings(files)
        + _client_call_missing_import_findings(files)
        + _phantom_client_import_findings(files)
        + _invented_mutation_ui_findings(files)
        + _unread_route_param_findings(files)
        + _callback_prop_arity_mismatch_findings(files)
        + _form_initial_data_ignored_findings(files)
    )


def _frontend_forms_units(visible_files: Mapping[str, str]) -> tuple[str, ...]:
    """Every product_ux_spec-declared module name that itself needs
    create/edit forms -- frontend_forms's own real, already-authoritative
    scope, named generically from the module's own real data, never a
    fixed entity count or domain name. Empty when no spec exists or no
    module declares create/edit -- the existing single-call path handles
    both exactly as it always has."""
    spec, _parse_findings = _parse_ux_spec(visible_files)
    if spec is None:
        return ()
    return tuple(
        module.name for module in spec.modules
        if "create" in module.actions or "edit" in module.actions
    )


def _narrowed_visible_files(
    visible_files: Mapping[str, str], module_names: frozenset[str],
) -> dict[str, str]:
    """The same real `visible_files` a unit's own attempt loop and checker
    both see, except `product/ux_spec.json` is replaced with a real copy
    holding only the modules already targeted (this unit, plus every
    earlier one in this same stage run) -- never a second source of truth,
    only a narrower view of the one that already exists."""
    spec, _parse_findings = _parse_ux_spec(visible_files)
    if spec is None:
        return dict(visible_files)
    narrowed = spec.model_copy(update={
        "modules": tuple(m for m in spec.modules if m.name in module_names),
    })
    return {**visible_files, _UX_SPEC_PATH: narrowed.model_dump_json()}


def _generate_frontend_forms_stage(
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
    """frontend_forms's own real dispatch: a product with at most one
    create/edit-declaring module is generated exactly as every other stage
    always has been -- one bounded call, unchanged (`target_runtime` is
    accepted only for a uniform call shape with every other stage; this
    stage's own rule never depends on it). A product with two or more is
    generated as one bounded call PER module, each a real
    `_generate_one_stage` attempt loop of its own, each seeing every
    earlier unit's own accepted files; the final merged result is
    validated once more by the exact same, unmodified stage checker before
    this stage is treated as passed."""
    from arkali.engineering.factory.component_generation import _generate_one_stage, _stage_findings

    units = _frontend_forms_units(visible_files)
    if len(units) <= 1:
        return _generate_one_stage(
            declaration, blueprint, model, model_id, visible_files,
            timeout_seconds=timeout_seconds, max_attempts=max_attempts,
        )

    accepted: dict[str, str] = {}
    completed: list[str] = []
    for unit in units:
        completed.append(unit)
        unit_visible = _narrowed_visible_files({**visible_files, **accepted}, frozenset(completed))
        accepted.update(_generate_one_stage(
            declaration, blueprint, model, model_id, unit_visible,
            timeout_seconds=timeout_seconds, max_attempts=max_attempts,
            unit_scope=unit,
        ))

    findings = _stage_findings("frontend_forms", {**visible_files, **accepted})
    if findings:
        detail = "; ".join(f"{f.code}:{f.path}:{f.detail}" for f in findings)
        raise _model_generation_error(
            f"stage 'frontend_forms' merged units still violate the contract: {detail}",
            "", None,
        )
    return accepted


__all__ = ["_generate_frontend_forms_stage"]
