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


def test_missing_module_feedback_names_the_real_backend_name_not_the_normalized_form() -> None:
    """golden-work-095 (session evidence, frozen): a real qwen2.5-coder:14b
    declared a module named "tasks" against a real backend model whose own
    real name was "task_model" (normalized to "taskmodel" for
    case/separator-insensitive comparison). The finding this stage's own
    retry feedback showed back to the model was the ALREADY-NORMALIZED
    string ("['taskmodel']") -- not a real, literal name the model could
    copy verbatim, since normalization strips the underscore/case it would
    naturally reintroduce. Two consecutive retries reproduced the
    identical mismatch and exhausted the anti-loop budget. The detail must
    now show the real backend-declared name so a corrected module's own
    "name" field has something literal to copy."""
    files = {
        "backend/task_model.json": json.dumps(
            {"table_name": "task_model", "fields": {"id": {"type": "integer"}}}
        ),
        "product/ux_spec.json": json.dumps({
            "product_title": "Tasks", "primary_roles": ["user"],
            "modules": [_module("tasks", ["view"])],
            "navigation_destinations": ["Tasks"],
            "design_system": _DESIGN_SYSTEM,
        }),
    }
    findings = _ux_spec_stage_findings(files)
    missing = next(f for f in findings if f.code == "ux_spec_missing_module")
    assert "task_model" in missing.detail
    assert "taskmodel" not in missing.detail


def test_a_task_module_matches_a_task_model_fallback_name() -> None:
    """F-0068 property A. golden-work-130 (real repository evidence,
    frozen): the real model's own module name ("task") against
    backend_contract's own fallback-derived model name ("task_model",
    from a real task_model.json with no table_name) is a real parity
    match, not a mismatch -- the same real concept, spelled two
    idiomatically different ways."""
    files = _task_spec_files(["view"])
    spec = json.loads(files["product/ux_spec.json"])
    spec["modules"][0]["name"] = "task"
    files["product/ux_spec.json"] = json.dumps(spec)
    findings = _ux_spec_stage_findings(files)
    assert not any(f.code in ("ux_spec_missing_module", "ux_spec_invented_module") for f in findings)


def test_b_and_h_an_inventory_module_matches_an_inventory_model_fallback_name() -> None:
    """F-0068 properties B/H: a second, structurally different domain
    (never task/student) reproduces the identical behavior -- proves the
    fix carries no domain-specific logic."""
    files = {
        "backend/inventory_model.json": json.dumps(
            {"fields": {"id": {"type": "integer"}, "quantity": {"type": "integer"}}}
        ),
        "backend/routes.json": json.dumps([
            {"path": "/inventory", "method": "GET"},
            {"path": "/inventory", "method": "POST"},
        ]),
        "product/ux_spec.json": json.dumps({
            "product_title": "Inventory System", "primary_roles": ["staff"],
            "modules": [_module("inventory", ["create", "view"], forms=[
                {"name": "InventoryForm", "fields": ["quantity"]},
            ])],
            "navigation_destinations": ["Inventory"],
            "design_system": _DESIGN_SYSTEM,
        }),
    }
    findings = _ux_spec_stage_findings(files)
    assert not any(f.code in ("ux_spec_missing_module", "ux_spec_invented_module") for f in findings)


def test_c_explicit_table_name_still_takes_precedence_over_the_filename() -> None:
    """F-0068 property C: a model file whose own real, deliberate
    `table_name` differs from its filename is still compared by that
    explicit name, never the filename -- `_model_names_in_document`'s own
    existing precedence is unchanged by this fix."""
    files = {
        "backend/tbl1.json": json.dumps(
            {"table_name": "products", "fields": {"id": {"type": "integer"}}}
        ),
        "backend/routes.json": json.dumps([{"path": "/products", "method": "GET"}]),
        "product/ux_spec.json": json.dumps({
            "product_title": "Shop", "primary_roles": ["staff"],
            "modules": [_module("products", ["view"])],
            "navigation_destinations": ["Products"],
            "design_system": _DESIGN_SYSTEM,
        }),
    }
    findings = _ux_spec_stage_findings(files)
    assert not any(f.code in ("ux_spec_missing_module", "ux_spec_invented_module") for f in findings)


