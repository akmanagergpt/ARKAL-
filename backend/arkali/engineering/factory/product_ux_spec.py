"""The `product_ux_spec` stage's schema, parser and backend-reconciliation.

Owner: `engineering.factory`. Internal staged-generation artifact only — not
a `CONTRACT_INVENTORY.md` entry, not a new authority, not an acceptance
verdict (see `STAGED_GENERATION_STAGES.md`'s own module-docstring precedent:
"nothing outside `engineering.factory` consumes this vocabulary"). This is a
*generation input* a later stage (`frontend_ui`) consumes, the same relation
`backend_contract`'s route/model JSON already has to `backend_implementation`
and `frontend_ui`.

WHY A SEPARATE STAGE INSTEAD OF FOLDING THIS INTO `frontend_ui`'S OWN RULE.
`frontend_ui` already writes real JSX/CSS source under real attempt/time
pressure (`STAGED_GENERATION_STAGES.md#7`/`8`). Planning which modules exist,
what navigates where, and which backend capability maps to which UI action
is a distinct, structured-data task with its own narrow, checkable shape —
the same reason `backend_contract` (schema-only) was split from
`backend_implementation` (real code) rather than asking one stage to do
both. `frontend_ui` still writes all real source; this stage only writes one
JSON planning artifact it then consumes as an input.

WHY THE SCHEMA IS DOMAIN-GENERIC. Every field name, module name and
navigation label here is derived from `backend_contract`'s own real declared
routes and data models — never a hard-coded product domain. A `Dershane`
specific answer key would defeat the entire point: this must generalize to
whatever the real blueprint's own goal and backend actually declare.

RECONCILIATION IS STRUCTURAL, NOT AESTHETIC. This stage's own validator
checks that every backend-declared data model has a corresponding UX
module (no reachable backend capability is planned into invisibility) and
that a module's declared actions do not under-claim what the real backend
methods for its resource actually expose. It never scores color, spacing or
"how professional this looks" — see `frontend_ux_preflight.py`'s own
docstring for the same boundary applied to the rendered UI.

EVERY PYDANTIC MODEL HERE IS PRIVATE ON PURPOSE. `engineering.factory`'s
public-surface budget (`max_public_surface_per_context: 40`) was already
measured once this session at its ceiling purely from promoted names with
zero behavior difference (see `component_generation.py`'s own docstring).
Only `_parse_ux_spec` and `_ux_spec_stage_findings` are consumed outside
this module; nothing else needs to be public.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from arkali.engineering.factory.semantic_finding import SemanticFinding

_ACTIONS = Literal["create", "edit", "delete", "view"]
_PRESENTATIONS = Literal["table", "card", "list"]

#: Relative POSIX path the `product_ux_spec` stage must write its one JSON
#: artifact to — a dedicated top-level root, additive only: the whole-product
#: gate's `required_roots` check (`model_product_generation.REQUIRED_ROOTS`)
#: is "at least these roots exist", never "only these roots may exist", so a
#: new root here is not rejected by it.
_UX_SPEC_PATH = "product/ux_spec.json"


class _UxFormSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    fields: tuple[str, ...] = Field(min_length=1)


class _UxStateCoverage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    loading: bool = True
    empty: bool = True
    error: bool = True
    #: Only meaningful (and only checked) when the owning module declares a
    #: mutating action — a read-only module has nothing to confirm.
    success: bool = False


class _UxModuleSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Must equal a real backend_contract-declared data model's table name
    #: (or its JSON file stem) — reconciled by `_ux_spec_stage_findings`,
    #: never taken on faith.
    name: str = Field(min_length=1)
    navigation_label: str = Field(min_length=1)
    presentation: _PRESENTATIONS
    actions: tuple[_ACTIONS, ...] = ()
    forms: tuple[_UxFormSpec, ...] = ()
    search_filter: bool = False
    states: _UxStateCoverage = _UxStateCoverage()


class _UxKpiSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    #: What the KPI counts/aggregates (e.g. "count_students") — real
    #: evidence this session (golden-work-064, frozen): a real
    #: qwen2.5-coder:14b's own unprompted shape for a KPI was never a bare
    #: string ("Total Students") but a {"name": ..., "metric": ...} object;
    #: codified as the real schema rather than fought, the same rule
    #: STAGED_GENERATION_STAGES.md#1 already states for backend_contract's
    #: own schema-first shape.
    metric: str = Field(min_length=1)


class _UxDashboardSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    navigation_label: str = Field(min_length=1, default="Dashboard")
    purpose: str = Field(min_length=1)
    kpis: tuple[_UxKpiSpec, ...] = ()


class _UxDesignSystemSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    typography_scale: tuple[str, ...] = Field(min_length=1)
    spacing_scale: tuple[str, ...] = Field(min_length=1)
    component_conventions: tuple[str, ...] = Field(min_length=1)
    #: golden-work-064 (session evidence, frozen): this stage's own rule
    #: text named "responsive" with no declared type, and a real
    #: qwen2.5-coder:14b reasonably read it as a yes/no flag (`true`), not
    #: a strategy string ("desktop-first") — a real prompt ambiguity this
    #: introduced, not a model defect. Accepts both real shapes rather
    #: than forcing one arbitrary format choice.
    responsive: bool | str = True
    accessible_focus_contrast: bool = True


class _ProductUxSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    product_title: str = Field(min_length=1)
    primary_roles: tuple[str, ...] = Field(min_length=1)
    #: A single-purpose product (one module) is legitimate — nothing here
    #: requires more than one; `min_length=1`, never a higher floor, is the
    #: whole answer to "don't force an enterprise shell onto a simple app".
    modules: tuple[_UxModuleSpec, ...] = Field(min_length=1)
    navigation_destinations: tuple[str, ...] = Field(min_length=1)
    #: Absent (None) is legitimate for a single-module product with nothing
    #: worth summarising — never required unconditionally.
    dashboard: _UxDashboardSpec | None = None
    design_system: _UxDesignSystemSpec
    destructive_action_confirmation: bool = True


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _parse_ux_spec(files: Mapping[str, str]) -> tuple[_ProductUxSpec | None, list[SemanticFinding]]:
    raw = files.get(_UX_SPEC_PATH)
    if raw is None:
        return None, [SemanticFinding(
            code="ux_spec_missing", path=_UX_SPEC_PATH,
            detail=f"no {_UX_SPEC_PATH} was written by the product_ux_spec stage",
        )]
    try:
        spec = _ProductUxSpec.model_validate_json(raw)
    except (ValidationError, ValueError) as error:
        return None, [SemanticFinding(
            code="ux_spec_invalid", path=_UX_SPEC_PATH, detail=str(error),
        )]
    return spec, []


def _path_stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    return name[: -len(".json")] if name.endswith(".json") else name


def _backend_json_documents(files: Mapping[str, str]) -> list[tuple[str, object]]:
    """Every real `backend/*.json` file's parsed content, paired with its
    path — the shared scan `_backend_declared_models` and
    `_backend_methods_by_resource` both build on, so neither repeats the
    parse loop (and its own decision points) itself."""
    documents: list[tuple[str, object]] = []
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".json")):
            continue
        try:
            documents.append((path, json.loads(source)))
        except json.JSONDecodeError:
            continue
    return documents


def _is_multi_model_field_map(fields: object) -> bool:
    """True for `{"students": {"id": "integer", ...}, "courses": {...}}` —
    one file's "fields" key holding several models keyed by name — false
    for one model's own `{"id": {"type": "integer"}, ...}` field map.

    golden-work-064 (session evidence, frozen): backend_contract's own
    rule (`STAGED_GENERATION_STAGES.md#1`) only ever required "a JSON
    object ... carrying a 'fields' key" — it never ruled out nesting
    several models under that one key, and a real qwen2.5-coder:14b wrote
    exactly one `backend/data_model.json` with three models nested this
    way. `_backend_declared_models` below silently saw one model (this
    file's own path stem) instead of three real ones — blind to exactly
    the shape `frontend_ux_preflight._unreachable_module_findings`'s own
    len(models) >= 2 gate exists to catch.
    """
    if not isinstance(fields, dict) or not fields:
        return False
    return all(isinstance(value, dict) and "type" not in value for value in fields.values())


def _model_names_in_document(path: str, parsed: object) -> set[str]:
    if not (isinstance(parsed, dict) and "fields" in parsed):
        return set()
    fields = parsed["fields"]
    if _is_multi_model_field_map(fields):
        return set(fields.keys())
    table_name = parsed.get("table_name")
    return {str(table_name) if table_name else _path_stem(path)}


def _backend_declared_models(files: Mapping[str, str]) -> set[str]:
    names: set[str] = set()
    for path, parsed in _backend_json_documents(files):
        names |= _model_names_in_document(path, parsed)
    return names


def _route_items(files: Mapping[str, str]) -> list[dict]:
    items: list[dict] = []
    for _path, parsed in _backend_json_documents(files):
        if isinstance(parsed, list):
            items.extend(item for item in parsed if isinstance(item, dict))
    return items


def _resource_keys(item: dict) -> list[str]:
    """Every real, non-parameter path segment, normalized -- not only the
    first. A real backend is free to nest a resource under a real,
    semantic prefix (`/api/books/overdue`, real evidence: `factory-goal-
    mtpnp9af-yeldck`) rather than the flat `/resource` convention every
    prior golden fixture happened to use; `acceptance_plan_compiler.
    _module_routes` was already widened this same way (F-0084) for its
    own, separate route-matching concern, but this sibling function --
    reconciling a module's own DECLARED actions against the real HTTP
    methods a route backs, `_module_parity_findings`'s own real
    mechanism and `acceptance_plan_compiler._resolved_actions`'s only
    source of truth -- still only ever checked `segments[0]`, silently
    reconciling NO real methods at all for any nested route (real
    evidence: `factory-goal-mtquvzmc-dt3go3`'s own real, mutation-capable
    `/api/catalog/widgets`-shaped test fixture would have wrongly refused
    a genuinely correct create/edit/delete module once `acceptance_plan_
    compiler` started gating a synthesized create/update payload on this
    exact reconciliation)."""
    if "path" not in item or "method" not in item:
        return []
    segments = [s for s in str(item["path"]).split("/") if s and not s.startswith("{")]
    return [_normalize(s) for s in segments]


def _backend_methods_by_resource(files: Mapping[str, str]) -> dict[str, set[str]]:
    """Every real, non-parameter path segment (normalized) -> the real
    HTTP methods declared for it. Deliberately coarse (path-segment
    matching, not full route resolution) — the same tolerance
    `http_contract_preflight._exposes` already accepts for this exact
    class of check."""
    methods: dict[str, set[str]] = {}
    for item in _route_items(files):
        for key in _resource_keys(item):
            methods.setdefault(key, set()).add(str(item["method"]).upper())
    return methods


#: golden-work-098 (session evidence, frozen): backend_contract's own real
#: `task_model.json` declared no `table_name` at all, so
#: `_backend_declared_models`'s own fallback (`_path_stem`) named it
#: "task_model" -- the exact real name `_module_parity_findings` then
#: correctly required the ux_spec module to reuse verbatim (golden-work-
#: 095's own fix). `_matching_methods` below normalizes that to
#: "taskmodel" and compares it against the real route's own resource key
#: ("tasks", from `/tasks`) -- neither string contains the other
#: ("taskmodel" has no "tasks" substring; "tasks" is not a substring of
#: "taskmodel" either), so this matched NOTHING, silently, for any real
#: candidate using this exact "<resource>_model" naming convention this
#: session's own real evidence has now produced twice (golden-work-095
#: and golden-work-098 both named a module "task_model"). Stripping a
#: trailing "model" suffix before the substring comparison -- only on
#: this function's own resource-matching side, never touching
#: `_module_parity_findings`'s own exact-name reconciliation, which
#: genuinely needs the unstripped "task_model" to match the backend's own
#: declared name -- turns "taskmodel" into "task", a real substring of
#: "tasks".
def _resource_matching_name(module_name: str) -> str:
    normalized = _normalize(module_name)
    if normalized.endswith("model") and len(normalized) > len("model"):
        return normalized[: -len("model")]
    return normalized


def _matching_methods(resource_methods: dict[str, set[str]], module_name: str) -> set[str]:
    normalized_module = _resource_matching_name(module_name)
    found: set[str] = set()
    for key, methods in resource_methods.items():
        if normalized_module in key or key in normalized_module:
            found |= methods
    return found


_METHOD_TO_ACTION = {"POST": "create", "PUT": "edit", "PATCH": "edit", "DELETE": "delete"}


def _module_parity_findings(spec: _ProductUxSpec, files: Mapping[str, str]) -> list[SemanticFinding]:
    """Every backend-declared data model has a corresponding module, and no
    module names one the backend never declared.

    golden-work-095 (session evidence, frozen): a real qwen2.5-coder:14b
    declared a module named "tasks" against a real backend-declared model
    whose own real name was "task_model" -- normalized to "taskmodel" for
    comparison (case/separator-insensitive matching is deliberate: real
    candidates routinely spell the same concept "Students"/"students"/
    "student_model"). The finding detail this stage's own retry feedback
    showed back to the model, though, was ALREADY-NORMALIZED
    ("['taskmodel']") -- not a real, usable module-name string the model
    could copy verbatim, since normalization strips underscores/case the
    model would naturally reintroduce when writing one. Two consecutive
    real retries reproduced the identical mismatch byte-for-byte and
    exhausted the anti-loop budget: the model had no way to guess which
    exact literal string would satisfy a check whose own normalization
    rule was never disclosed. `missing` now reports the real backend name
    (the exact string a corrected module's own "name" field should use);
    `invented` still reports the model's own already-real, self-declared
    name -- it never needed to guess that half.

    F-0068 (`golden-work-130`, real repository evidence, frozen, a THIRD
    independent real occurrence of the identical class): disclosing the
    literal real name was still not enough. `backend/task_model.json`
    declared no `table_name`, so `_backend_declared_models`'s own fallback
    (`_path_stem`) named it "task_model" -- an awkward, redundant real name
    no reasonable UX module would naturally choose. The stage's own retry
    feedback correctly showed "['task_model']" as a real, literal,
    copy-pasteable string on every attempt, and the real model still wrote
    "task" as its own module name on the final attempt rather than copying
    it verbatim -- an EXACT match was never going to converge against a
    name this artificial. `_matching_methods` (below) already solves the
    identical asymmetry for action/route reconciliation by stripping a
    genuine trailing "model" suffix via `_resource_matching_name` before
    comparing; this function now reuses that exact same helper, unchanged,
    for its own comparison, rather than inventing a second normalization
    rule. `missing`/`invented` still report the real, un-stripped original
    names -- `_resource_matching_name` is used only to decide whether two
    real names refer to the same real concept, never surfaced as a string
    the model would have to reproduce."""
    real_models = _backend_declared_models(files)
    matching_to_real = {_resource_matching_name(name): name for name in real_models}
    module_matching_names = {_resource_matching_name(module.name) for module in spec.modules}
    findings: list[SemanticFinding] = []
    missing = sorted(
        matching_to_real[key] for key in matching_to_real if key not in module_matching_names
    )
    if missing:
        findings.append(SemanticFinding(
            code="ux_spec_missing_module", path=_UX_SPEC_PATH,
            detail=f"backend_contract declares data model(s) {missing!r} with no "
                   "corresponding module in product_ux_spec -- add a module whose "
                   "\"name\" field matches one of these real backend-declared names",
        ))
    invented = sorted({
        module.name for module in spec.modules
        if _resource_matching_name(module.name) not in matching_to_real
    })
    if invented:
        findings.append(SemanticFinding(
            code="ux_spec_invented_module", path=_UX_SPEC_PATH,
            detail=f"product_ux_spec declares module(s) {invented!r} matching no "
                   "backend_contract-declared data model",
        ))
    return findings


def _module_action_findings(
    module: _UxModuleSpec, resource_methods: dict[str, set[str]]
) -> list[SemanticFinding]:
    """A module never under-claims a mutating action the real backend
    exposes a method for, never over-claims one the real backend has no
    method for, and never claims create/edit with no form.

    golden-work-098 (real end-to-end execution evidence, frozen): a real
    module declared `"actions": ["create", "edit", "delete", "view"]`
    against a real backend that only ever implemented GET/POST/PUT for
    `/tasks` -- no DELETE route anywhere (backend_contract runs before
    product_ux_spec even exists; it had no way to know a later stage
    would declare a delete action). frontend_forms then faithfully built
    a full, real TaskDelete.js -- a real confirm-then-delete UI, a real
    `deleteTask` client call -- pointing at an endpoint that structurally
    could never exist. A real production build compiled successfully; a
    real user clicking "Yes" would get a real HTTP 405 from Flask, not a
    build-time or syntax error. Over-claiming is only checked when
    `real_methods` is non-empty -- an inconclusive resource match (this
    module's own name never matched any real backend resource at all)
    must never be treated as proof every one of its declared actions is
    unsupported."""
    real_methods = _matching_methods(resource_methods, module.name)
    required_actions = {_METHOD_TO_ACTION[m] for m in real_methods if m in _METHOD_TO_ACTION}
    findings: list[SemanticFinding] = []
    under_declared = sorted(required_actions - set(module.actions))
    if under_declared:
        findings.append(SemanticFinding(
            code="ux_spec_action_under_declared", path=_UX_SPEC_PATH,
            detail=f"module {module.name!r}: backend exposes method(s) implying "
                   f"action(s) {under_declared!r}, not declared",
        ))
    over_declared = sorted(
        action for action in module.actions
        if real_methods and action != "view" and action not in required_actions
    )
    if over_declared:
        findings.append(SemanticFinding(
            code="ux_spec_action_over_declared", path=_UX_SPEC_PATH,
            detail=f"module {module.name!r}: declares action(s) {over_declared!r} but "
                   "the real backend exposes no matching method for them -- "
                   "frontend_forms would build a real UI and client call pointing at "
                   "an endpoint that does not exist. Remove the action, or add the "
                   "matching route to backend_contract for the next candidate",
        ))
    if any(action in ("create", "edit") for action in module.actions) and not module.forms:
        findings.append(SemanticFinding(
            code="ux_spec_action_without_form", path=_UX_SPEC_PATH,
            detail=f"module {module.name!r} declares a create/edit action but no form",
        ))
    return findings


def _module_navigation_findings(
    module: _UxModuleSpec, declared_labels: set[str]
) -> list[SemanticFinding]:
    if module.navigation_label in declared_labels:
        return []
    return [SemanticFinding(
        code="ux_spec_navigation_incomplete", path=_UX_SPEC_PATH,
        detail=f"module {module.name!r}'s navigation_label "
               f"{module.navigation_label!r} is not listed in navigation_destinations",
    )]


def _declared_navigation_labels(spec: _ProductUxSpec) -> set[str]:
    labels = set(spec.navigation_destinations)
    if spec.dashboard is not None:
        labels.add(spec.dashboard.navigation_label)
    return labels


def _repair_flat_ux_spec_envelope(stage_name: str, raw_json: str) -> str | None:
    """golden-work-093/094 (session evidence, frozen, byte-identical
    failure reproduced on two independent candidates): a real
    qwen2.5-coder:14b reliably wrote this stage's own `_ProductUxSpec`
    fields (`product_title`/`primary_roles`/`modules`/
    `navigation_destinations`/`design_system`) directly at the JSON top
    level -- a real, valid `_ProductUxSpec` by this module's own schema --
    instead of nesting that same content as a string inside the generic
    stage envelope (`{"files": {"product/ux_spec.json": "..."}}`) every
    stage's own prompt (`stage_prompting._stage_prompt`'s
    `output_contract`) explicitly documents. Proven by actually validating
    the raw JSON against `_ProductUxSpec` itself, not by guessing at field
    names, so this can never misfire on an unrelated stage's own different
    contract violation. Returns `None` (no repair) for every other stage
    and every shape that does not itself validate as a real spec."""
    if stage_name != "product_ux_spec":
        return None
    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict) or "files" in parsed:
        return None
    try:
        _ProductUxSpec.model_validate(parsed)
    except ValidationError:
        return None
    return json.dumps({"files": {_UX_SPEC_PATH: json.dumps(parsed)}})


def _ux_spec_stage_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`product_ux_spec`'s own narrow rule: the JSON parses against the real
    schema, every backend-declared data model has a corresponding module
    (no declared backend capability is planned into invisibility), no
    module names a model the backend never declared, and a module never
    under-claims a mutating action the real backend exposes a method for."""
    spec, findings = _parse_ux_spec(files)
    if spec is None:
        return findings

    findings = findings + _module_parity_findings(spec, files)
    resource_methods = _backend_methods_by_resource(files)
    declared_labels = _declared_navigation_labels(spec)
    for module in spec.modules:
        findings += _module_action_findings(module, resource_methods)
        findings += _module_navigation_findings(module, declared_labels)
    return findings


__all__ = [
    "_parse_ux_spec", "_ux_spec_stage_findings", "_backend_declared_models",
    "_repair_flat_ux_spec_envelope",
]
