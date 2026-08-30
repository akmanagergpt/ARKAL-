"""Proves `_compile_acceptance_plan` -- the SAME unmodified compiler code,
with no domain-name branch anywhere in it -- derives a structurally correct
`_AcceptanceScenario` for three unrelated domains, each compared against
the existing hand-authored `golden/scenarios/*.json` file as a real oracle.

These fixture contract files live ONLY here (test-file scope), never under
`golden/` or any production import path -- `golden/scenarios/*.json`
itself is real DATA (an oracle to compare against), not a second code path
this module or the compiler could ever import (ARK-REQ-0074).

The comparison is STRUCTURAL, not literal-value equality: the compiler's
own deterministic example values (keyed on field TYPE) are, by design,
different literals than the ones a human hand-picked for the oracle file
(e.g. "Acceptance Student" vs. "Acceptance Value") -- what must match is
the real shape a candidate's own contracts determine: which resources
exist, their real routes, which fields are editable, which field is a
foreign key to which other resource, and which resource is primary/
related.
"""

from __future__ import annotations

import json
import pathlib

from arkali.engineering.factory.acceptance_plan_compiler import _compile_acceptance_plan
from arkali.engineering.factory.acceptance_plan_reconciliation import _reconcile_scenario

REPO = pathlib.Path(__file__).resolve().parents[3]
SCENARIOS = REPO / "golden" / "scenarios"

_DESIGN_SYSTEM = {
    "typography_scale": ["14px", "16px", "24px"],
    "spacing_scale": ["4px", "8px", "16px"],
    "component_conventions": ["primary buttons are filled"],
}


def _ux_spec(modules: list[dict], navigation_destinations: list[str], title: str) -> str:
    return json.dumps({
        "product_title": title, "primary_roles": ["Operator"], "modules": modules,
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


def _student_fee_files() -> dict[str, str]:
    return {
        "product/ux_spec.json": _ux_spec(
            [
                _module("students", "Students", ["create", "edit", "delete"], ["id", "name", "email"]),
                _module("payments", "Payments", ["create"], ["id", "student_id", "amount", "due_date"]),
            ],
            ["Students", "Payments", "Dashboard"], "Student Fee Management",
        ),
        "backend/routes.json": _routes(
            ("/students", "GET"), ("/students", "POST"),
            ("/students/{id}", "PUT"), ("/students/{id}", "DELETE"),
            ("/payments", "GET"), ("/payments", "POST"),
        ),
        "backend/data_model.json": _models({
            "students": {"id": "integer", "name": "string", "email": "string"},
            "payments": {"id": "integer", "student_id": "integer", "amount": "float", "due_date": "date"},
        }),
    }


def _inventory_files() -> dict[str, str]:
    return {
        "product/ux_spec.json": _ux_spec(
            [
                _module("products", "Products", ["create", "edit", "delete"], ["id", "name", "price"]),
                _module("categories", "Categories", ["create", "edit"], ["id", "name"]),
                _module(
                    "stock_movements", "Stock Movements", ["create"],
                    ["id", "product_id", "quantity", "movement_type"],
                ),
            ],
            ["Products", "Categories", "Stock Movements", "Dashboard"], "Inventory Management",
        ),
        "backend/routes.json": _routes(
            ("/products", "GET"), ("/products", "POST"),
            ("/products/{id}", "PUT"), ("/products/{id}", "DELETE"),
            ("/categories", "GET"), ("/categories", "POST"), ("/categories/{id}", "PUT"),
            ("/stock-movements", "GET"), ("/stock-movements", "POST"),
        ),
        "backend/data_model.json": _models({
            "products": {"id": "integer", "name": "string", "price": "float"},
            "categories": {"id": "integer", "name": "string"},
            "stock_movements": {
                "id": "integer", "product_id": "integer", "quantity": "integer", "movement_type": "string",
            },
        }),
    }


def _task_management_files() -> dict[str, str]:
    return {
        "product/ux_spec.json": _ux_spec(
            [
                _module("projects", "Projects", ["create", "edit", "delete"], ["id", "title"]),
                _module("tasks", "Tasks", ["create", "edit", "delete"], ["id", "project_id", "title", "due_date"]),
            ],
            ["Projects", "Tasks", "Dashboard"], "Task Management",
        ),
        "backend/routes.json": _routes(
            ("/projects", "GET"), ("/projects", "POST"),
            ("/projects/{id}", "PUT"), ("/projects/{id}", "DELETE"),
            ("/tasks", "GET"), ("/tasks", "POST"), ("/tasks/{id}", "PUT"), ("/tasks/{id}", "DELETE"),
        ),
        "backend/data_model.json": _models({
            "projects": {"id": "integer", "title": "string"},
            "tasks": {"id": "integer", "project_id": "integer", "title": "string", "due_date": "date"},
        }),
    }


_DOMAINS = {
    "student_fee_management": _student_fee_files,
    "inventory_management": _inventory_files,
    "task_management": _task_management_files,
}


def _oracle(scenario_name: str) -> dict:
    return json.loads((SCENARIOS / f"{scenario_name}.json").read_text(encoding="utf-8"))


class TestCompilerMatchesTheOracleShapeAcrossThreeDomains:
    def test_the_same_compiler_code_resolves_all_three_domains(self) -> None:
        for scenario_name, build_files in _DOMAINS.items():
            files = build_files()
            scenario = _compile_acceptance_plan(files)
            oracle = _oracle(scenario_name)

            assert scenario.primary_resource == oracle["primary_resource"], scenario_name
            assert scenario.related_resource == oracle["related_resource"], scenario_name
            assert set(scenario.navigation_destinations) == set(oracle["navigation_destinations"]), scenario_name

            oracle_resources = {r["name"]: r for r in oracle["resources"]}
            assert {r.name for r in scenario.resources} == set(oracle_resources), scenario_name
            for resource in scenario.resources:
                oracle_resource = oracle_resources[resource.name]
                assert resource.collection_route == oracle_resource["collection_route"], resource.name
                assert set(resource.editable_form_fields) == set(oracle_resource["editable_form_fields"]), resource.name
                assert resource.relationship_fields == oracle_resource.get("relationship_fields", {}), resource.name
                assert resource.destructive_confirmation_required == oracle_resource[
                    "destructive_confirmation_required"
                ], resource.name

    def test_every_compiled_domain_reconciles_cleanly_against_its_own_source(self) -> None:
        for build_files in _DOMAINS.values():
            files = build_files()
            scenario = _compile_acceptance_plan(files)
            assert _reconcile_scenario(scenario, files) == []

    # No separate domain-token negative control is written here on purpose:
    # `tests/governance/test_no_golden_domain_leakage.py` already scans
    # every real file under `backend/arkali` (which includes both
    # `acceptance_plan_compiler.py` and `acceptance_plan_reconciliation.py`)
    # with a real AST/tokenize-aware scanner that excludes docstrings and
    # comments -- a second, blunter substring scanner here would be exactly
    # the duplicate-authority/duplicate-parser this phase's own audit
    # (Part F) forbids, and would also false-positive on this compiler's
    # own docstrings, which legitimately cite "student_id" as the literal
    # counter-example of what NOT to hardcode.
