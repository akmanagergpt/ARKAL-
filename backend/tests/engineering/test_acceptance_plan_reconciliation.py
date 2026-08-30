from __future__ import annotations

import json

from arkali.engineering.factory.acceptance_plan_compiler import _compile_acceptance_plan
from arkali.engineering.factory.acceptance_plan_reconciliation import _reconcile_scenario
from arkali.engineering.factory.acceptance_scenario import _AcceptanceScenario, _ResourceScenario

_DESIGN_SYSTEM = {
    "typography_scale": ["14px", "16px", "24px"],
    "spacing_scale": ["4px", "8px", "16px"],
    "component_conventions": ["primary buttons are filled"],
}


def _ux_spec(modules: list[dict], navigation_destinations: list[str]) -> str:
    return json.dumps({
        "product_title": "Test Product", "primary_roles": ["Operator"], "modules": modules,
        "navigation_destinations": navigation_destinations, "design_system": _DESIGN_SYSTEM,
    })


def _module(name: str, label: str, actions: list[str], fields: list[str]) -> dict:
    return {
        "name": name, "navigation_label": label, "presentation": "table",
        "actions": actions, "forms": [{"name": f"{label}Form", "fields": fields}],
    }


def _routes(*items: tuple[str, str]) -> str:
    return json.dumps([{"path": path, "method": method} for path, method in items])


def _models(fields: dict[str, dict[str, str]]) -> str:
    return json.dumps({"fields": fields})


def _widget_files() -> dict[str, str]:
    return {
        "product/ux_spec.json": _ux_spec(
            [_module("widgets", "Widgets", ["create", "edit", "delete"], ["id", "name", "price"])],
            ["Widgets"],
        ),
        "backend/routes.json": _routes(
            ("/widgets", "GET"), ("/widgets", "POST"),
            ("/widgets/{id}", "PUT"), ("/widgets/{id}", "DELETE"),
        ),
        "backend/data_model.json": _models({"widgets": {"id": "integer", "name": "string", "price": "float"}}),
    }


def _widget_resource(**overrides: object) -> _ResourceScenario:
    fields = {
        "name": "widgets", "collection_route": "/widgets", "navigation_label": "Widgets",
        "singular_label": "Widget", "editable_form_fields": ("name", "price"),
        "destructive_confirmation_required": True, "relationship_fields": {},
    }
    fields.update(overrides)
    return _ResourceScenario(**fields)


def _widget_scenario(**resource_overrides: object) -> _AcceptanceScenario:
    return _AcceptanceScenario(
        scenario_id="hand-authored", resources=(_widget_resource(**resource_overrides),),
        primary_resource="widgets", create_payload={"name": "A", "price": 1.0},
        update_payload={"name": "B", "price": 2.0}, navigation_destinations=("Widgets",),
    )


class TestReconciliationAcceptsAValidOverride:
    def test_a_scenario_shaped_exactly_like_the_real_contracts_reconciles_cleanly(self) -> None:
        assert _reconcile_scenario(_widget_scenario(), _widget_files()) == []

    def test_the_compiler_own_output_always_reconciles_against_its_own_source(self) -> None:
        files = _widget_files()
        scenario = _compile_acceptance_plan(files)
        assert _reconcile_scenario(scenario, files) == []


class TestReconciliationRejectsAnIncompatibleOverride:
    def test_an_unknown_route_is_rejected(self) -> None:
        scenario = _widget_scenario(name="gizmos", collection_route="/gizmos")
        reasons = _reconcile_scenario(scenario, _widget_files())
        assert any("gizmos" in r and "no matching real backend route" in r for r in reasons)

    def test_a_wrong_collection_route_is_rejected(self) -> None:
        scenario = _widget_scenario(collection_route="/widget")  # real route is "/widgets"
        reasons = _reconcile_scenario(scenario, _widget_files())
        assert any("collection_route" in r for r in reasons)

    def test_an_unknown_schema_field_is_rejected(self) -> None:
        scenario = _widget_scenario(editable_form_fields=("name", "color"))
        reasons = _reconcile_scenario(scenario, _widget_files())
        assert any("color" in r and "not a real" in r for r in reasons)

    def test_an_unknown_navigation_destination_is_rejected(self) -> None:
        scenario = _AcceptanceScenario(
            scenario_id="hand-authored", resources=(_widget_resource(),),
            primary_resource="widgets", create_payload={"name": "A", "price": 1.0},
            update_payload={"name": "B", "price": 2.0},
            navigation_destinations=("Widgets", "Reports"),
        )
        reasons = _reconcile_scenario(scenario, _widget_files())
        assert any("Reports" in r for r in reasons)

    def test_a_delete_confirmation_with_no_real_delete_route_is_rejected(self) -> None:
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("widgets", "Widgets", ["create", "edit"], ["id", "name", "price"])], ["Widgets"],
            ),
            "backend/routes.json": _routes(
                ("/widgets", "GET"), ("/widgets", "POST"), ("/widgets/{id}", "PUT"),
            ),
            "backend/data_model.json": _models({"widgets": {"id": "integer", "name": "string", "price": "float"}}),
        }
        reasons = _reconcile_scenario(_widget_scenario(), files)
        assert any("DELETE" in r for r in reasons)

    def test_an_unbacked_create_operation_is_rejected(self) -> None:
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("widgets", "Widgets", ["edit", "delete"], ["id", "name", "price"])], ["Widgets"],
            ),
            "backend/routes.json": _routes(
                ("/widgets", "GET"), ("/widgets/{id}", "PUT"), ("/widgets/{id}", "DELETE"),
            ),
            "backend/data_model.json": _models({"widgets": {"id": "integer", "name": "string", "price": "float"}}),
        }
        reasons = _reconcile_scenario(_widget_scenario(), files)
        assert any("no POST route" in r for r in reasons)

    def test_an_unknown_relationship_target_is_rejected(self) -> None:
        scenario = _widget_scenario(relationship_fields={"owner_id": "owners"})
        reasons = _reconcile_scenario(scenario, _widget_files())
        assert any("owners" in r and "not a real declared backend model" in r for r in reasons)

    def test_a_create_payload_field_outside_editable_fields_is_rejected(self) -> None:
        scenario = _AcceptanceScenario(
            scenario_id="hand-authored", resources=(_widget_resource(),),
            primary_resource="widgets", create_payload={"name": "A", "sku": "X"},
            update_payload={"name": "B"}, navigation_destinations=("Widgets",),
        )
        reasons = _reconcile_scenario(scenario, _widget_files())
        assert any("sku" in r and "create_payload" in r for r in reasons)

    def test_a_primary_resource_naming_no_real_scenario_resource_is_rejected(self) -> None:
        scenario = _AcceptanceScenario(
            scenario_id="hand-authored", resources=(_widget_resource(),),
            primary_resource="gadgets", create_payload={"name": "A"},
            update_payload={"name": "B"}, navigation_destinations=("Widgets",),
        )
        reasons = _reconcile_scenario(scenario, _widget_files())
        assert any("gadgets" in r for r in reasons)
