from __future__ import annotations

import json

import pytest

from arkali.engineering.factory.acceptance_plan_compiler import (
    _AcceptancePlanIncomplete,
    _compile_acceptance_plan,
)
from arkali.engineering.factory.acceptance_plan_reconciliation import _reconcile_scenario

_DESIGN_SYSTEM = {
    "typography_scale": ["14px", "16px", "24px"],
    "spacing_scale": ["4px", "8px", "16px"],
    "component_conventions": ["primary buttons are filled"],
}


def _ux_spec(modules: list[dict], navigation_destinations: list[str], title: str = "Test Product") -> str:
    return json.dumps({
        "product_title": title,
        "primary_roles": ["Operator"],
        "modules": modules,
        "navigation_destinations": navigation_destinations,
        "design_system": _DESIGN_SYSTEM,
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


class TestSingleResourceNoRelationship:
    """The narrowest real shape: one module, no relationship field, an id
    primary key that must never leak into the payload it compiles."""

    def _files(self) -> dict[str, str]:
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

    def test_compiles_a_real_scenario(self) -> None:
        scenario = _compile_acceptance_plan(self._files())
        assert scenario.primary_resource == "widgets"
        assert scenario.related_resource is None
        resource = scenario.resource("widgets")
        assert resource.collection_route == "/widgets"
        assert resource.destructive_confirmation_required is True

    def test_the_primary_key_never_leaks_into_editable_fields_or_payloads(self) -> None:
        scenario = _compile_acceptance_plan(self._files())
        resource = scenario.resource("widgets")
        assert "id" not in resource.editable_form_fields
        assert "id" not in scenario.create_payload
        assert "id" not in scenario.update_payload

    def test_create_update_and_browser_values_are_all_distinct(self) -> None:
        scenario = _compile_acceptance_plan(self._files())
        assert scenario.create_payload["name"] != scenario.update_payload["name"]
        assert scenario.create_payload["name"] != scenario.browser_create_values["name"]
        assert scenario.update_payload["name"] != scenario.browser_update_values["name"]
        assert scenario.browser_create_values["name"] != scenario.browser_update_values["name"]

    def test_a_compiled_scenario_reconciles_cleanly_against_its_own_source(self) -> None:
        files = self._files()
        scenario = _compile_acceptance_plan(files)
        assert _reconcile_scenario(scenario, files) == []


class TestTwoResourcesWithASchemaDrivenRelationship:
    """A relationship is detected from the real declared field TYPE
    (integer) and a real declared model name it structurally matches --
    never from a hardcoded field-name branch."""

    def _files(self) -> dict[str, str]:
        return {
            "product/ux_spec.json": _ux_spec(
                [
                    _module("crates", "Crates", ["create", "edit", "delete"], ["id", "label"]),
                    _module("crate_items", "Crate Items", ["create"], ["id", "crate_id", "quantity"]),
                ],
                ["Crates", "Crate Items"],
            ),
            "backend/routes.json": _routes(
                ("/crates", "GET"), ("/crates", "POST"), ("/crates/{id}", "PUT"), ("/crates/{id}", "DELETE"),
                ("/crate-items", "GET"), ("/crate-items", "POST"),
            ),
            "backend/data_model.json": _models({
                "crates": {"id": "integer", "label": "string"},
                "crate_items": {"id": "integer", "crate_id": "integer", "quantity": "integer"},
            }),
        }

    def test_the_relationship_is_resolved_against_the_real_schema(self) -> None:
        scenario = _compile_acceptance_plan(self._files())
        assert scenario.primary_resource == "crates"
        assert scenario.related_resource == "crate_items"
        related = scenario.resource("crate_items")
        assert related.relationship_fields == {"crate_id": "crates"}
        assert "crate_id" not in related.editable_form_fields
        assert scenario.related_create_payload is not None
        assert "crate_id" not in scenario.related_create_payload

    def test_a_field_ending_in_id_with_no_matching_model_is_not_a_relationship(self) -> None:
        """`external_id` ends in `_id` and is an integer, but no declared
        model is named (singular or plural) "external" -- must be treated
        as a plain field, never guessed into a fabricated relationship."""
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("tickets", "Tickets", ["create"], ["id", "external_id"])], ["Tickets"],
            ),
            "backend/routes.json": _routes(("/tickets", "GET"), ("/tickets", "POST")),
            "backend/data_model.json": _models({"tickets": {"id": "integer", "external_id": "integer"}}),
        }
        scenario = _compile_acceptance_plan(files)
        resource = scenario.resource("tickets")
        assert resource.relationship_fields == {}
        assert "external_id" in resource.editable_form_fields