def test_d_genuinely_different_resource_names_still_fail() -> None:
    """F-0068 property D: normalization narrows a real spelling gap, it
    never widens the check into accepting an unrelated resource."""
    files = _task_spec_files(["view"])
    spec = json.loads(files["product/ux_spec.json"])
    spec["modules"][0]["name"] = "payment"
    files["product/ux_spec.json"] = json.dumps(spec)
    findings = _ux_spec_stage_findings(files)
    assert any(f.code == "ux_spec_missing_module" for f in findings)
    assert any(f.code == "ux_spec_invented_module" for f in findings)


def test_e_a_natural_word_only_containing_model_is_not_wrongly_stripped() -> None:
    """F-0068 property E: `_resource_matching_name` only strips a genuine
    TRAILING "model" suffix -- a resource whose real name merely contains
    the substring "model" elsewhere (never at the very end, e.g. a hobby
    shop's real "modeltrain" resource) reconciles using its own real,
    complete name, never wrongly truncated."""
    files = {
        "backend/modeltrain_model.json": json.dumps(
            {"table_name": "modeltrain", "fields": {"id": {"type": "integer"}}}
        ),
        "backend/routes.json": json.dumps([{"path": "/modeltrain", "method": "GET"}]),
        "product/ux_spec.json": json.dumps({
            "product_title": "Hobby Shop", "primary_roles": ["staff"],
            "modules": [_module("modeltrain", ["view"])],
            "navigation_destinations": ["Modeltrain"],
            "design_system": _DESIGN_SYSTEM,
        }),
    }
    findings = _ux_spec_stage_findings(files)
    assert not any(f.code in ("ux_spec_missing_module", "ux_spec_invented_module") for f in findings)


def test_f_action_route_mismatch_still_fails_independent_of_name_parity() -> None:
    """F-0068 property F: golden-work-130's own real second half. The
    module name now correctly parity-matches ("task" <-> the backend's
    fallback-derived "task_model"), but the real backend still has no
    DELETE route for /tasks -- the pre-existing, untouched
    over-declared-action check must still fire exactly as before; this
    fix is scoped to name parity only, never touching action/route
    reconciliation."""
    files = _task_spec_files(["create", "edit", "delete", "view"])
    spec = json.loads(files["product/ux_spec.json"])
    spec["modules"][0]["name"] = "task"
    files["product/ux_spec.json"] = json.dumps(spec)
    findings = _ux_spec_stage_findings(files)
    assert not any(f.code in ("ux_spec_missing_module", "ux_spec_invented_module") for f in findings)
    over = next(f for f in findings if f.code == "ux_spec_action_over_declared")
    assert "delete" in over.detail


def test_g_golden_work_130s_own_real_model_artifact_no_longer_fails_on_name_parity() -> None:
    """F-0068 property G: `golden-work-130`'s own real, frozen, unmodified
    `backend/task_model.json` and `backend/routes.json` bytes (copied
    verbatim, never re-typed) -- the exact real evidence this fix was
    written from -- reconciled against a module genuinely named "task",
    the real model's own final real choice. Read-only evidence: this test
    never touches `var/factory/candidates/golden-work-130` itself."""
    files = {
        "backend/task_model.json": json.dumps({
            "fields": {
                "id": {"type": "integer", "primary_key": True},
                "title": {"type": "string"},
                "description": {"type": "string"},
                "completed": {"type": "boolean"},
            },
        }),
        "backend/routes.json": json.dumps([
            {"path": "/tasks", "method": "GET"},
            {"path": "/tasks", "method": "POST"},
            {"path": "/tasks/{id}", "method": "GET"},
            {"path": "/tasks/{id}", "method": "PUT"},
        ]),
        "product/ux_spec.json": json.dumps({
            "product_title": "Task Management System", "primary_roles": ["Task Manager"],
            "modules": [_module("task", ["create", "edit", "view"], forms=[
                {"name": "TaskForm", "fields": ["title", "description", "completed"]},
            ])],
            "navigation_destinations": ["Tasks"],
            "design_system": _DESIGN_SYSTEM,
        }),
    }
    findings = _ux_spec_stage_findings(files)
    assert not any(f.code in ("ux_spec_missing_module", "ux_spec_invented_module") for f in findings)


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


