from __future__ import annotations

import json
import pathlib

import pytest

from arkali.engineering.factory.component_generation import (
    _frontend_forms_findings,
    generate_staged_model_product,
)
from arkali.engineering.factory.errors import ModelGenerationError
from arkali.engineering.factory.frontend_callback_arity_preflight import (
    _callback_prop_arity_mismatch_findings,
)
from arkali.engineering.factory.frontend_manifest_preflight import _frontend_local_import_findings
from arkali.engineering.factory.frontend_mutation_contract import (
    _build_mutation_contracts,
    _mutation_contracts_for_stage,
)
from arkali.engineering.factory.generation_stages import StageVocabulary
from arkali.engineering.factory.stage_prompting import (
    _DEFAULT_REPAIR_STRATEGY,
    _prior_finding_hint_blocks,
    _repair_strategy_for_attempt,
    _STRUCTURED_HINT_REPAIR_STRATEGY,
    _stage_prompt,
    _structured_hint_text,
    _SUPPORTED_HINT_INVARIANTS,
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
#: F-0069. A real call to a real client export (`updateWork(id, title)`,
#: never a bare reference -- that's the callback-arity class above), with
#: no import of it anywhere in this file -- the exact real
#: `frontend_client_call_missing_import` shape `golden-work-131`'s own
#: real `App.js` independently reproduced.
_MISSING_IMPORT_APP_JS = (
    "import React from 'react';\n" + _WORK_FORM_JS +
    "<WorkForm onSubmit={async (title) => { const { id } = useParams(); "
    "await updateWork(id, title); }} />"
)
#: FRONTEND_FORMS_LOCAL_COMPONENT_COMPLETENESS_GAP. A deliberately
#: create-only module (no edit/id/route concern at all) isolates the one
#: fixture defect this class exists to prove converges: `./NoteForm` is
#: a real relative import to a form component split into its own file --
#: the exact real `frontend_local_import_unresolved` shape
#: `factory-goal-mu1oieg4-3bye3k`'s own real output independently
#: reproduced (two form components imported, neither ever emitted).
#: `createNote` is imported from `./client` (already real and visible)
#: and takes the same one argument `NoteForm`'s own `onSubmit(title)`
#: call supplies, so this fixture triggers exactly the one intended
#: finding -- never `frontend_client_call_missing_import` (the import is
#: present) nor the callback-arity-mismatch class above (no route
#: identifier is involved for a create-only action).
_LOCAL_IMPORT_BACKEND_CONTRACT_FILES = {
    "backend/routes/note_routes.json": json.dumps([
        {"path": "/notes", "method": "GET", "model_fields": ["id", "title"]},
        {"path": "/notes", "method": "POST", "model_fields": ["id", "title"]},
    ]),
    "backend/models/note_model.json": json.dumps(
        {"table_name": "notes", "fields": {"id": {"type": "integer"}, "title": {"type": "string"}}}
    ),
}
_LOCAL_IMPORT_UX_SPEC_JSON = json.dumps({
    "product_title": "Notes",
    "primary_roles": ["user"],
    "modules": [{
        "name": "notes",
        "navigation_label": "Notes",
        "presentation": "list",
        "actions": ["create"],
        "forms": [{"name": "note_form", "fields": ["title"]}],
        "search_filter": False,
        "states": {"loading": True, "empty": True, "error": True, "success": True},
    }],
    "navigation_destinations": ["Notes"],
    "design_system": {
        "typography_scale": ["base"], "spacing_scale": ["sm"],
        "component_conventions": ["list"], "responsive": "desktop-first",
        "accessible_focus_contrast": True,
    },
    "destructive_action_confirmation": False,
})
_LOCAL_IMPORT_CLIENT_JS = (
    "export function createNote(title) { return fetch('/notes', {method:'POST'}); }\n"
)
_NOTE_FORM_JS = (
    "function NoteForm({ onSubmit }) {\n"
    "  const [title, setTitle] = React.useState('');\n"
    "  const [success, setSuccess] = React.useState(false);\n"
    "  const handleSubmit = async (e) => { e.preventDefault(); await onSubmit(title); "
    "setSuccess(true); };\n"
    "  return <form onSubmit={handleSubmit}><label>Title<input required value={title} "
    "onChange={e=>setTitle(e.target.value)} /></label><button type='submit'>Submit</button>"
    "{success && <div>Success!</div>}</form>;\n"
    "}\n"
)
#: A real, reachable "Add Note" control is included here so this fixture
#: exercises only the one convergence class this test exists to prove --
#: `_create_access_findings` (F-0099/Wave B's own, already-correct, out
#: of scope for this turn) is otherwise unrelated and must not fire.
_LOCAL_IMPORT_BROKEN_APP_JS = (
    "import React from 'react';\n"
    "import { createNote } from './client';\n"
    "import NoteForm from './NoteForm';\n"
    "function App() { return (<div><button>Add Note</button>"
    "<NoteForm onSubmit={createNote} /></div>); }\n"
)
_NOTE_FORM_STANDALONE_JS = _NOTE_FORM_JS + "export default NoteForm;\n"


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

    def test_the_same_algorithm_produces_the_same_shape_across_three_unrelated_domains(
        self,
    ) -> None:
        """The core mutation-contract algorithm names no domain -- the
        exact same code, unchanged, must derive a structurally identical
        contract shape for a student/fee product, an inventory product,
        and a task/reservation product. Proves _build_mutation_contracts
        is domain-independent, not merely undocumented-as-domain-specific."""
        domains = {
            "student_fee": (
                json.dumps({"modules": [{
                    "name": "students", "actions": ["create", "edit", "delete"],
                    "forms": [{"name": "student_form", "fields": ["id", "name", "email"]}],
                }]}),
                "export function createStudent(name, email) {}\n"
                "export function updateStudent(id, name, email) {}\n"
                "export function deleteStudent(id) {}\n",
                "createStudent", "updateStudent", "deleteStudent",
            ),
            "inventory": (
                json.dumps({"modules": [{
                    "name": "products", "actions": ["create", "edit", "delete"],
                    "forms": [{"name": "product_form", "fields": ["id", "name", "price"]}],
                }]}),
                "export function createProduct(name, price) {}\n"
                "export function updateProduct(id, name, price) {}\n"
                "export function deleteProduct(id) {}\n",
                "createProduct", "updateProduct", "deleteProduct",
            ),
            "task_reservation": (
                json.dumps({"modules": [{
                    "name": "tasks", "actions": ["create", "edit", "delete"],
                    "forms": [{"name": "task_form", "fields": ["id", "title", "due_date"]}],
                }]}),
                "export function createTask(title, due_date) {}\n"
                "export function updateTask(id, title, due_date) {}\n"
                "export function deleteTask(id) {}\n",
                "createTask", "updateTask", "deleteTask",
            ),
        }
        for domain_name, (ux_spec, client, create_fn, edit_fn, delete_fn) in domains.items():
            contracts = _build_mutation_contracts(ux_spec, client)
            assert len(contracts) == 1, domain_name
            contract = contracts[0]
            # Structural shape identical across all three -- only the real
            # names differ, never the algorithm.
            assert set(contract.keys()) == {"module", "actions", "form_fields"}, domain_name
            assert set(contract["actions"].keys()) == {"create", "edit", "delete"}, domain_name
            assert contract["actions"]["create"]["client_function"] == create_fn
            assert contract["actions"]["edit"]["client_function"] == edit_fn
            assert contract["actions"]["edit"]["route_param"] == "id"
            assert contract["actions"]["delete"]["client_function"] == delete_fn
            assert "id" not in contract["form_fields"]

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
        """The worked example inside the hint must be derived from THIS
        candidate's own real mutation_contracts (here, the "works"
        domain fixture's own real updateWork(id, title)) -- never a
        fixed example naming a field or function from an unrelated
        domain a differently-domained candidate would never generate."""
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, "some failure",
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY,
        ))
        assert payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        hint = payload["repair_hint"]
        assert "updateWork" in hint  # this fixture's own real edit client function
        assert "useParams()" in hint
        assert "updateStudent" not in hint
        assert "StudentForm" not in hint


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


