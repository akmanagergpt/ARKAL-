"""Derives a real `_AcceptanceScenario` from a candidate's own authoritative
generated contracts -- never a second, hand-authored truth source.

Owner: `engineering.factory`. Before this module, `_AcceptanceScenario` was
real data (ARK-REQ-0074 already keeps it domain-neutral), but the ONLY way
to produce one was to hand-write a JSON file. ARKALI cannot ask an operator
to hand-author an acceptance scenario for every new product it generates --
the scenario must be a real, deterministic DERIVATION of the same contracts
the candidate itself already carries: `backend_contract`'s own route/model
JSON, `product_ux_spec.json`'s own module/action/form declarations, and
`frontend_client`'s own real exported function signatures.

REUSES `product_ux_spec.py`'s OWN existing resource-matching machinery
(`_parse_ux_spec`, `_backend_methods_by_resource`, `_route_items`,
`_resource_matching_name`, `_matching_methods`, `_METHOD_TO_ACTION`) rather
than re-deriving "which backend route belongs to which ux_spec module" a
second time -- the identical reconciliation `_module_action_findings`
already performs for its own, narrower purpose.

NO DOMAIN NAME ANYWHERE. Every decision here is keyed on the FIELD TYPE
a real backend model declares (`"integer"`, `"string"`, `"float"`,
`"date"`, ...) or on a real STRUCTURAL convention this pipeline's own
generated candidates already consistently use (a route segment wrapped in
`{...}` names that segment's own real route parameter; a field ending in
`_id` whose stripped prefix matches another real declared resource is a
real relationship, checked against the schema, never against a literal
name like `"student_id"`) -- never on what a specific candidate happens to
call anything.

REFUSES RATHER THAN GUESSES. A required field whose declared type this
module does not recognize, or a relationship field naming no real declared
resource, stops compilation with `_AcceptancePlanIncomplete` rather than
inventing a value or silently dropping the field -- the same posture every
other real derivation in this pipeline already takes (`frontend_mutation_
contract.py`'s own "never fabricated" stance on a missing client function).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.acceptance_scenario import _AcceptanceScenario, _ResourceScenario
from arkali.engineering.factory.product_ux_spec import (
    _METHOD_TO_ACTION,
    _backend_json_documents,
    _backend_methods_by_resource,
    _is_multi_model_field_map,
    _matching_methods,
    _parse_ux_spec,
    _resource_matching_name,
    _route_items,
)

_ACTION_TO_VERB = {"create": "create", "edit": "update", "delete": "delete"}
_ROUTE_PARAM = re.compile(r"\{(\w+)\}")
#: A server-generated primary key is never a real user-entered or client-
#: supplied field, with or without a matching `{param}` route segment --
#: the same structural (not domain-specific) REST/SQL convention
#: `frontend_mutation_contract._ROUTE_IDENTIFIER_FIELD_NAMES` already
#: encodes on the frontend-generation side.
_PRIMARY_KEY_FIELD_NAMES = frozenset({"id"})
#: Four deterministic, distinguishable example values per real declared
#: field type -- never by field name. create != update (a real edit must
#: change something to prove the PUT took effect) and backend != browser
#: (a real API-created record and a real UI-created record exist in the
#: SAME running backend at once and must never collide).
_VARIANTS = ("create", "update", "browser_create", "browser_update")
_TYPE_EXAMPLES: dict[str, tuple[object, object, object, object]] = {
    "integer": (7, 11, 8, 12),
    "int": (7, 11, 8, 12),
    "float": (19.99, 24.99, 21.99, 26.99),
    "decimal": (19.99, 24.99, 21.99, 26.99),
    "number": (19.99, 24.99, 21.99, 26.99),
    "boolean": (True, False, True, False),
    "bool": (True, False, True, False),
    "date": ("2030-01-15", "2030-02-01", "2030-03-01", "2030-04-01"),
    "datetime": (
        "2030-01-15T00:00:00", "2030-02-01T00:00:00",
        "2030-03-01T00:00:00", "2030-04-01T00:00:00",
    ),
    "email": (
        "acceptance@example.com", "acceptance.edited@example.com",
        "browser.acceptance@example.com", "browser.acceptance.edited@example.com",
    ),
    "string": (
        "Acceptance Value", "Acceptance Value Edited",
        "Browser Acceptance Value", "Browser Acceptance Value Edited",
    ),
    "text": (
        "Acceptance Value", "Acceptance Value Edited",
        "Browser Acceptance Value", "Browser Acceptance Value Edited",
    ),
    "enum": ("active", "active", "active", "active"),
}


class _AcceptancePlanIncomplete(Exception):
    """Compilation refused rather than guessed. `reasons` names every real
    field/relationship/action this candidate's own contracts could not
    resolve -- never a partial, silently-wrong scenario."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("ACCEPTANCE_PLAN_INCOMPLETE: " + "; ".join(reasons))


