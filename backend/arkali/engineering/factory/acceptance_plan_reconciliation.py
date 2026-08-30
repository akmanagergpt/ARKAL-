"""Checks a hand-authored `--scenario` override against a candidate's own
authoritative contracts -- never taken on faith just because an operator
supplied it.

Owner: `engineering.factory`. `acceptance_plan_compiler._compile_acceptance_
plan` is the default, DERIVED path; `run_golden_acceptance.py --scenario`
remains an explicit override/test-fixture path (e.g. `golden/scenarios/
student_fee_management.json` as a regression oracle). An override that no
longer matches the candidate it is pointed at -- an unknown route, a wrong
route parameter, an unknown schema field, an unknown navigation
destination, or a create/edit claim the real backend does not back -- must
be REJECTED, not silently run. `_reconcile_scenario` performs that check
against the SAME real route/schema/navigation facts `_compile_
acceptance_plan` itself derives from (`_module_routes`, `_model_field_
types`, `_resolved_actions`), never a second, independent notion of
correctness.

Split out of `acceptance_plan_compiler.py` on line-budget grounds
(AUTHORITY_MAP.yaml architecture_budgets, ADR-0008): compilation
(derivation) and reconciliation (verification of a foreign scenario) are
two real, separately testable concerns sharing the same underlying
contract-reading helpers, not one.
"""

from __future__ import annotations

from collections.abc import Mapping

from arkali.engineering.factory.acceptance_plan_compiler import (
    _model_field_types,
    _module_routes,
    _resolved_actions,
)
from arkali.engineering.factory.acceptance_scenario import _AcceptanceScenario, _ResourceScenario
from arkali.engineering.factory.product_ux_spec import _parse_ux_spec, _resource_matching_name


def _reconciled_routes(files: Mapping[str, str], resource: _ResourceScenario) -> list[str]:
    collection_route, _item_route, route_param = _module_routes(files, resource.name)
    if collection_route is None:
        return [f"resource {resource.name!r} has no matching real backend route"]
    reasons = []
    if collection_route != resource.collection_route:
        reasons.append(
            f"resource {resource.name!r} declares collection_route "
            f"{resource.collection_route!r} but the real backend route is {collection_route!r}",
        )
    actions = _resolved_actions(files, resource.name, ("create", "edit", "delete"))
    if resource.destructive_confirmation_required and "delete" not in actions:
        reasons.append(
            f"resource {resource.name!r} requires destructive confirmation but the real "
            "backend exposes no DELETE route for it",
        )
    if route_param is None and resource.destructive_confirmation_required:
        reasons.append(f"resource {resource.name!r} has no real item route parameter to delete by")
    return reasons


def _reconciled_fields(files: Mapping[str, str], resource: _ResourceScenario) -> list[str]:
    model_fields = _model_field_types(files)
    fields = model_fields.get(resource.name) or {}
    if not fields:
        for candidate_name, candidate_fields in model_fields.items():
            if _resource_matching_name(candidate_name) == _resource_matching_name(resource.name):
                fields = candidate_fields
                break
    reasons = []
    for field_name in resource.editable_form_fields:
        if field_name in fields or field_name in resource.relationship_fields:
            continue
        reasons.append(
            f"resource {resource.name!r} editable field {field_name!r} is not a real "
            "declared backend model field",
        )
    for field_name, target in resource.relationship_fields.items():
        if target not in model_fields:
            reasons.append(
                f"resource {resource.name!r} relationship field {field_name!r} names "
                f"{target!r}, which is not a real declared backend model",
            )
    return reasons


def _reconciled_payload(
    scenario: _AcceptanceScenario, resource_name: str, payload: Mapping[str, object] | None, label: str,
) -> list[str]:
    if payload is None:
        return []
    resource = next((r for r in scenario.resources if r.name == resource_name), None)
    if resource is None:
        return []
    allowed = set(resource.editable_form_fields) | set(resource.relationship_fields)
    return [
        f"{label} field {key!r} is not declared editable for resource {resource_name!r}"
        for key in payload if key not in allowed
    ]


def _reconciled_navigation(scenario: _AcceptanceScenario, spec) -> list[str]:  # noqa: ANN001
    nav = set(spec.navigation_destinations)
    return [
        f"navigation destination {dest!r} is not declared by product_ux_spec"
        for dest in scenario.navigation_destinations if dest not in nav
    ]


def _reconciled_resource_names(scenario: _AcceptanceScenario) -> list[str]:
    resource_names = {r.name for r in scenario.resources}
    reasons = []
    if scenario.primary_resource not in resource_names:
        reasons.append(f"primary_resource {scenario.primary_resource!r} names no scenario resource")
    if scenario.related_resource is not None and scenario.related_resource not in resource_names:
        reasons.append(f"related_resource {scenario.related_resource!r} names no scenario resource")
    return reasons


def _reconciled_primary_actions(files: Mapping[str, str], scenario: _AcceptanceScenario) -> list[str]:
    resource_names = {r.name for r in scenario.resources}
    if scenario.primary_resource not in resource_names:
        return []
    primary_actions = _resolved_actions(files, scenario.primary_resource, ("create", "edit"))
    reasons = []
    if "create" not in primary_actions:
        reasons.append(
            f"primary resource {scenario.primary_resource!r} has a create_payload but the "
            "real backend exposes no POST route for it",
        )
    if "edit" not in primary_actions:
        reasons.append(
            f"primary resource {scenario.primary_resource!r} has an update_payload but the "
            "real backend exposes no PUT/PATCH route for it",
        )
    return reasons


def _reconcile_scenario(scenario: _AcceptanceScenario, files: Mapping[str, str]) -> list[str]:
    """Every real reason a hand-authored `--scenario` override is
    incompatible with `files`' own authoritative contracts -- checked
    against the SAME real route/schema/navigation facts
    `acceptance_plan_compiler._compile_acceptance_plan` itself derives
    from, never a second, independent notion of correctness. `[]` means
    fully compatible; a manually-authored scenario is never taken on faith
    otherwise.

    Known narrower-than-`_compile_acceptance_plan` limitation: a backend
    schema this pipeline generates never declares a field "required" as
    its own concept (`_normalize_field_types` only ever records a type),
    so a scenario payload silently omitting a real field cannot be flagged
    here -- an extra/unknown field, an unknown route, a wrong route
    parameter, an unknown relationship target, and an unbacked
    create/edit/delete network operation all can be, and are.
    """
    spec, spec_findings = _parse_ux_spec(files)
    if spec is None:
        return [f.detail for f in spec_findings] or ["no product_ux_spec"]

    reasons: list[str] = []
    reasons.extend(_reconciled_navigation(scenario, spec))
    reasons.extend(_reconciled_resource_names(scenario))
    for resource in scenario.resources:
        reasons.extend(_reconciled_routes(files, resource))
        reasons.extend(_reconciled_fields(files, resource))
    reasons.extend(_reconciled_primary_actions(files, scenario))
    reasons.extend(_reconciled_payload(scenario, scenario.primary_resource, scenario.create_payload, "create_payload"))
    reasons.extend(_reconciled_payload(scenario, scenario.primary_resource, scenario.update_payload, "update_payload"))
    if scenario.related_resource is not None:
        reasons.extend(_reconciled_payload(
            scenario, scenario.related_resource, scenario.related_create_payload, "related_create_payload",
        ))
    return reasons


__all__ = ["_reconcile_scenario"]
