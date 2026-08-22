from __future__ import annotations

import json

from arkali.engineering.factory.product_ux_spec import _parse_ux_spec, _ux_spec_stage_findings

#: A deliberately non-Dershane, non-Golden-Product domain (e-commerce) --
#: proving these checks generalize rather than encoding one product's
#: answer key.
_BACKEND_FILES = {
    "backend/products_model.json": json.dumps(
        {"table_name": "products", "fields": {"id": {"type": "integer"}, "name": {"type": "string"}}}
    ),
    "backend/categories_model.json": json.dumps(
        {"table_name": "categories", "fields": {"id": {"type": "integer"}}}
    ),
    "backend/orders_model.json": json.dumps(
        {"table_name": "orders", "fields": {"id": {"type": "integer"}}}
    ),
    "backend/routes.json": json.dumps([
        {"path": "/products", "method": "GET"},
        {"path": "/products", "method": "POST"},
        {"path": "/categories", "method": "GET"},
        {"path": "/orders", "method": "GET"},
        {"path": "/orders", "method": "POST"},
        {"path": "/orders", "method": "DELETE"},
    ]),
}


def _module(name: str, actions: list[str], *, forms: list[dict] | None = None) -> dict:
    return {
        "name": name, "navigation_label": name.capitalize(), "presentation": "table",
        "actions": actions, "forms": forms or [],
        "states": {"loading": True, "empty": True, "error": True, "success": bool(actions)},
    }


_DESIGN_SYSTEM = {
    "typography_scale": ["base"], "spacing_scale": ["sm"],
    "component_conventions": ["table"], "responsive": "desktop-first",
    "accessible_focus_contrast": True,
}


def _valid_spec_files() -> dict[str, str]:
    spec = {
        "product_title": "Shop", "primary_roles": ["staff"],
        "modules": [
            _module("products", ["create", "view"], forms=[{"name": "ProductForm", "fields": ["name"]}]),
            _module("categories", ["view"]),
            _module("orders", ["create", "delete", "view"], forms=[{"name": "OrderForm", "fields": ["item"]}]),
        ],
        "navigation_destinations": ["Products", "Categories", "Orders", "Dashboard"],
        "dashboard": {"navigation_label": "Dashboard", "purpose": "overview", "kpis": ["Total Orders"]},
        "design_system": _DESIGN_SYSTEM,
        "destructive_action_confirmation": True,
    }
    return {**_BACKEND_FILES, "product/ux_spec.json": json.dumps(spec)}


def test_a_complete_reconciling_spec_passes() -> None:
    findings = _ux_spec_stage_findings(_valid_spec_files())
    assert findings == []


def test_missing_spec_file_is_refused() -> None:
    findings = _ux_spec_stage_findings(dict(_BACKEND_FILES))
    assert [f.code for f in findings] == ["ux_spec_missing"]


def test_invalid_json_is_refused() -> None:
    files = {**_BACKEND_FILES, "product/ux_spec.json": "{not json"}
    findings = _ux_spec_stage_findings(files)
    assert [f.code for f in findings] == ["ux_spec_invalid"]


def test_a_module_for_a_model_the_backend_never_declared_is_refused() -> None:
    files = _valid_spec_files()
    spec = json.loads(files["product/ux_spec.json"])
    spec["modules"].append(_module("invoices", ["view"]))
    spec["navigation_destinations"].append("Invoices")
    files["product/ux_spec.json"] = json.dumps(spec)
    findings = _ux_spec_stage_findings(files)
    assert any(f.code == "ux_spec_invented_module" for f in findings)


def test_a_backend_declared_model_missing_from_the_spec_is_refused() -> None:
    files = _valid_spec_files()
    spec = json.loads(files["product/ux_spec.json"])
    spec["modules"] = [m for m in spec["modules"] if m["name"] != "categories"]
    files["product/ux_spec.json"] = json.dumps(spec)
    findings = _ux_spec_stage_findings(files)
    assert any(f.code == "ux_spec_missing_module" for f in findings)


def test_a_module_under_declaring_a_real_backend_action_is_refused() -> None:
    """The backend exposes POST /products (real create capability); a spec
    that only declares "view" for the products module under-claims it."""
    files = _valid_spec_files()
    spec = json.loads(files["product/ux_spec.json"])
    for module in spec["modules"]:
        if module["name"] == "products":
            module["actions"] = ["view"]
    files["product/ux_spec.json"] = json.dumps(spec)
    findings = _ux_spec_stage_findings(files)
    assert any(f.code == "ux_spec_action_under_declared" for f in findings)


def test_a_create_action_with_no_form_is_refused() -> None:
    files = _valid_spec_files()
    spec = json.loads(files["product/ux_spec.json"])
    for module in spec["modules"]:
        if module["name"] == "products":
            module["forms"] = []
    files["product/ux_spec.json"] = json.dumps(spec)
    findings = _ux_spec_stage_findings(files)
    assert any(f.code == "ux_spec_action_without_form" for f in findings)


def test_a_navigation_label_missing_from_destinations_is_refused() -> None:
    files = _valid_spec_files()
    spec = json.loads(files["product/ux_spec.json"])
    spec["navigation_destinations"] = ["Products", "Categories", "Dashboard"]  # Orders dropped
    files["product/ux_spec.json"] = json.dumps(spec)
    findings = _ux_spec_stage_findings(files)
    assert any(f.code == "ux_spec_navigation_incomplete" for f in findings)


def test_a_genuinely_single_purpose_product_needs_no_dashboard() -> None:
    """A one-module product with a read-only module and no dashboard is a
    legal, complete spec -- nothing here forces an enterprise shell onto a
    simple product."""
    backend = {
        "backend/notes_model.json": json.dumps(
            {"table_name": "notes", "fields": {"id": {"type": "integer"}}}
        ),
        "backend/routes.json": json.dumps([{"path": "/notes", "method": "GET"}]),
    }
    spec = {
        "product_title": "Notes", "primary_roles": ["user"],
        "modules": [_module("notes", ["view"])],
        "navigation_destinations": ["Notes"],
        "design_system": _DESIGN_SYSTEM,
    }
    files = {**backend, "product/ux_spec.json": json.dumps(spec)}
    assert _ux_spec_stage_findings(files) == []
    spec_obj, parse_findings = _parse_ux_spec(files)
    assert parse_findings == []
    assert spec_obj is not None and spec_obj.dashboard is None
