from __future__ import annotations

import json
import pathlib

import pytest

from arkali.engineering.factory.component_generation import generate_staged_model_product
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.frontend_callback_arity_preflight import (
    _callback_prop_arity_mismatch_findings,
)
from arkali.engineering.factory.frontend_mutation_contract import (
    _build_mutation_contracts,
    _mutation_contracts_for_stage,
)
from arkali.engineering.factory.generation_stages import StageVocabulary
from arkali.engineering.factory.stage_prompting import (
    _DEFAULT_REPAIR_STRATEGY,
    _repair_strategy_for_attempt,
    _STRUCTURED_HINT_REPAIR_STRATEGY,
    _stage_prompt,
)
from arkali.engineering.localai.adapter import HonestState
from tests.engineering.test_component_generation import (
    _blueprint,
    _factory,
    _happy_path_queues,
    _output,
    _workspace,
    REPO,
)

_UX_SPEC_JSON = json.dumps({
    "product_title": "Work Tracker",
    "primary_roles": ["user"],
    "modules": [{
        "name": "works",
        "navigation_label": "Works",
        "presentation": "list",
        "actions": ["create", "edit"],
        "forms": [{"name": "work_form", "fields": ["id", "title"]}],
        "search_filter": False,
        "states": {"loading": True, "empty": True, "error": True, "success": True},
    }],
    "navigation_destinations": ["Works"],
    "design_system": {
        "typography_scale": ["base"], "spacing_scale": ["sm"],
        "component_conventions": ["list"], "responsive": "desktop-first",
        "accessible_focus_contrast": True,
    },
    "destructive_action_confirmation": False,
})

_CLIENT_JS = (
    "export function createWork(title) { return fetch('/works', {method:'POST'}); }\n"
    "export function updateWork(id, title) { return fetch(`/works/${id}`, {method:'PUT'}); }\n"
)
_BACKEND_CONTRACT_FILES = {
    "backend/routes/task_routes.json": json.dumps([
        {"path": "/works", "method": "GET", "model_fields": ["id", "title"]},
        {"path": "/works", "method": "POST", "model_fields": ["id", "title"]},
        {"path": "/works", "method": "PUT", "model_fields": ["id", "title"]},
    ]),
    "backend/models/task_model.json": json.dumps(
        {"table_name": "works", "fields": {"id": {"type": "integer"}, "title": {"type": "string"}}}
    ),
}
_WORK_FORM_JS = (
    "function WorkForm({ onSubmit }) {\n"
    "  const [title, setTitle] = React.useState('');\n"
    "  const [success, setSuccess] = React.useState(false);\n"
    "  const handleSubmit = async (e) => { e.preventDefault(); await onSubmit(title); setSuccess(true); };\n"
    "  return <form onSubmit={handleSubmit}><label>Title<input required value={title} "
    "onChange={e=>setTitle(e.target.value)} /></label><button type='submit'>Submit</button>"
    "{success && <div>Success!</div>}</form>;\n"
    "}\n"
)
_BROKEN_APP_JS = (
    "import React from 'react';\n" + _WORK_FORM_JS + "<WorkForm onSubmit={updateWork} />"
)
_FIXED_APP_JS = (
    "import React from 'react';\n"
    "import { useParams } from 'react-router-dom';\n"
    "import { updateWork } from './client';\n" + _WORK_FORM_JS +
    "<WorkForm onSubmit={async (title) => { const { id } = useParams(); "
    "await updateWork(id, title); }} />"
)