#: F-0069. `golden-work-131`'s own real, frozen `(code, path, detail)` --
#: never re-typed by hand, copied verbatim from the real evidence blob
#: (`sha256:35d6183c...`) the STAGE_FAILED outcome froze.
_GOLDEN_WORK_131_FINDINGS: tuple[tuple[str, str, str], ...] = (
    (
        "frontend_route_unreachable", "frontend/src/App.js",
        "<Route path='/tasks/edit/:id'> in frontend/src/App.js is never reached from "
        "anywhere else in the real frontend -- '/tasks/edit/' appears nowhere but this "
        "exact declaration, so no real Link, button or navigation call anywhere ever "
        "constructs a matching URL",
    ),
    (
        "frontend_root_path_unreachable", "frontend/src/App.js",
        "frontend/src/App.js declares a <Switch> with <Route> children but none of "
        "them ever matches the bare root path \"/\" -- a real end user landing on the "
        "app's own base URL sees a blank page",
    ),
    (
        "frontend_ui_form_missing_validation", "frontend/src/",
        "a <form> exists but the frontend shows no required/error/invalid validation marker",
    ),
    (
        "frontend_client_call_missing_import", "frontend/src/App.js",
        "frontend/src/App.js calls ['getTask', 'updateTask'] but never imports them "
        "from the real frontend_client module that declares them -- a real runtime "
        "ReferenceError, not a syntax error `node --check` can see",
    ),
)