#: golden-work-098 (real end-to-end execution evidence, frozen): the real
#: backend_contract/product_ux_spec shape that exposed the matching bug --
#: a module named "task_model" (backend_contract's own task_model.json
#: declared no table_name, so its real declared name defaulted to the
#: file stem "task_model" -- golden-work-095's own fix requires the
#: module to reuse that exact name) against a real backend that only ever
#: implemented GET/POST/GET/PUT for /tasks, no DELETE.
_TASK_BACKEND_FILES = {
    "backend/task_model.json": json.dumps(
        {"fields": {"id": {"type": "integer"}, "title": {"type": "string"}}}
    ),
    "backend/routes.json": json.dumps([
        {"path": "/tasks", "method": "GET"},
        {"path": "/tasks", "method": "POST"},
        {"path": "/tasks/{id}", "method": "GET"},
        {"path": "/tasks/{id}", "method": "PUT"},
    ]),
}


def _task_spec_files(actions: list[str]) -> dict[str, str]:
    spec = {
        "product_title": "Task Management System", "primary_roles": ["Task Manager"],
        "modules": [_module("task_model", actions, forms=[
            {"name": "create_task", "fields": ["title"]},
        ] if any(a in ("create", "edit") for a in actions) else [])],
        "navigation_destinations": ["Tasks"],
        "design_system": _DESIGN_SYSTEM,
    }
    return {**_TASK_BACKEND_FILES, "product/ux_spec.json": json.dumps(spec)}


def test_module_action_matching_tolerates_a_model_suffixed_module_name() -> None:
    """golden-work-098 (real end-to-end execution evidence, frozen): before
    this fix, `_matching_methods` normalized "task_model" to "taskmodel"
    and compared it against the real route's own resource key ("tasks")
    -- neither string contains the other, so this matched NOTHING,
    silently, for any real candidate using this exact naming convention.
    Proven here via the real under-declared-action check that bug also
    silently disabled: the backend genuinely exposes POST+PUT (create+
    edit), which a view-only spec now correctly under-declares."""
    files = _task_spec_files(["view"])
    findings = _ux_spec_stage_findings(files)
    under = next(f for f in findings if f.code == "ux_spec_action_under_declared")
    assert "create" in under.detail and "edit" in under.detail


def test_flags_a_declared_action_the_real_backend_has_no_route_for() -> None:
    """golden-work-098 (real end-to-end execution evidence, frozen): the
    real spec declared "delete" for task_model against a real backend
    that never implemented a DELETE route for /tasks -- backend_contract
    runs before product_ux_spec even exists, so it had no way to know a
    later stage would declare a delete action. frontend_forms then
    faithfully built a full, real TaskDelete.js pointing at an endpoint
    that structurally could never exist -- a real production build
    compiled successfully; only a real click would get a real HTTP 405
    from Flask."""
    files = _task_spec_files(["create", "edit", "delete", "view"])
    findings = _ux_spec_stage_findings(files)
    over = next(f for f in findings if f.code == "ux_spec_action_over_declared")
    assert "delete" in over.detail
    assert "create" not in over.detail and "edit" not in over.detail


def test_is_silent_when_every_declared_action_has_a_real_backend_route() -> None:
    files = _task_spec_files(["create", "edit", "view"])
    findings = _ux_spec_stage_findings(files)
    assert not any(f.code == "ux_spec_action_over_declared" for f in findings)


def test_over_declared_check_is_silent_when_the_module_matches_no_real_resource() -> None:
    """An inconclusive resource match (real_methods empty) must never be
    treated as proof every declared action is unsupported -- that would
    be strictly worse than no check at all."""
    files = {
        "backend/widget_model.json": json.dumps(
            {"fields": {"id": {"type": "integer"}}}
        ),
        "backend/routes.json": json.dumps([{"path": "/completely-unrelated", "method": "GET"}]),
        "product/ux_spec.json": json.dumps({
            "product_title": "Widgets", "primary_roles": ["user"],
            "modules": [_module("widget_model", ["create", "edit", "delete", "view"], forms=[
                {"name": "widget_form", "fields": ["name"]},
            ])],
            "navigation_destinations": ["Widgets"],
            "design_system": _DESIGN_SYSTEM,
        }),
    }
    findings = _ux_spec_stage_findings(files)
    assert not any(f.code == "ux_spec_action_over_declared" for f in findings)


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