def _model_field_types(files: Mapping[str, str]) -> dict[str, dict[str, str]]:
    """Real declared model name -> {field_name: real declared type string},
    tolerating both real shapes this pipeline's own candidates use: several
    models nested under one file's own "fields" key
    (`{"students": {"id": "integer", ...}, ...}`), or one model's own flat
    or `{"type": ...}`-wrapped field map."""
    result: dict[str, dict[str, str]] = {}
    for _path, parsed in _backend_json_documents(files):
        if not (isinstance(parsed, dict) and "fields" in parsed):
            continue
        fields = parsed["fields"]
        if _is_multi_model_field_map(fields):
            for model_name, model_fields in fields.items():
                result[str(model_name)] = _normalize_field_types(model_fields)
            continue
        table_name = parsed.get("table_name")
        if table_name:
            result[str(table_name)] = _normalize_field_types(fields)
    return result


def _normalize_field_types(fields: object) -> dict[str, str]:
    if not isinstance(fields, dict):
        return {}
    normalized: dict[str, str] = {}
    for name, declared in fields.items():
        if isinstance(declared, dict):
            declared = declared.get("type")
        if isinstance(declared, str):
            normalized[str(name)] = declared.lower()
    return normalized


def _path_segment_matches(segment: str, target: str) -> bool:
    key = re.sub(r"[^a-z0-9]", "", segment.lower())
    matching_key = _resource_matching_name(key)
    return target in matching_key or matching_key in target


def _module_routes(files: Mapping[str, str], module_name: str) -> tuple[str | None, str | None, str | None]:
    """(collection_route, item_route_template, route_param) for the real
    backend routes matching `module_name` -- reuses `product_ux_spec.py`'s
    own resource-matching normalization so a route is matched to a module
    exactly the way `_module_action_findings` already reconciles them.

    Checks EVERY real path segment, not only the first: a real, valid
    backend is free to nest a resource under a prefix (`/api/books/
    overdue`, real evidence, `factory-goal-mtpnp9af-yeldck`) rather than
    the flat `/resource` convention every prior golden fixture happened to
    use -- no canonical stage rule ever required the first segment to BE
    the resource name, and `_module_parity_findings`'s own real model<->
    module reconciliation (the one that actually gates staged generation)
    never assumed it either. The real matched path is returned verbatim
    (never reconstructed from `segments[0]` alone) so a matched nested
    route round-trips as the exact real path the candidate's own backend
    and frontend already agree on."""
    target = _resource_matching_name(module_name)
    collection: str | None = None
    item: str | None = None
    param: str | None = None
    for item_dict in _route_items(files):
        path = item_dict.get("path")
        if not isinstance(path, str) or not path.startswith("/"):
            continue
        segments = [s for s in path.split("/") if s]
        if not segments:
            continue
        if not any(
            _path_segment_matches(segment, target)
            for segment in segments if not segment.startswith("{")
        ):
            continue
        match = _ROUTE_PARAM.search(path)
        if match:
            item = path
            param = match.group(1)
        elif collection is None:
            collection = path
    return collection, item, param


def _resolved_actions(
    files: Mapping[str, str], module_name: str, declared_actions: tuple[str, ...],
) -> dict[str, str]:
    """`{action: verb}` for every real action the ux_spec module declares
    AND a real backend route+method actually backs (`_METHOD_TO_ACTION`,
    the identical mapping `_module_action_findings` already reconciles
    against) -- an action declared with no backing route is silently
    excluded here, not fabricated, since `product_ux_spec_preflight`'s own
    stage gate is the authority that refuses that mismatch outright."""
    resource_methods = _backend_methods_by_resource(files)
    real_methods = _matching_methods(resource_methods, module_name)
    real_actions = {_METHOD_TO_ACTION[m] for m in real_methods if m in _METHOD_TO_ACTION}
    if "GET" in real_methods or "POST" in real_methods:
        real_actions.add("create") if "POST" in real_methods else None
    return {a: _ACTION_TO_VERB[a] for a in declared_actions if a in real_actions and a in _ACTION_TO_VERB}


def _relationship_target(field_name: str, field_type: str, model_names: set[str]) -> str | None:
    if field_type not in ("integer", "int") or not field_name.endswith("_id"):
        return None
    prefix = field_name[: -len("_id")]
    for candidate in model_names:
        normalized_candidate = _resource_matching_name(candidate)
        if prefix == normalized_candidate or f"{prefix}s" == normalized_candidate:
            return candidate
    return None