class TestMultiFindingHintCoverage:
    """F-0069 (`FRONTEND_FORMS_MULTI_FINDING_CONVERGENCE_GAP`). Additive
    coverage: the exact original callback-arity hint text stays
    byte-unchanged; a new block is appended per real, supported prior
    finding code."""

    def test_a_attempt_1_default_strategy_is_unaffected_by_prior_findings(self) -> None:
        """`prior_findings` is a `structured_hint`-only concern -- passing
        it alongside the default strategy (attempt 1's own real shape)
        changes nothing, exactly like `prior_failure` itself already
        never appears in the default-strategy payload's own repair_hint."""
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, None, prior_findings=_GOLDEN_WORK_131_FINDINGS,
        ))
        assert payload["repair_strategy"] == _DEFAULT_REPAIR_STRATEGY
        assert "repair_hint" not in payload

    @pytest.mark.parametrize(
        ("code", "path", "detail"), _GOLDEN_WORK_131_FINDINGS, ids=lambda v: v if isinstance(v, str) else None,
    )
    def test_b_through_e_each_real_golden_work_131_finding_gets_its_own_correct_hint(
        self, code: str, path: str, detail: str,
    ) -> None:
        text = _structured_hint_text([], ((code, path, detail),))
        assert _SUPPORTED_HINT_INVARIANTS[code] in text
        assert path in text
        assert detail in text

    def test_f_multiple_supported_findings_are_all_represented(self) -> None:
        """All four of `golden-work-131`'s own real, simultaneous findings
        -- never just the first one a naive implementation might stop at."""
        text = _structured_hint_text([], _GOLDEN_WORK_131_FINDINGS)
        for code, path, detail in _GOLDEN_WORK_131_FINDINGS:
            assert code in text
            assert detail in text

    def test_g_an_unsupported_finding_is_dropped_from_the_structured_block_but_not_from_raw_evidence(
        self,
    ) -> None:
        """A real code this hint mechanism does not (yet) cover must never
        appear in the new structured block section -- but the FULL prompt
        payload's own `prior_attempt_failure` (built independently,
        unconditionally, from every real finding) must still carry it in
        full: no evidence is ever discarded, only the NEW enrichment is
        selective."""
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        # `frontend_ui_missing_edit_ui` was a real historical checker false
        # positive (F-0101), fixed at the checker level and deliberately
        # never given a hint entry (see TestF0101LabelHintCoverage) --
        # a stable, permanently-unsupported code for this example.
        unsupported = ("frontend_ui_missing_edit_ui", "frontend/src/", "no edit UI reference anywhere")
        prior_findings = (_GOLDEN_WORK_131_FINDINGS[0], unsupported)
        raw_failure = "; ".join(f"{c}:{p}:{d}" for c, p, d in prior_findings)
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, raw_failure,
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY, prior_findings=prior_findings,
        ))
        assert unsupported[0] in payload["prior_attempt_failure"]
        assert _GOLDEN_WORK_131_FINDINGS[0][0] in payload["repair_hint"]
        assert unsupported[0] not in payload["repair_hint"]

    def test_h_the_original_callback_arity_hint_text_is_byte_unchanged(self) -> None:
        """No regression: with no prior_findings (every existing call
        site's own real shape, this field's default), the hint is
        byte-identical to the original, pre-F-0069 text."""
        original = (
            "This is a retry. Do not simply reword the previous attempt -- apply this "
            "exact pattern. For any resource's edit or delete action, the route (not "
            "the form) supplies the record's real identifier: read it as the FIRST "
            "line of the routed component's own function body via "
            "`const { id } = useParams();` (imported from 'react-router-dom'), then "
            "pass it explicitly, in order, to the real client function named in "
            "mutation_contracts. If a form component is shared between create and "
            "edit, wrap the mutation call in a closure that supplies every real "
            "argument explicitly -- for example, derived from this candidate's own "
            "real edit contract: `onSubmit={async (title) => { const { id } = useParams(); "
            "await updateWork(id, title); }}`. NEVER bind a mutation prop directly to "
            "a bare multi-parameter client function reference -- a bare reference "
            "cannot supply the route's own identifier and silently shifts every "
            "other positional argument. A route's own identifier is never a "
            "user-entered form field -- do not render an input for it; "
            "mutation_contracts.form_fields already excludes it."
        )
        contracts = _build_mutation_contracts(_UX_SPEC_JSON, _CLIENT_JS)
        assert _structured_hint_text(contracts) == original

    def test_i_two_structurally_different_domains_produce_the_identical_invariant_sentence(self) -> None:
        """Only the real, candidate-owned path/detail facts vary between
        domains -- the fixed invariant sentence itself must be byte
        identical, proving no domain leaked into it."""
        student_text = _structured_hint_text([], ((
            "frontend_route_unreachable", "frontend/src/App.js",
            "<Route path='/students/edit/:id'> is never reached",
        ),))
        inventory_text = _structured_hint_text([], ((
            "frontend_route_unreachable", "frontend/src/App.js",
            "<Route path='/products/edit/:id'> is never reached",
        ),))
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        assert invariant in student_text
        assert invariant in inventory_text
        assert "/students/" not in invariant and "/products/" not in invariant

    def test_j_no_golden_domain_token_in_the_invariant_sentences(self) -> None:
        banned = ("student", "payment", "course", "task", "/tasks", "/students")
        for invariant in _SUPPORTED_HINT_INVARIANTS.values():
            lowered = invariant.lower()
            for token in banned:
                assert token not in lowered, (token, invariant)

    def test_k_the_real_stage_prompt_payload_carries_the_extended_hint(self) -> None:
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, "some failure",
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY,
            prior_findings=_GOLDEN_WORK_131_FINDINGS,
        ))
        for code, _path, _detail in _GOLDEN_WORK_131_FINDINGS:
            assert code in payload["repair_hint"]
        # The pre-existing callback-arity worked example is still present too.
        assert "useParams()" in payload["repair_hint"]

    def test_a_code_absent_from_the_supported_map_returns_no_blocks(self) -> None:
        assert _prior_finding_hint_blocks((("some_unknown_code", "path", "detail"),)) == []

    def test_the_same_code_twice_yields_only_one_block(self) -> None:
        finding = _GOLDEN_WORK_131_FINDINGS[0]
        blocks = _prior_finding_hint_blocks((finding, finding))
        assert len(blocks) == 1


