from __future__ import annotations

import json

from arkali.engineering.factory.product_ux_spec import (
    _parse_ux_spec,
    _repair_flat_ux_spec_envelope,
    _ux_spec_stage_findings,
)

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
        "dashboard": {
            "navigation_label": "Dashboard", "purpose": "overview",
            "kpis": [{"name": "Total Orders", "metric": "count_orders"}],
        },
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


def _flat_valid_spec() -> dict:
    """The exact real, valid `_ProductUxSpec` content -- with no `files`
    envelope wrapper around it -- golden-work-093/094 (session evidence,
    frozen, byte-identical failure reproduced on two independent
    candidates) reliably produced at the `product_ux_spec` stage."""
    return {
        "product_title": "Shop", "primary_roles": ["staff"],
        "modules": [_module("products", ["view"])],
        "navigation_destinations": ["Products"],
        "design_system": _DESIGN_SYSTEM,
        "destructive_action_confirmation": True,
    }


def test_repairs_a_flat_spec_at_the_product_ux_spec_stage() -> None:
    raw = json.dumps(_flat_valid_spec())
    repaired = _repair_flat_ux_spec_envelope("product_ux_spec", raw)
    assert repaired is not None
    envelope = json.loads(repaired)
    assert set(envelope) == {"files"}
    rewrapped_spec = json.loads(envelope["files"]["product/ux_spec.json"])
    assert rewrapped_spec == _flat_valid_spec()


def test_repair_is_a_noop_for_a_different_stage() -> None:
    """A flat JSON object matching `_ProductUxSpec`'s own shape is real
    evidence only at `product_ux_spec` -- some other stage's own real,
    unrelated contract violation must never be silently reinterpreted as
    this one."""
    raw = json.dumps(_flat_valid_spec())
    assert _repair_flat_ux_spec_envelope("frontend_ui", raw) is None


def test_repair_is_a_noop_when_files_key_already_present() -> None:
    raw = json.dumps({"files": {"product/ux_spec.json": json.dumps(_flat_valid_spec())}})
    assert _repair_flat_ux_spec_envelope("product_ux_spec", raw) is None


def test_repair_is_a_noop_for_unparseable_json() -> None:
    assert _repair_flat_ux_spec_envelope("product_ux_spec", "{not json") is None


def test_repair_is_a_noop_when_the_flat_shape_does_not_validate_as_a_real_spec() -> None:
    """Proof by real validation against `_ProductUxSpec`, not a guess from
    field names -- an unrelated flat JSON object must never be wrapped and
    accepted as a real ux_spec it never was."""
    raw = json.dumps({"some_other_stage_shape": True})
    assert _repair_flat_ux_spec_envelope("product_ux_spec", raw) is None


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


#: golden-work-064 (session evidence, frozen): the real first attempt at a
#: fresh Student/Fee Management candidate. A real qwen2.5-coder:14b wrote
#: exactly this shape -- one backend/data_model.json with three models
#: nested under its own single "fields" key, not three separate files.
_GOLDEN_WORK_064_DATA_MODEL = json.dumps({
    "fields": {
        "students": {"id": "integer", "name": "string", "email": "string"},
        "courses": {"id": "integer", "name": "string", "description": "string"},
        "payments": {"id": "integer", "student_id": "integer", "amount": "float", "due_date": "date"},
    },
})
_GOLDEN_WORK_064_ROUTES = json.dumps([
    {"path": "/students", "method": "GET"},
    {"path": "/students", "method": "POST"},
    {"path": "/students/{id}", "method": "GET"},
    {"path": "/students/{id}", "method": "PUT"},
    {"path": "/students/{id}", "method": "DELETE"},
    {"path": "/courses", "method": "GET"},
    {"path": "/payments", "method": "POST"},
    {"path": "/payments", "method": "GET"},
])


def test_a_real_nested_multi_model_file_yields_three_real_models() -> None:
    """The bug this regression-proves: `_backend_declared_models` used to
    assume one backend/*.json file declared exactly one model (by its own
    top-level table_name), so this real file -- one file, three real
    nested models -- silently counted as one model named after the file
    itself."""
    from arkali.engineering.factory.product_ux_spec import _backend_declared_models

    files = {"backend/data_model.json": _GOLDEN_WORK_064_DATA_MODEL}
    assert _backend_declared_models(files) == {"students", "courses", "payments"}


def test_a_spec_reconciling_against_the_real_nested_shape_passes() -> None:
    spec = {
        "product_title": "Student Fee Manager", "primary_roles": ["staff"],
        "modules": [
            _module("students", ["create", "edit", "delete", "view"],
                    forms=[{"name": "StudentForm", "fields": ["name", "email"]}]),
            _module("courses", ["view"]),
            _module("payments", ["create", "view"],
                    forms=[{"name": "PaymentForm", "fields": ["amount", "due_date"]}]),
        ],
        "navigation_destinations": ["Students", "Courses", "Payments", "Dashboard"],
        "dashboard": {
            "navigation_label": "Dashboard", "purpose": "overview",
            "kpis": [{"name": "Total Students", "metric": "count_students"}],
        },
        "design_system": {**_DESIGN_SYSTEM, "responsive": True},
    }
    files = {
        "backend/data_model.json": _GOLDEN_WORK_064_DATA_MODEL,
        "backend/routes.json": _GOLDEN_WORK_064_ROUTES,
        "product/ux_spec.json": json.dumps(spec),
    }
    assert _ux_spec_stage_findings(files) == []


def test_a_kpi_object_and_a_boolean_responsive_flag_both_parse() -> None:
    """golden-work-064 (session evidence, frozen): a real qwen2.5-coder:14b
    wrote kpis as {"name": ..., "metric": ...} objects, never bare
    strings, and wrote responsive as a bare boolean, never the
    "desktop-first" strategy string this stage's rule text used to imply
    without ever actually requiring. Both real shapes must parse."""
    spec = {
        "product_title": "Student Fee Manager", "primary_roles": ["staff"],
        "modules": [_module("students", ["view"])],
        "navigation_destinations": ["Students", "Dashboard"],
        "dashboard": {
            "navigation_label": "Dashboard", "purpose": "overview",
            "kpis": [
                {"name": "Total Students", "metric": "count_students"},
                {"name": "Average Payment", "metric": "average_payment_amount"},
            ],
        },
        "design_system": {**_DESIGN_SYSTEM, "responsive": True},
    }
    files = {"product/ux_spec.json": json.dumps(spec)}
    spec_obj, findings = _parse_ux_spec(files)
    assert findings == []
    assert spec_obj is not None
    assert spec_obj.dashboard is not None
    assert spec_obj.dashboard.kpis[0].metric == "count_students"
    assert spec_obj.design_system.responsive is True