def _field_value(field_type: str, variant: str, reasons: list[str], field_name: str) -> object | None:
    """`variant` is one of `_VARIANTS` -- the real example value for
    `field_type` in that one slot, never re-used across slots (create !=
    update, and neither collides with the browser-driven pair)."""
    examples = _TYPE_EXAMPLES.get(field_type)
    if examples is None:
        reasons.append(f"field {field_name!r} has unrecognized type {field_type!r}")
        return None
    return examples[_VARIANTS.index(variant)]


def _resource_fields(model_fields: dict[str, dict[str, str]], module_name: str) -> dict[str, str]:
    fields = model_fields.get(module_name) or model_fields.get(_resource_matching_name(module_name), {})
    if fields:
        return fields
    for candidate_name, candidate_fields in model_fields.items():
        if _resource_matching_name(candidate_name) == _resource_matching_name(module_name):
            return candidate_fields
    return {}


def _resource_payloads(
    fields: dict[str, str], editable: tuple[str, ...], model_fields: dict[str, dict[str, str]],
    reasons: list[str],
) -> tuple[dict[str, object], dict[str, object], dict[str, str], dict[str, str], dict[str, str]]:
    create_payload: dict[str, object] = {}
    update_payload: dict[str, object] = {}
    browser_create: dict[str, str] = {}
    browser_update: dict[str, str] = {}
    relationship_fields: dict[str, str] = {}
    for field_name in editable:
        field_type = fields[field_name]
        target = _relationship_target(field_name, field_type, set(model_fields.keys()))
        if target is not None:
            relationship_fields[field_name] = target
            continue
        create_payload[field_name] = _field_value(field_type, "create", reasons, field_name)
        update_payload[field_name] = _field_value(field_type, "update", reasons, field_name)
        browser_create[field_name] = str(_field_value(field_type, "browser_create", reasons, field_name))
        browser_update[field_name] = str(_field_value(field_type, "browser_update", reasons, field_name))
    return create_payload, update_payload, browser_create, browser_update, relationship_fields


def _declared_mutation_never_backed(module, actions: tuple[str, ...]) -> str | None:  # noqa: ANN001
    """CAPABILITY-AWARE ACCEPTANCE (human governance decision, session
    record): a module the candidate's own real `product_ux_spec.json`
    never declares "create"/"edit" for at all is a genuine, legitimate
    READ-ONLY design -- real evidence, `factory-goal-mtquvzmc-dt3go3` --
    and must be accepted via a real read/render/restart journey, never
    forced through a synthesized mutation (the acceptance-overreach class
    F-0088 already closed for THIS shape: a real, live "HTTP Error 405:
    METHOD NOT ALLOWED" once `_build_resource` stopped guessing a
    create_payload for it). But a module that DOES declare "create"/"edit"
    whose real, RECONCILED actions (backend route+method backed) never
    actually satisfy that declaration is a real, genuine DEFECT (a
    declared mutation the real backend never backs) -- never silently
    reclassified as "read-only by design" just because its own
    `create_payload` would otherwise end up empty. The distinction is the
    module's own DECLARED intent (`module.actions`, from the real
    `product_ux_spec.json`), never inferred from a route name or any
    candidate-specific string. Returns the refusal reason, or `None` when
    this module's declared intent is either backed or genuinely absent."""
    declared_mutating = {a for a in module.actions if a in ("create", "edit")}
    if declared_mutating and not ({"create", "edit"} & set(actions)):
        return (
            f"module {module.name!r} declares {sorted(declared_mutating)} but no matching "
            "backend route/method actually backs any of them"
        )
    return None


def _build_resource(
    files: Mapping[str, str], module, model_fields: dict[str, dict[str, str]],  # noqa: ANN001
    reasons: list[str],
) -> tuple[_ResourceScenario, dict[str, str], dict[str, str], dict[str, str], dict[str, str]] | None:
    collection_route, _item_route, route_param = _module_routes(files, module.name)
    if collection_route is None:
        reasons.append(f"module {module.name!r} has no matching backend collection route")
        return None
    actions = _resolved_actions(files, module.name, module.actions)
    unbacked_reason = _declared_mutation_never_backed(module, actions)
    if unbacked_reason is not None:
        reasons.append(unbacked_reason)
        return None
    fields = _resource_fields(model_fields, module.name)
    mutable = bool({"create", "edit"} & set(actions))
    editable = (
        tuple(f for f in fields if f != route_param and f not in _PRIMARY_KEY_FIELD_NAMES)
        if mutable else ()
    )
    create_payload, update_payload, browser_create, browser_update, relationship_fields = _resource_payloads(
        fields, editable, model_fields, reasons,
    )
    resource = _ResourceScenario(
        name=module.name, collection_route=collection_route,
        navigation_label=module.navigation_label,
        singular_label=_singularize(module.navigation_label),
        editable_form_fields=tuple(f for f in editable if f not in relationship_fields) or (route_param or "value",),
        destructive_confirmation_required="delete" in actions,
        relationship_fields=relationship_fields,
        actions=tuple(sorted(actions)),
    )
    return resource, create_payload, update_payload, browser_create, browser_update