class TestMutationContractBuilder:
    def test_mutation_contracts_match_golden_work_125s_own_real_shape(self) -> None:
        """golden-work-125's own real product/ux_spec.json + apiClient.js."""
        ux_spec = json.dumps({"modules": [{
            "name": "students", "actions": ["create", "edit", "delete"],
            "forms": [{"name": "student_form", "fields": ["id", "name", "email"]}],
        }]})
        client = (
            "async function createStudent(name, email) {}\n"
            "async function updateStudent(id, name, email) {}\n"
            "async function deleteStudent(id) {}\n"
        )
        contracts = _build_mutation_contracts(ux_spec, client)
        assert contracts == [{
            "module": "students",
            "actions": {
                "create": {"client_function": "createStudent", "signature": ["name", "email"]},
                "edit": {
                    "client_function": "updateStudent", "signature": ["id", "name", "email"],
                    "route": "/students/edit/:id", "route_param": "id",
                },
                "delete": {
                    "client_function": "deleteStudent", "signature": ["id"],
                    "route": "/students/delete/:id", "route_param": "id",
                },
            },
            "form_fields": ["name", "email"],
        }]

    def test_8_the_route_identifier_is_never_a_form_field(self) -> None:
        """"Route ID form alanı değildir" -- golden-work-125's own real
        product_ux_spec.json listed "id" inside forms[].fields as though
        it were a user-entered field; the structured contract must
        exclude it regardless."""
        ux_spec = json.dumps({"modules": [{
            "name": "students", "actions": ["edit"],
            "forms": [{"name": "student_form", "fields": ["id", "name", "email"]}],
        }]})
        client = "async function updateStudent(id, name, email) {}\n"
        contracts = _build_mutation_contracts(ux_spec, client)
        assert contracts[0]["form_fields"] == ["name", "email"]

    def test_a_missing_real_client_function_is_omitted_not_fabricated(self) -> None:
        ux_spec = json.dumps({"modules": [{
            "name": "students", "actions": ["edit"], "forms": [],
        }]})
        client = "async function somethingUnrelated() {}\n"
        assert _build_mutation_contracts(ux_spec, client) == []

    def test_malformed_ux_spec_json_yields_no_contracts_not_a_crash(self) -> None:
        assert _build_mutation_contracts("not json", "") == []

    def test_only_stages_declaring_both_real_inputs_get_contracts(self) -> None:
        assert _mutation_contracts_for_stage(("frontend_ui",), {}) is None
        assert _mutation_contracts_for_stage(("product_ux_spec",), {}) is None
        assert _mutation_contracts_for_stage(
            ("frontend_client", "frontend_ui", "product_ux_spec"),
            {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS},
        ) == _build_mutation_contracts(_UX_SPEC_JSON, _CLIENT_JS)


class TestStructuredContractInThePrompt:
    def _declaration(self):  # noqa: ANN202
        return next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")

    def test_10_the_structured_contract_reaches_the_real_generation_prompt(self) -> None:
        decl = self._declaration()
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        prompt = _stage_prompt(decl, _blueprint(), visible, None)
        payload = json.loads(prompt)
        assert payload["mutation_contracts"] == _build_mutation_contracts(_UX_SPEC_JSON, _CLIENT_JS)

    def test_13_the_stages_own_rule_and_other_fields_survive_unchanged(self) -> None:
        decl = self._declaration()
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        payload = json.loads(_stage_prompt(decl, _blueprint(), visible, None))
        assert payload["task"] == decl.rule
        assert "success" in decl.rule.lower() or "success" in payload["task"].lower()
        assert payload["goal"] == _blueprint().goal.goal_text
        assert payload["visible_prior_files"] == visible

    def test_a_stage_with_no_mutation_concern_gets_no_contract_field(self) -> None:
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_ui")
        payload = json.loads(_stage_prompt(decl, _blueprint(), {}, None))
        assert "mutation_contracts" not in payload
        assert "repair_strategy" not in payload


class TestRepairStrategyEscalation:
    def test_9_the_first_attempt_uses_the_default_strategy(self) -> None:
        assert _repair_strategy_for_attempt(1) == _DEFAULT_REPAIR_STRATEGY

    def test_9_the_second_attempt_escalates_to_the_structured_hint_strategy(self) -> None:
        assert _repair_strategy_for_attempt(2) == _STRUCTURED_HINT_REPAIR_STRATEGY
        assert _repair_strategy_for_attempt(4) == _STRUCTURED_HINT_REPAIR_STRATEGY

    def test_default_strategy_omits_the_repair_hint(self) -> None:
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        payload = json.loads(_stage_prompt(decl, _blueprint(), visible, "some failure"))
        assert payload["repair_strategy"] == _DEFAULT_REPAIR_STRATEGY
        assert "repair_hint" not in payload

    def test_structured_hint_strategy_names_the_forbidden_pattern_and_a_worked_example(self) -> None:
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, "some failure",
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY,
        ))
        assert payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        hint = payload["repair_hint"]
        assert "onSubmit={updateStudent}" in hint
        assert "useParams()" in hint