class TestMultiFindingRealConvergence:
    def test_l_a_real_missing_import_defect_converges_on_the_structured_hint_retry(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """F-0069's own real end-to-end proof, the same shape
        `TestConvergence.test_12_...` already established for
        callback-arity: a real, controlled `_QueueModel` reproduces
        `golden-work-131`'s own real `frontend_client_call_missing_import`
        shape on attempt 1, and a correctly-wired version on attempt 2 --
        proving the extended retry mechanism actually converges within
        budget, never merely that the checker rejects the broken shape
        once in isolation."""
        queues = _happy_path_queues()
        queues["backend_contract"] = [(HonestState.PASS, _output(_BACKEND_CONTRACT_FILES))]
        queues["product_ux_spec"] = [(HonestState.PASS, _output({
            "product/ux_spec.json": _UX_SPEC_JSON,
        }))]
        queues["frontend_client"] = [(HonestState.PASS, _output({
            "frontend/src/client.js": _CLIENT_JS,
        }))]
        broken = _output({"frontend/src/App.js": _MISSING_IMPORT_APP_JS})
        fixed = _output({"frontend/src/App.js": _FIXED_APP_JS})
        queues["frontend_forms"] = [(HonestState.PASS, broken), (HonestState.PASS, fixed)]

        factory = _factory(queues)
        result = generate_staged_model_product(
            _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
        )
        assert "frontend/src/App.js" in result.files

        forms_model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
        assert len(forms_model.prompts) == 2
        second_payload = json.loads(forms_model.prompts[1])
        assert second_payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        assert "frontend_client_call_missing_import" in second_payload["prior_attempt_failure"]
        assert "frontend_client_call_missing_import" in second_payload["repair_hint"]


#: F-0099 (`FRONTEND_FORMS_LIST_LINK_WIRING_CONVERGENCE_GAP`). The real,
#: frozen `(code, path, detail)` findings from `factory-goal-mty4pvfe-vxppwp`
#: (`sha256:ec9585c3...`, STAGE_FAILED at `frontend_forms`, attempts 2/3
#: identical fingerprint) -- never re-typed by hand for the two already-
#: hinted route findings, and copied verbatim from the real ARK-ERR-0116
#: error string for all three.
_F0099_FINDINGS: tuple[tuple[str, str, str], ...] = (
    (
        "frontend_route_unreachable", "frontend/src/App.js",
        "<Route path='/pets/edit/:id'> in frontend/src/App.js is never reached from "
        "anywhere else in the real frontend -- '/pets/edit/' appears nowhere but this "
        "exact declaration, so no real Link, button or navigation call anywhere ever "
        "constructs a matching URL",
    ),
    (
        "frontend_route_unreachable", "frontend/src/App.js",
        "<Route path='/pets/delete/:id'> in frontend/src/App.js is never reached from "
        "anywhere else in the real frontend -- '/pets/delete/' appears nowhere but this "
        "exact declaration, so no real Link, button or navigation call anywhere ever "
        "constructs a matching URL",
    ),
    (
        "frontend_ui_create_unreachable_from_empty_state", "frontend/src/",
        "module 'pets' declares create, but no accessible interactive create/add/new "
        "control associated with it remains reachable; the action must be usable even "
        "when the collection is empty",
    ),
)


class TestF0099EmptyStateHintCoverage:
    """F-0099. The Q02 empty-state-create finding code did not have a
    structured-hint entry, so a retry sharing this exact fingerprint with
    the already-hinted `frontend_route_unreachable` findings above received
    guidance for those two but nothing for this third, simultaneous one."""

    def test_a_the_q02_code_is_now_in_the_supported_map(self) -> None:
        assert "frontend_ui_create_unreachable_from_empty_state" in _SUPPORTED_HINT_INVARIANTS

    def test_b_the_q02_hint_states_reachability_survives_zero_records(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "zero records" in invariant or "empty" in invariant
        assert "reachable" in invariant

    def test_c_the_q02_hint_never_requires_an_exact_button_label(self) -> None:
        """No exact word-matching requirement such as a button labelled
        'Create' -- multiple real, legal control shapes are named instead,
        and styling/wording is explicitly left unconstrained."""
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "labelled" not in invariant.lower()
        assert "No specific label" in invariant

    def test_d_the_route_unreachable_hint_still_states_the_original_reachability_rule(self) -> None:
        """F-0099 recurrence (`factory-goal-mtzkvowr-998jly`) strengthened
        this hint's wording; the original reachability sentence is
        preserved as a prefix, never removed -- only extended."""
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        assert invariant.startswith(
            "a declared parameterized route must be reachable through a real Link, "
            "button, or navigation call somewhere else in the frontend, built from "
            "the same static path prefix the route itself declares"
        )

    def test_e_all_three_simultaneous_f0099_finding_classes_compose(self) -> None:
        """The historical F-0099 replay: route-reachability guidance (one
        block, per the existing per-code dedup -- see test_f) and
        empty-state-create guidance must both reach the same retry hint at
        once -- never one overwriting the other."""
        text = _structured_hint_text([], _F0099_FINDINGS)
        assert "/pets/edit/" in text  # first same-code finding, per existing dedup
        assert "module 'pets' declares create" in text
        assert _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"] in text
        assert _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"] in text

    def test_f_the_two_same_code_route_findings_collapse_to_one_block(self) -> None:
        """F-0099's own real evidence has TWO `frontend_route_unreachable`
        findings (edit + delete) -- existing per-code dedup collapses them
        to one block; only the empty-state finding (a different code)
        contributes a second block. Pre-existing behavior, unchanged."""
        blocks = _prior_finding_hint_blocks(_F0099_FINDINGS)
        assert len(blocks) == 2
        codes = {c for c, _p, _d in _F0099_FINDINGS}
        assert codes == {"frontend_route_unreachable", "frontend_ui_create_unreachable_from_empty_state"}

    def test_g_no_pets_or_candidate_specific_token_in_the_invariant(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "pets" not in invariant.lower()

    def test_h_the_real_stage_prompt_payload_carries_all_three(self) -> None:
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        raw_failure = "; ".join(f"{c}:{p}:{d}" for c, p, d in _F0099_FINDINGS)
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, raw_failure,
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY, prior_findings=_F0099_FINDINGS,
        ))
        assert payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        assert "frontend_ui_create_unreachable_from_empty_state" in payload["repair_hint"]
        assert "frontend_route_unreachable" in payload["repair_hint"]
        # I. previous-attempt output / retry budget concerns are exercised by
        # `TestMultiFindingRealConvergence` end-to-end; this test isolates the
        # hint-composition path alone.
        assert "frontend_ui_create_unreachable_from_empty_state" in payload["prior_attempt_failure"]


class TestF0099RecurrenceHintStrengthening:
    """F-0099 recurrence (real evidence: `factory-goal-mtzkvowr-998jly`,
    `frontend_route_unreachable` x4 and `frontend_ui_create_unreachable_
    from_empty_state` x2, both against real list components rendering zero
    interactive elements that the retry's own output never touched). These
    two hints already existed and were already delivered; this class proves
    the strengthened wording now says what the recurrence showed was
    missing, without narrowing the checker or prescribing an exact repair."""

    def test_a_route_hint_states_a_declared_route_alone_is_insufficient(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        assert "alone is never sufficient" in invariant

    def test_b_route_hint_names_the_rendered_list_item_surface(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        assert "existing rendered list/item surface" in invariant

    def test_c_route_hint_says_existing_component_modification_may_be_required(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        assert "modify that existing component" in invariant

    def test_d_route_hint_ties_the_action_to_the_specific_record(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        assert "associated with that specific record" in invariant
        assert "record's own real id" in invariant

    def test_e_route_hint_prescribes_no_exact_wording(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        assert "No exact button text, route string, DOM shape, or styling" in invariant

    def test_f_route_hint_names_no_domain_or_candidate_specific_token(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        banned = ("customer", "ticket", "customerlist", "ticketlist", "pets", "student")
        lowered = invariant.lower()
        for token in banned:
            assert token not in lowered, token

    def test_g_empty_state_hint_covers_zero_records_explicitly(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "zero records" in invariant

    def test_h_empty_state_hint_requires_a_reachable_create_action(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "real, accessible interactive control" in invariant
        assert "remain reachable" in invariant

    def test_i_empty_state_hint_says_existing_component_modification_may_be_required(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "that existing component is where the reachable control is missing and must " \
            "be modified" in invariant

    def test_j_empty_state_hint_rejects_a_per_record_only_control(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "Never render the only such control inside a map/list of existing items" in invariant

    def test_k_empty_state_hint_rejects_a_route_declared_elsewhere_as_sufficient(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "declaring a create route elsewhere" in invariant
        assert "does not resolve this finding" in invariant

    def test_l_empty_state_hint_prescribes_no_exact_wording(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"]
        assert "No specific label, wording, or styling is required" in invariant

    def test_m_composed_recurrence_hint_carries_both_strengthened_invariants_and_dedups(
        self,
    ) -> None:
        """Historical replay of the real recurrence finding set (4 route +
        2 empty-state) through the real composer: both strengthened
        invariants appear, together, and the 4 identical-code route
        findings still collapse to exactly one block -- proves neither
        block suppresses the other and per-code dedup is unchanged."""
        recurrence_findings: tuple[tuple[str, str, str], ...] = (
            (
                "frontend_route_unreachable", "frontend/src/App.js",
                "<Route path='/customers/edit/:id'> is never reached from anywhere else "
                "in the real frontend",
            ),
            (
                "frontend_route_unreachable", "frontend/src/App.js",
                "<Route path='/customers/delete/:id'> is never reached from anywhere "
                "else in the real frontend",
            ),
            (
                "frontend_route_unreachable", "frontend/src/App.js",
                "<Route path='/tickets/edit/:id'> is never reached from anywhere else "
                "in the real frontend",
            ),
            (
                "frontend_route_unreachable", "frontend/src/App.js",
                "<Route path='/tickets/delete/:id'> is never reached from anywhere else "
                "in the real frontend",
            ),
            (
                "frontend_ui_create_unreachable_from_empty_state", "frontend/src/",
                "module 'customers' declares create, but no accessible interactive "
                "create/add/new control remains reachable at zero records",
            ),
            (
                "frontend_ui_create_unreachable_from_empty_state", "frontend/src/",
                "module 'tickets' declares create, but no accessible interactive "
                "create/add/new control remains reachable at zero records",
            ),
        )
        blocks = _prior_finding_hint_blocks(recurrence_findings)
        assert len(blocks) == 2
        text = _structured_hint_text([], recurrence_findings)
        assert _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"] in text
        assert _SUPPORTED_HINT_INVARIANTS["frontend_ui_create_unreachable_from_empty_state"] in text

    def test_n_retry_budget_and_repair_strategy_selection_are_unchanged(self) -> None:
        """No convergence-engine behavior changed this turn -- only hint
        text. `_repair_strategy_for_attempt` still escalates to the
        structured-hint strategy starting at attempt 2, unchanged."""
        assert _repair_strategy_for_attempt(1) == _DEFAULT_REPAIR_STRATEGY
        assert _repair_strategy_for_attempt(2) == _STRUCTURED_HINT_REPAIR_STRATEGY

    def test_o_previous_attempt_output_wiring_is_unchanged(self) -> None:
        """`_stage_prompt` still threads `previous_attempt_files` into
        `previous_attempt_output` unchanged by this turn's hint-wording
        edit."""
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        prior_files = {"frontend/src/App.js": "// prior attempt content"}
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, "frontend_route_unreachable:frontend/src/App.js:x",
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY,
            prior_findings=(("frontend_route_unreachable", "frontend/src/App.js", "x"),),
            previous_attempt_files=prior_files,
        ))
        assert payload["previous_attempt_output"] == prior_files


#: F-0101 (`FRONTEND_UI_EDIT_EXPORT_MISDETECTION_AND_LABEL_HINT_GAP`). The
#: real, frozen `(code, path, detail)` findings from
#: `factory-goal-mtz6bst2-myhr15` (`sha256:70a83649...`, STAGE_FAILED at
#: `frontend_forms`, full 4-attempt budget exhausted) -- copied verbatim
#: from the real ARK-ERR-0116 error string. `frontend_ui_missing_edit_ui`
#: is a real historical checker false positive, fixed at the checker
#: level (`_exported_js_names`), never given a retry hint here; only
#: `frontend_ui_form_control_unlabelled` -- the genuine defect -- gets one.
_F0101_FINDINGS: tuple[tuple[str, str, str], ...] = (
    (
        "frontend_ui_missing_edit_ui", "frontend/src/",
        "product_ux_spec declares an edit action but the frontend never "
        "references an update/edit-named client function anywhere -- a "
        "create form alone does not satisfy a declared edit action",
    ),
    (
        "frontend_ui_form_control_unlabelled", "frontend/src/",
        "every input/select/textarea must have an accessible name: "
        "associate a label with htmlFor+id, wrap the control in its "
        "label, or use a non-empty aria-label/aria-labelledby; adjacent "
        "label text alone is not exposed as the control's accessible name",
    ),
)


class TestF0101LabelHintCoverage:
    """F-0101B. `frontend_ui_form_control_unlabelled` did not have a
    structured hint entry, unlike `frontend_ui_create_unreachable_from_
    empty_state` (F-0099) before it -- the same class of gap, a
    different finding code."""

    def test_a_the_label_code_is_now_in_the_supported_map(self) -> None:
        assert "frontend_ui_form_control_unlabelled" in _SUPPORTED_HINT_INVARIANTS

    def test_b_the_label_hint_names_every_real_legal_mechanism(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_form_control_unlabelled"]
        assert "htmlFor" in invariant
        assert "aria-label" in invariant
        assert "aria-labelledby" in invariant
        assert "label" in invariant.lower()

    def test_c_the_label_hint_never_requires_exact_wording(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_form_control_unlabelled"]
        assert "no specific label text" in invariant.lower()

    def test_d_no_candidate_specific_token_in_the_invariant(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_form_control_unlabelled"]
        banned = ("customer", "ticket", "student", "payment", "course", "pets", "task")
        lowered = invariant.lower()
        for token in banned:
            assert token not in lowered, token

    def test_e_the_missing_edit_ui_code_never_received_a_hint(self) -> None:
        """The checker fix (`_exported_js_names`) resolves this class at
        the source; a retry hint was never needed for it and none was
        added."""
        assert "frontend_ui_missing_edit_ui" not in _SUPPORTED_HINT_INVARIANTS

    def test_f_the_historical_f0101_replay_hints_only_the_genuine_finding(self) -> None:
        """Section 16's own explicit requirement: after the checker fix,
        replaying the exact real historical finding set must compose a
        hint for the genuine label defect, and never invent guidance for
        the (now-impossible) false edit finding, which this dict still
        does not name."""
        text = _structured_hint_text([], _F0101_FINDINGS)
        assert _SUPPORTED_HINT_INVARIANTS["frontend_ui_form_control_unlabelled"] in text
        assert "frontend_ui_missing_edit_ui" not in text

    def test_g_the_real_stage_prompt_payload_carries_the_label_hint(self) -> None:
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        raw_failure = "; ".join(f"{c}:{p}:{d}" for c, p, d in _F0101_FINDINGS)
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, raw_failure,
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY, prior_findings=_F0101_FINDINGS,
        ))
        assert payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        assert "frontend_ui_form_control_unlabelled" in payload["repair_hint"]

    def test_h_retry_budget_is_unchanged_and_route_hint_retains_its_original_rule(self) -> None:
        """No behavior change to how many attempts a stage gets; the route
        hint's own original reachability sentence (predating both F-0099
        and its later recurrence fix) is still present as a prefix."""
        route_invariant = _SUPPORTED_HINT_INVARIANTS["frontend_route_unreachable"]
        assert route_invariant.startswith(
            "a declared parameterized route must be reachable through a real Link, "
            "button, or navigation call somewhere else in the frontend, built from "
            "the same static path prefix the route itself declares"
        )


#: FRONTEND_FORMS_LOCAL_COMPONENT_COMPLETENESS_GAP. The real, frozen
#: `(code, path, detail)` findings mechanically reproducible from
#: `factory-goal-mu1oieg4-3bye3k` (`sha256:5cefea47...`, STAGE_FAILED at
#: `frontend_forms`, full 4-attempt budget exhausted, `finish_reason:
#: "stop"`, not truncated) -- copied verbatim from the real ARK-ERR-0116
#: error string for both real, simultaneous missing local components.
_LOCAL_IMPORT_FINDINGS: tuple[tuple[str, str, str], ...] = (
    (
        "frontend_local_import_unresolved", "frontend/src/App.js",
        "frontend/src/App.js imports './EquipmentForm' but no such file exists "
        "anywhere in this real candidate -- a real webpack build fails outright "
        "with \"Module not found: Error: Can't resolve './EquipmentForm'\"",
    ),
    (
        "frontend_local_import_unresolved", "frontend/src/App.js",
        "frontend/src/App.js imports './RentalForm' but no such file exists "
        "anywhere in this real candidate -- a real webpack build fails outright "
        "with \"Module not found: Error: Can't resolve './RentalForm'\"",
    ),
)


class TestFrontendLocalImportHintCoverage:
    """`FRONTEND_FORMS_LOCAL_COMPONENT_COMPLETENESS_GAP`.
    `frontend_local_import_unresolved` did not have a structured hint
    entry, unlike `frontend_client_call_missing_import`/F-0099/F-0101B
    before it -- the same class of gap (a real, existing, unmodified
    checker fires correctly, but a retry received no actionable repair
    instruction beyond the raw finding text), a different finding code
    and a different repair shape (creating a whole new file is a legal
    fix here; adding an import line for something that already exists,
    F-0069's own shape, is not enough on its own)."""

    def test_a_the_code_is_now_in_the_supported_map(self) -> None:
        assert "frontend_local_import_unresolved" in _SUPPORTED_HINT_INVARIANTS

    def test_b_the_hint_offers_the_emit_repair_action(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_local_import_unresolved"]
        assert "emit the missing imported local file" in invariant
        assert "real, working implementation content" in invariant

    def test_c_the_hint_offers_the_remove_or_inline_repair_action(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_local_import_unresolved"]
        assert "remove that" in invariant
        assert "inline in the" in invariant
        assert "reuse an already-existing local file" in invariant

    def test_d_the_hint_forbids_assuming_a_future_stage_completes_it(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_local_import_unresolved"]
        assert "a later stage or a future attempt will create the missing file" in invariant

    def test_e_no_candidate_specific_token_in_the_invariant(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_local_import_unresolved"]
        banned = (
            "equipmentform", "rentalform", "equipment", "rental", "customer", "ticket", "student",
        )
        lowered = invariant.lower()
        for token in banned:
            assert token not in lowered, token

    def test_f_the_frozen_real_replay_hints_both_missing_components_coherently(self) -> None:
        """Replaying the exact real, frozen finding set from
        `factory-goal-mu1oieg4-3bye3k` (two real findings, the identical
        code) must never produce two contradictory or duplicate literal
        blocks for the one code -- the same existing per-code dedup
        `TestF0099RouteWiringHintCoverage` already proved for two
        simultaneous `frontend_route_unreachable` findings: one
        structured block, naming the first real observed detail. Both
        real missing filenames still survive, unconditionally, in the
        raw `prior_attempt_failure` string (proven in test_g below) --
        only the new, selective enrichment ever drops the second."""
        blocks = _prior_finding_hint_blocks(_LOCAL_IMPORT_FINDINGS)
        assert len(blocks) == 1
        text = _structured_hint_text([], _LOCAL_IMPORT_FINDINGS)
        assert _SUPPORTED_HINT_INVARIANTS["frontend_local_import_unresolved"] in text
        assert "./EquipmentForm" in text

    def test_g_the_real_stage_prompt_payload_carries_the_hint_and_the_failed_app_js(self) -> None:
        """The canonical retry-prompt, reconstructed: the next attempt's
        real prompt must simultaneously carry the raw finding, the new
        actionable repair hint, the failed previous App.js (via the
        existing, unmodified `previous_attempt_output` mechanism), and
        the normal multi-file output contract."""
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        raw_failure = "; ".join(f"{c}:{p}:{d}" for c, p, d in _LOCAL_IMPORT_FINDINGS)
        failed_app_js = (
            "import EquipmentForm from './EquipmentForm';\nimport RentalForm from './RentalForm';\n"
        )
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, raw_failure,
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY, prior_findings=_LOCAL_IMPORT_FINDINGS,
            previous_attempt_files={"frontend/src/App.js": failed_app_js},
        ))
        assert payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        assert "frontend_local_import_unresolved" in payload["repair_hint"]
        # Both real missing filenames survive, unconditionally, in the raw
        # failure string -- even though the structured block above names
        # only the first (test_f's own dedup proof).
        assert "./EquipmentForm" in payload["prior_attempt_failure"]
        assert "./RentalForm" in payload["prior_attempt_failure"]
        assert payload["previous_attempt_output"]["frontend/src/App.js"] == failed_app_js
        assert payload["output_contract"]["schema"] == {
            "files": [{"path": "relative/posix/path", "content": "complete text"}],
        }

    def test_h_retry_budget_and_repair_strategy_selection_are_unchanged(self) -> None:
        """No convergence-engine behavior changed this turn -- only rule
        and hint text."""
        assert _repair_strategy_for_attempt(1) == _DEFAULT_REPAIR_STRATEGY
        assert _repair_strategy_for_attempt(2) == _STRUCTURED_HINT_REPAIR_STRATEGY


class TestFrontendLocalImportConvergence:
    def test_m_a_real_missing_local_component_file_converges_by_emitting_it(
        self, tmp_path: pathlib.Path,
    ) -> None:
        """The new hint's own end-to-end proof, the same shape
        `TestMultiFindingRealConvergence.test_l_...` already established
        for a missing client-function import: a controlled `_QueueModel`
        reproduces this session's own real `frontend_local_import_
        unresolved` shape on attempt 1 (a real relative import to a form
        component this stage's own output never emits), and a correctly
        completed version -- emitting the previously-missing component
        file alongside the unchanged App.js, in the SAME response -- on
        attempt 2, proving the extended contract+hint actually converges
        within budget, never merely that the checker rejects the broken
        shape once in isolation."""
        queues = _happy_path_queues()
        queues["backend_contract"] = [
            (HonestState.PASS, _output(_LOCAL_IMPORT_BACKEND_CONTRACT_FILES)),
        ]
        queues["product_ux_spec"] = [(HonestState.PASS, _output({
            "product/ux_spec.json": _LOCAL_IMPORT_UX_SPEC_JSON,
        }))]
        queues["frontend_client"] = [(HonestState.PASS, _output({
            "frontend/src/client.js": _LOCAL_IMPORT_CLIENT_JS,
        }))]
        broken = _output({"frontend/src/App.js": _LOCAL_IMPORT_BROKEN_APP_JS})
        fixed = _output({
            "frontend/src/App.js": _LOCAL_IMPORT_BROKEN_APP_JS,
            "frontend/src/NoteForm.js": _NOTE_FORM_STANDALONE_JS,
        })
        queues["frontend_forms"] = [(HonestState.PASS, broken), (HonestState.PASS, fixed)]

        factory = _factory(queues)
        result = generate_staged_model_product(
            _blueprint(), factory, _workspace(tmp_path), vocabulary=StageVocabulary.load(REPO),
        )
        assert "frontend/src/NoteForm.js" in result.files
        assert "frontend/src/App.js" in result.files

        forms_model = factory.models["frontend_forms"]  # type: ignore[attr-defined]
        assert len(forms_model.prompts) == 2
        second_payload = json.loads(forms_model.prompts[1])
        assert second_payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        assert "frontend_local_import_unresolved" in second_payload["prior_attempt_failure"]
        assert "frontend_local_import_unresolved" in second_payload["repair_hint"]
        assert (
            second_payload["previous_attempt_output"]["frontend/src/App.js"]
            == _LOCAL_IMPORT_BROKEN_APP_JS
        )


class TestFrontendLocalImportFrozenReplay:
    """Section 18's own requirement: prove parser output -> merged file
    set -> local-import checker -> hint lookup against the real, frozen
    `factory-goal-mu1oieg4-3bye3k` evidence blob's own real persisted
    bytes -- read fresh from disk, never re-typed by hand -- with no
    model call."""

    @staticmethod
    def _real_evidence() -> dict:
        blob = (
            REPO / "var" / "factory" / "evidence" / "blobs" / "sha256" / "5c"
            / "5cefea47b03c999fe4654f15d32fef7e3681b0f62b12f199cc7a67df104e2e46"
        )
        return json.loads(blob.read_text(encoding="utf-8"))

    @staticmethod
    def _real_merged_files() -> dict[str, str]:
        """The real stage's own `{**visible_files, **stage_files}` merge
        (`_generate_one_stage`, unchanged) -- `apiClient.js` is a real,
        frozen, unmodified prior-stage (`frontend_client`) file this
        stage's own output never touches, read fresh from the real
        candidate workspace, never re-typed by hand."""
        evidence = TestFrontendLocalImportFrozenReplay._real_evidence()
        raw = json.loads(evidence["last_raw_output"])
        stage_files = {f["path"]: f["content"] for f in raw["files"]}
        api_client = (
            REPO / "var" / "factory" / "candidates" / "factory-goal-mu1oieg4-3bye3k"
            / "frontend" / "src" / "apiClient.js"
        ).read_text(encoding="utf-8")
        return {"frontend/src/apiClient.js": api_client, **stage_files}

    def test_a_the_real_raw_output_parses_to_exactly_one_file(self) -> None:
        evidence = self._real_evidence()
        raw = json.loads(evidence["last_raw_output"])
        assert [f["path"] for f in raw["files"]] == ["frontend/src/App.js"]

    def test_b_the_real_merged_state_produces_both_local_import_findings(self) -> None:
        findings = _frontend_local_import_findings(self._real_merged_files())
        codes = {f.code for f in findings}
        assert codes == {"frontend_local_import_unresolved"}
        assert any("./EquipmentForm" in f.detail for f in findings)
        assert any("./RentalForm" in f.detail for f in findings)
        assert len(findings) == 2

    def test_c_the_real_findings_map_to_the_new_actionable_hint(self) -> None:
        findings = _frontend_local_import_findings(self._real_merged_files())
        prior_findings = tuple((f.code, f.path, f.detail) for f in findings)
        text = _structured_hint_text([], prior_findings)
        assert _SUPPORTED_HINT_INVARIANTS["frontend_local_import_unresolved"] in text


class TestSuccessFeedbackHintCoverage:
    """`FRONTEND_SUCCESS_FEEDBACK_RETRY_HINT_GAP` (real evidence: `factory-
    goal-mu2h4fda-yyz4hh`). `frontend_ui_missing_success_feedback` did not
    have a structured hint entry, unlike `frontend_client_call_missing_
    import`/F-0099/F-0101/`frontend_local_import_unresolved` before it --
    the same class of gap (a real, existing, unmodified checker fires
    correctly, but a retry received only the raw finding text and the
    generic mutation-contracts callback-arity hint, unrelated to this
    finding). Analysis this session proved PREVENTION already complete
    (`STAGED_GENERATION_STAGES.md#9` already states this invariant) --
    this fix is convergence-only; the rule text is untouched."""

    def test_a_the_code_is_now_in_the_supported_map(self) -> None:
        assert "frontend_ui_missing_success_feedback" in _SUPPORTED_HINT_INVARIANTS

    def test_b_the_hint_requires_feedback_only_after_genuine_success(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_missing_success_feedback"]
        assert "genuinely resolves" in invariant
        assert "never before it resolves" in invariant

    def test_c_the_hint_forbids_treating_error_as_success(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_missing_success_feedback"]
        assert "never on a failed attempt" in invariant
        assert "a real error marker is never itself a success marker" in invariant

    def test_d_the_hint_permits_either_the_form_or_the_parent(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_missing_success_feedback"]
        assert "in the form itself or in the parent component" in invariant

    def test_e_the_hint_prescribes_no_specific_implementation(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_missing_success_feedback"]
        assert "No specific wording, library, modal, redirect, or component structure" in invariant

    def test_f_no_candidate_specific_token_in_the_invariant(self) -> None:
        invariant = _SUPPORTED_HINT_INVARIANTS["frontend_ui_missing_success_feedback"]
        banned = ("patient", "appointment", "veterinary", "customer", "ticket", "student")
        lowered = invariant.lower()
        for token in banned:
            assert token not in lowered, token

    def test_g_the_real_stage_prompt_payload_carries_the_hint_and_the_failed_files(self) -> None:
        """The canonical retry-prompt, reconstructed with realistic
        `visible_files` (so the pre-existing generic mutation-contracts
        callback-arity hint is present too, exactly as it was in the real
        run) -- the next attempt's real prompt must simultaneously carry
        the raw finding, the new actionable hint, the failed previous
        frontend files, the pre-existing generic hint, and the normal
        multi-file output contract."""
        decl = next(s for s in StageVocabulary.load(REPO).stages() if s.name == "frontend_forms")
        visible = {"product/ux_spec.json": _UX_SPEC_JSON, "frontend/src/client.js": _CLIENT_JS}
        finding = (
            "frontend_ui_missing_success_feedback", "frontend/src/",
            "product_ux_spec declares a mutating action but the frontend shows no "
            "success/feedback marker after it",
        )
        raw_failure = ":".join(finding)
        failed_files = {"frontend/src/App.js": _WORK_FORM_JS}
        payload = json.loads(_stage_prompt(
            decl, _blueprint(), visible, raw_failure,
            repair_strategy=_STRUCTURED_HINT_REPAIR_STRATEGY, prior_findings=(finding,),
            previous_attempt_files=failed_files,
        ))
        assert payload["repair_strategy"] == _STRUCTURED_HINT_REPAIR_STRATEGY
        assert "frontend_ui_missing_success_feedback" in payload["repair_hint"]
        assert "add a visible success/feedback marker after a" in payload["task"]
        assert payload["prior_attempt_failure"] == raw_failure
        assert payload["previous_attempt_output"] == failed_files
        # The pre-existing generic mutation-contracts hint is still present too.
        assert "useParams()" in payload["repair_hint"]

    def test_h_retry_budget_and_repair_strategy_selection_are_unchanged(self) -> None:
        assert _repair_strategy_for_attempt(1) == _DEFAULT_REPAIR_STRATEGY
        assert _repair_strategy_for_attempt(2) == _STRUCTURED_HINT_REPAIR_STRATEGY


class TestSuccessFeedbackFrozenReplay:
    """Prove parser output -> merged file set -> `frontend_forms` findings
    -> hint lookup against the real, frozen `factory-goal-mu2h4fda-yyz4hh`
    evidence blob's own real persisted bytes -- read fresh from disk,
    never re-typed by hand -- with no model call. This also protects
    c1e7785's own live-proven local-import behavior from regression: the
    real merged state must show zero `frontend_local_import_unresolved`
    findings alongside the one genuine success-feedback finding."""

    @staticmethod
    def _real_merged_files() -> dict[str, str]:
        blob = (
            REPO / "var" / "factory" / "evidence" / "blobs" / "sha256" / "3e"
            / "3e0e21dc85fbabd956912c720e2bcdf523adacb8d75c4490640284b9e7fec3c3"
        )
        evidence = json.loads(blob.read_text(encoding="utf-8"))
        raw = json.loads(evidence["last_raw_output"])
        stage_files = {f["path"]: f["content"] for f in raw["files"]}
        cand = REPO / "var" / "factory" / "candidates" / "factory-goal-mu2h4fda-yyz4hh"
        visible = {
            "product/ux_spec.json": (cand / "product/ux_spec.json").read_text(encoding="utf-8"),
            "frontend/src/apiClient.js": (
                cand / "frontend/src/apiClient.js"
            ).read_text(encoding="utf-8"),
            "frontend/src/index.js": (cand / "frontend/src/index.js").read_text(encoding="utf-8"),
        }
        return {**visible, **stage_files}

    def test_a_the_real_merged_state_produces_exactly_the_one_real_finding(self) -> None:
        findings = _frontend_forms_findings(self._real_merged_files())
        codes = {f.code for f in findings}
        assert codes == {"frontend_ui_missing_success_feedback"}
        assert len(findings) == 1

    def test_b_the_real_merged_state_has_no_local_import_regression(self) -> None:
        """c1e7785 non-regression: the real candidate's own final attempt
        legitimately split forms into separate files and emitted all of
        them together -- zero unresolved local imports."""
        findings = _frontend_local_import_findings(self._real_merged_files())
        assert findings == []

    def test_c_the_real_finding_maps_to_the_new_actionable_hint(self) -> None:
        findings = _frontend_forms_findings(self._real_merged_files())
        prior_findings = tuple((f.code, f.path, f.detail) for f in findings)
        text = _structured_hint_text([], prior_findings)
        assert _SUPPORTED_HINT_INVARIANTS["frontend_ui_missing_success_feedback"] in text