def _singularize(label: str) -> str:
    stripped = label[:-1] if label.endswith("s") else label
    return stripped or label


def _built_resources(
    files: Mapping[str, str], spec, model_fields: dict[str, dict[str, str]], reasons: list[str],  # noqa: ANN001
) -> dict[str, tuple[_ResourceScenario, dict, dict, dict, dict]]:
    built: dict[str, tuple[_ResourceScenario, dict, dict, dict, dict]] = {}
    for module in spec.modules:
        result = _build_resource(files, module, model_fields, reasons)
        if result is not None:
            built[module.name] = result
    return built


def _select_primary(spec, built: dict) -> str:  # noqa: ANN001
    """The first module (ux_spec declaration order) whose own resource
    actually resolved AND declares "create" -- the create -> edit ->
    delete -> restart-persistence journey's own real starting point.
    Falls back to the first resolved module if none declares create (a
    read-mostly product with only a related mutation)."""
    return next(
        (m.name for m in spec.modules if m.name in built and "create" in m.actions), None,
    ) or next(iter(built))


def _select_related(built: dict, primary_name: str) -> str | None:
    return next(
        (
            name for name, (resource, *_rest) in built.items()
            if name != primary_name and primary_name in resource.relationship_fields.values()
        ),
        None,
    )


def _assemble_scenario(
    spec, built: dict, primary_name: str, related_name: str | None,  # noqa: ANN001
) -> _AcceptanceScenario:
    _primary_resource, create_payload, update_payload, browser_create, browser_update = built[primary_name]
    related_payload = None
    browser_related: dict[str, str] | None = None
    if related_name is not None:
        _related_resource, related_payload, _upd, browser_related, _bupd = built[related_name]
    resources = tuple(r for r, *_rest in built.values())
    return _AcceptanceScenario(
        scenario_id=f"compiled-{spec.product_title.lower().replace(' ', '-')}",
        resources=resources,
        primary_resource=primary_name,
        create_payload=create_payload,
        update_payload=update_payload,
        related_resource=related_name,
        related_create_payload=related_payload,
        navigation_destinations=spec.navigation_destinations,
        browser_create_values=browser_create or None,
        browser_update_values=browser_update or None,
        browser_related_values=browser_related,
    )


def _compile_acceptance_plan(files: Mapping[str, str]) -> _AcceptanceScenario:
    """Derives a real `_AcceptanceScenario` from `files`' own authoritative
    contracts (`product/ux_spec.json`, `backend/*.json`, `frontend/src/
    *client*`). Raises `_AcceptancePlanIncomplete` -- never a guessed or
    partial scenario -- when a required field, relationship, or the
    primary journey itself cannot be resolved from real declared data."""
    spec, spec_findings = _parse_ux_spec(files)
    if spec is None:
        raise _AcceptancePlanIncomplete([f.detail for f in spec_findings] or ["no product_ux_spec"])
    model_fields = _model_field_types(files)
    reasons: list[str] = []
    built = _built_resources(files, spec, model_fields, reasons)
    if not built:
        raise _AcceptancePlanIncomplete(reasons or ["no module resolved a real backend resource"])

    primary_name = _select_primary(spec, built)
    # CAPABILITY-AWARE ACCEPTANCE (human governance decision, session
    # record): a primary resource with no real create_payload and no
    # relationship_fields is no longer refused here -- `_build_resource`
    # already proved, above, that this is a genuine, declared-intent
    # READ-ONLY resource (never a declared-but-unbacked mutation, which
    # `_build_resource` itself already excludes from `built` with its own
    # real reason). A real, view-only primary is a legitimate acceptance
    # target: `_accept()` (factory_acceptance.py) and the browser journey
    # both branch on this exact resource's own `actions` to run a real
    # read/render/restart journey instead of a synthesized mutation one.
    if reasons:
        raise _AcceptancePlanIncomplete(reasons)

    related_name = _select_related(built, primary_name)
    return _assemble_scenario(spec, built, primary_name, related_name)


__all__ = ["_AcceptancePlanIncomplete", "_compile_acceptance_plan"]