class TestBareReferenceEditCallbackBan:
    def test_1_a_bare_reference_create_wrapper_passes(self) -> None:
        files = {
            "frontend/src/App.js": "<WorkForm onSubmit={createWork} />",
            "frontend/src/client.js": _CLIENT_JS,
        }
        assert _callback_prop_arity_mismatch_findings(files) == []

    def test_3_a_bare_reference_to_the_edit_function_is_rejected(self) -> None:
        files = {
            "frontend/src/App.js": "<WorkForm onSubmit={updateWork} />",
            "frontend/src/client.js": _CLIENT_JS,
        }
        findings = _callback_prop_arity_mismatch_findings(files)
        codes = {f.code for f in findings}
        assert "frontend_ui_edit_callback_bound_by_bare_reference" in codes

    def test_7_the_create_flow_never_expects_an_edit_id(self) -> None:
        """A 2-parameter create function whose first param is NOT "id"
        never trips the edit-only ban, bare reference or not."""
        files = {
            "frontend/src/App.js": "<WorkForm onSubmit={createWork} />",
            "frontend/src/client.js": _CLIENT_JS,
        }
        findings = _callback_prop_arity_mismatch_findings(files)
        assert all(f.code != "frontend_ui_edit_callback_bound_by_bare_reference" for f in findings)

    def test_2_an_edit_wrapper_reading_and_passing_the_route_id_passes(self) -> None:
        files = {
            "frontend/src/App.js": (
                "<WorkForm onSubmit={async (title) => { "
                "const { id } = useParams(); await updateWork(id, title); }} />"
            ),
            "frontend/src/client.js": _CLIENT_JS,
        }
        assert _callback_prop_arity_mismatch_findings(files) == []

    def test_5_an_edit_wrapper_reading_but_never_passing_the_route_id_is_rejected(self) -> None:
        files = {
            "frontend/src/App.js": (
                "<WorkForm onSubmit={async (title) => { "
                "const { id } = useParams(); await updateWork(title); }} />"
            ),
            "frontend/src/client.js": _CLIENT_JS,
        }
        findings = _callback_prop_arity_mismatch_findings(files)
        codes = {f.code for f in findings}
        assert "frontend_ui_route_id_read_but_not_passed" in codes


class TestConvergence:
    def test_12_a_controlled_broken_first_attempt_converges_on_the_structured_hint_retry(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """A real, controlled `_QueueModel` reproduces golden-work-125's
        own class on attempt 1 (a bare reference to the edit client
        function) and a correctly-wrapped closure on attempt 2 -- proving
        the retry mechanism actually converges within budget for this
        defect class, not just that the checker rejects the broken shape
        once in isolation."""
        queues = _happy_path_queues()
        queues["backend_contract"] = [(HonestState.PASS, _output(_BACKEND_CONTRACT_FILES))]
        queues["product_ux_spec"] = [(HonestState.PASS, _output({
            "product/ux_spec.json": _UX_SPEC_JSON,
        }))]
        queues["frontend_client"] = [(HonestState.PASS, _output({
            "frontend/src/client.js": _CLIENT_JS,
        }))]
        broken = _output({"frontend/src/App.js": _BROKEN_APP_JS})
        fixed = _output({"frontend/src/App.js": _FIXED_APP_JS})
        queues["frontend_forms"] = [(HonestState.PASS, broken), (HonestState.PASS, fixed)]

        factory = _factory(queues)
        result = generate_staged_model_product(
            _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
        )
        assert "frontend/src/App.js" in result.files

        forms_model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
        assert len(forms_model.prompts) == 2
        first_payload = json.loads(forms_model.prompts[0])
        second_payload = json.loads(forms_model.prompts[1])
        assert first_payload["repair_strategy"] == _DEFAULT_REPAIR_STRATEGY
        assert "repair_hint" not in first_payload
        assert second_payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        assert "repair_hint" in second_payload
        assert "frontend_ui_edit_callback_bound_by_bare_reference" in second_payload["prior_attempt_failure"]

    def test_a_broken_attempt_that_never_improves_still_exhausts_the_real_budget(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """The structured hint helps a model that CAN converge; it must
        not silently mask a model that never does -- the real bounded
        attempt budget (and ModelGenerationError on exhaustion) is
        unchanged."""
        queues = _happy_path_queues()
        queues["backend_contract"] = [(HonestState.PASS, _output(_BACKEND_CONTRACT_FILES))]
        queues["product_ux_spec"] = [(HonestState.PASS, _output({
            "product/ux_spec.json": _UX_SPEC_JSON,
        }))]
        queues["frontend_client"] = [(HonestState.PASS, _output({
            "frontend/src/client.js": _CLIENT_JS,
        }))]
        broken = _output({"frontend/src/App.js": _BROKEN_APP_JS})
        queues["frontend_forms"] = [(HonestState.PASS, broken)] * 4

        factory = _factory(queues)
        # An identical broken attempt repeated verbatim trips the existing,
        # separate anti-loop guard (component_generation.py) before the
        # bounded budget itself would exhaust -- either way, a model that
        # never converges is refused, never silently accepted.
        with pytest.raises(ModelGenerationError, match="frontend_ui_edit_callback_bound_by_bare_reference"):
            generate_staged_model_product(
                _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
            )