class TestNestedRoutePrefixMatching:
    """A real backend is free to nest a resource under a real, semantic
    path prefix (`/api/books/overdue`, real evidence: `factory-goal-
    mtpnp9af-yeldck`) rather than the flat `/resource` convention every
    prior golden fixture happened to use -- no canonical stage rule ever
    required the FIRST path segment to name the resource, and this is
    the real, previously-undiscovered gap that blocked this candidate's
    own real production acceptance attempt."""

    def test_a_module_nested_under_an_unrelated_prefix_still_resolves(self) -> None:
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("widgets", "Widgets", ["create", "edit", "delete"], ["id", "name", "price"])],
                ["Widgets"],
            ),
            "backend/routes.json": _routes(
                ("/api/catalog/widgets", "GET"), ("/api/catalog/widgets", "POST"),
                ("/api/catalog/widgets/{id}", "PUT"), ("/api/catalog/widgets/{id}", "DELETE"),
            ),
            "backend/data_model.json": _models({"widgets": {"id": "integer", "name": "string", "price": "float"}}),
        }
        scenario = _compile_acceptance_plan(files)
        resource = scenario.resource("widgets")
        assert resource.collection_route == "/api/catalog/widgets"

    def test_a_route_matching_no_segment_at_all_still_refuses(self) -> None:
        """The widened matching never becomes "any route will do" -- a
        genuinely unrelated nested path still resolves nothing, exactly
        as the pre-existing flat-path case already required."""
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("ghosts", "Ghosts", ["create"], ["id", "name"])], ["Ghosts"],
            ),
            "backend/routes.json": _routes(("/api/catalog/other", "GET")),
            "backend/data_model.json": _models({"ghosts": {"id": "integer", "name": "string"}}),
        }
        with pytest.raises(_AcceptancePlanIncomplete):
            _compile_acceptance_plan(files)

    def test_a_route_param_segment_is_never_matched_as_a_resource_name(self) -> None:
        """`{id}` (or any `{param}`) is a placeholder, never a real
        segment this module's own name could coincidentally match."""
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("id", "Ids", ["create"], ["id", "name"])], ["Ids"],
            ),
            "backend/routes.json": _routes(("/api/widgets/{id}", "GET")),
            "backend/data_model.json": _models({"id": {"id": "integer", "name": "string"}}),
        }
        with pytest.raises(_AcceptancePlanIncomplete):
            _compile_acceptance_plan(files)


class TestViewOnlyModuleNeverGetsAGuessedMutation:
    """Real evidence: `factory-goal-mtquvzmc-dt3go3`. A real, valid,
    view-only module (declared actions `["view"]` only, a real backend
    exposing GET alone) previously still got a real `create_payload`
    synthesized from its own model fields, was still selected as primary
    (the only resolved module), and the real browser journey's own POST
    against its real, GET-only route then failed with a real, live
    "HTTP Error 405: METHOD NOT ALLOWED" -- never a candidate defect, an
    acceptance-compiler one: it silently GUESSED a mutation capability
    the module's own real, reconciled actions never claimed."""

    def _files(self) -> dict[str, str]:
        view_only_module = {
            "name": "overdue_books", "navigation_label": "Overdue Books", "presentation": "table",
            "actions": ["view"], "forms": [],
        }
        return {
            "product/ux_spec.json": _ux_spec([view_only_module], ["Overdue Books"]),
            "backend/routes.json": _routes(("/api/books/overdue", "GET")),
            "backend/data_model.json": _models({
                "overdue_books": {
                    "book_id": "integer", "title": "string",
                    "borrow_date": "date", "due_date": "date",
                },
            }),
        }

    def test_a_view_only_module_refuses_rather_than_guesses_a_create_payload(self) -> None:
        with pytest.raises(_AcceptancePlanIncomplete) as excinfo:
            _compile_acceptance_plan(self._files())
        assert any("no real editable field to create with" in reason for reason in excinfo.value.reasons)

    def test_the_real_factory_goal_mtquvzmc_dt3go3_contracts_now_refuse_cleanly(self) -> None:
        """Direct historical replay of this real candidate's own real,
        frozen `product/ux_spec.json` + `backend/*.json` bytes -- no new
        generation, no live process, the exact same real contracts that
        real acceptance attempt actually used."""
        import pathlib

        candidate_dir = pathlib.Path(__file__).resolve().parents[3] / "var" / "factory" / "candidates" / "factory-goal-mtquvzmc-dt3go3"
        if not candidate_dir.is_dir():
            pytest.skip("real candidate directory not present in this checkout")
        files: dict[str, str] = {}
        for sub in ("product", "backend"):
            directory = candidate_dir / sub
            if not directory.is_dir():
                continue
            for path in directory.glob("*.json"):
                files[f"{sub}/{path.name}"] = path.read_text(encoding="utf-8")
        with pytest.raises(_AcceptancePlanIncomplete) as excinfo:
            _compile_acceptance_plan(files)
        assert any("no real editable field to create with" in reason for reason in excinfo.value.reasons)

    def test_a_module_declaring_edit_but_not_create_still_gets_a_payload(self) -> None:
        """The gate is "create OR edit", not "create only" -- a real,
        valid update-only module must still be usable as an acceptance
        primary via its own real edit flow."""
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("settings", "Settings", ["edit"], ["id", "value"])], ["Settings"],
            ),
            "backend/routes.json": _routes(
                ("/settings", "GET"), ("/settings/{id}", "PUT"),
            ),
            "backend/data_model.json": _models({"settings": {"id": "integer", "value": "string"}}),
        }
        scenario = _compile_acceptance_plan(files)
        assert scenario.update_payload


class TestRefusesRatherThanGuesses:
    def test_no_product_ux_spec_refuses(self) -> None:
        with pytest.raises(_AcceptancePlanIncomplete):
            _compile_acceptance_plan({})

    def test_an_unrecognized_field_type_refuses_by_name(self) -> None:
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("widgets", "Widgets", ["create"], ["id", "blob"])], ["Widgets"],
            ),
            "backend/routes.json": _routes(("/widgets", "GET"), ("/widgets", "POST")),
            "backend/data_model.json": _models({"widgets": {"id": "integer", "blob": "binary"}}),
        }
        with pytest.raises(_AcceptancePlanIncomplete) as excinfo:
            _compile_acceptance_plan(files)
        assert any("blob" in reason for reason in excinfo.value.reasons)

    def test_a_module_with_no_matching_backend_route_refuses(self) -> None:
        files = {
            "product/ux_spec.json": _ux_spec(
                [_module("ghosts", "Ghosts", ["create"], ["id", "name"])], ["Ghosts"],
            ),
            "backend/routes.json": _routes(("/other", "GET")),
            "backend/data_model.json": _models({"ghosts": {"id": "integer", "name": "string"}}),
        }
        with pytest.raises(_AcceptancePlanIncomplete):
            _compile_acceptance_plan(files)
