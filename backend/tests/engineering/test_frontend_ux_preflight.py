from __future__ import annotations

import json
import pathlib
import re

from arkali.engineering.factory.frontend_actionability_preflight import _create_access_findings
from arkali.engineering.factory.frontend_manifest_preflight import (
    _frontend_local_import_findings,
    _react_router_missing_import_findings,
    _repair_missing_react_router_imports,
    _route_component_missing_props_findings,
)
from arkali.engineering.factory.frontend_ux_preflight import (
    _exported_js_names,
    _form_quality_findings,
    _shadowed_route_findings,
    _unreachable_module_findings,
    _unreachable_parameterized_route_findings,
    _unused_client_export_findings,
    _update_like_client_exports,
    _ux_spec_mutation_findings,
    _ux_spec_shell_findings,
)
from arkali.engineering.factory.semantic_finding import SemanticFinding
from tests.engineering.test_product_ux_spec import (
    _GOLDEN_WORK_064_DATA_MODEL,
    _valid_spec_files,
)

_STUDENT_MODEL = json.dumps({"table_name": "students", "fields": {"id": {"type": "integer"}}})
_COURSE_MODEL = json.dumps({"table_name": "courses", "fields": {"id": {"type": "integer"}}})
_PAYMENT_MODEL = json.dumps({"table_name": "payments", "fields": {"id": {"type": "integer"}}})


def test_flags_a_bare_list_against_the_real_nested_multi_model_shape() -> None:
    """golden-work-064 (session evidence, frozen): before the fix, this
    exact real backend shape -- one data_model.json nesting three real
    models -- counted as one model (`len(models) < 2`), so the bare-list
    gate silently never fired for it at all."""
    files = {
        "backend/data_model.json": _GOLDEN_WORK_064_DATA_MODEL,
        "frontend/src/StudentList.js": (
            "const StudentList = () => (<ul>{students.map(s => "
            "<li key={s.id}>{s.name}</li>)}</ul>);"
        ),
    }
    findings = _unreachable_module_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_unreachable_modules"
    assert "students" in findings[0].detail


def test_flags_a_bare_list_when_backend_declares_multiple_unreachable_models() -> None:
    """dershane-demo-003 (real repository evidence): backend declared
    student/course/payment models; the shipped frontend was one component
    rendering one <ul> of student names with no way to reach the other two."""
    files = {
        "backend/student_model.json": _STUDENT_MODEL,
        "backend/course_model.json": _COURSE_MODEL,
        "backend/payment_model.json": _PAYMENT_MODEL,
        "frontend/src/StudentList.js": (
            "const StudentList = () => (<ul>{students.map(s => "
            "<li key={s.id}>{s.name}</li>)}</ul>);"
        ),
    }
    findings = _unreachable_module_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_unreachable_modules"
    assert "students" in findings[0].detail


def test_is_silent_when_navigation_is_present() -> None:
    files = {
        "backend/student_model.json": _STUDENT_MODEL,
        "backend/course_model.json": _COURSE_MODEL,
        "frontend/src/App.js": (
            "import { Link } from 'react-router-dom';\n"
            "const App = () => (<nav><Link to='/students'>Students</Link>"
            "<Link to='/courses'>Courses</Link></nav>);"
        ),
    }
    assert _unreachable_module_findings(files) == []


def test_is_silent_when_an_interactive_control_is_present() -> None:
    files = {
        "backend/student_model.json": _STUDENT_MODEL,
        "backend/course_model.json": _COURSE_MODEL,
        "frontend/src/App.js": (
            "const App = () => (<form><input name='q' /><button>Go</button></form>);"
        ),
    }
    assert _unreachable_module_findings(files) == []


def test_is_silent_when_only_one_model_is_declared() -> None:
    files = {
        "backend/student_model.json": _STUDENT_MODEL,
        "frontend/src/StudentList.js": "<ul>{students.map(s => <li>{s.name}</li>)}</ul>",
    }
    assert _unreachable_module_findings(files) == []


def test_is_silent_when_no_frontend_source_exists_yet() -> None:
    files = {
        "backend/student_model.json": _STUDENT_MODEL,
        "backend/course_model.json": _COURSE_MODEL,
    }
    assert _unreachable_module_findings(files) == []


#: The test matrix below is the deterministic proof asked for before any
#: real Ollama run: A (bare-list, above) / B-G here. All fixtures use a
#: deliberately non-Dershane, non-Golden-Product e-commerce domain
#: (products/categories/orders) to prove these checks generalize.

_PROFESSIONAL_SHELL_JS = """
import { Link } from "react-router-dom";
function App() {
  return (
    <nav>
      <Link to="/">Dashboard</Link>
      <Link to="/products">Products</Link>
      <Link to="/products/create">Create Product</Link>
      <Link to="/categories">Categories</Link>
      <Link to="/orders">Orders</Link>
      <Link to="/orders/create">Create Order</Link>
    </nav>
  );
}
function ProductForm() {
  return (
    <form>
      <label htmlFor="name">Name</label>
      <input id="name" required />
      <button type="submit">Save</button>
    </form>
  );
}
function OrdersList() {
  if (loading) return <div>loading</div>;
  if (empty) return <div>empty</div>;
  if (error) return <div>error <button onClick={retry}>Retry</button></div>;
  const onDelete = () => { if (window.confirm("Are you sure?")) { deleteOrder(); } };
  return <div>success</div>;
}
"""


def test_b_navigation_present_but_a_declared_module_is_unreachable() -> None:
    """A nav bar exists, but one product_ux_spec-declared destination
    (Orders) never appears anywhere in the frontend -- still a FAIL."""
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": (
            'import { Link } from "react-router-dom";\n'
            'function App() { return (<nav>'
            '<Link to="/products">Products</Link>'
            '<Link to="/categories">Categories</Link>'
            "</nav>); }"
        ),
    }
    findings = _ux_spec_shell_findings(files)
    codes = {f.code for f in findings}
    assert "frontend_ui_navigation_destination_unreachable" in codes
    unreachable_finding = next(
        f for f in findings if f.code == "frontend_ui_navigation_destination_unreachable"
    )
    assert "Orders" in unreachable_finding.detail


def test_c_backend_has_create_capability_but_frontend_has_no_mutation_ui() -> None:
    """The backend exposes POST /products and POST/DELETE /orders (real
    create/delete capability, reconciled into product_ux_spec's own
    "create"/"delete" actions) but the frontend renders navigation only,
    with no <form> anywhere -- a FAIL distinct from the bare-list check,
    since real navigation does exist here."""
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": (
            'import { Link } from "react-router-dom";\n'
            'function App() { return (<nav>'
            '<Link to="/">Dashboard</Link>'
            '<Link to="/products">Products</Link>'
            '<Link to="/categories">Categories</Link>'
            '<Link to="/orders">Orders</Link>'
            "</nav>); }"
        ),
    }
    findings = _ux_spec_mutation_findings(files)
    assert any(f.code == "frontend_ui_missing_mutation_ui" for f in findings)


def test_d_form_exists_with_no_label_and_no_validation_marker() -> None:
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": (
            _PROFESSIONAL_SHELL_JS.replace(
                '<label htmlFor="name">Name</label>\n      <input id="name" required />',
                '<input id="name" />',
            )
        ),
    }
    findings = _ux_spec_mutation_findings(files)
    codes = {f.code for f in findings}
    assert "frontend_ui_form_missing_labels" in codes
    assert "frontend_ui_form_missing_validation" in codes


def test_adjacent_label_text_without_association_is_not_an_accessible_name() -> None:
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS.replace(
            '<label htmlFor="name">Name</label>\n      <input id="name" required />',
            '<label>Name</label>\n      <input required />',
        ),
    }
    findings = _ux_spec_mutation_findings(files)
    assert any(f.code == "frontend_ui_form_control_unlabelled" for f in findings)


def test_wrapping_label_gives_its_control_an_accessible_name() -> None:
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS.replace(
            '<label htmlFor="name">Name</label>\n      <input id="name" required />',
            '<label>Name <input required /></label>',
        ),
    }
    findings = _ux_spec_mutation_findings(files)
    assert not any(f.code == "frontend_ui_form_control_unlabelled" for f in findings)


def test_matching_jsx_identifier_expressions_associate_label_and_control() -> None:
    """golden-work-126: mapped fields commonly bind both attributes to the
    same runtime identifier instead of a quoted constant."""
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS.replace(
            '<label htmlFor="name">Name</label>\n      <input id="name" required />',
            "<label htmlFor={field}>Name</label>\n      <input id={field} required />",
        ),
    }
    findings = _ux_spec_mutation_findings(files)
    assert not any(f.code == "frontend_ui_form_control_unlabelled" for f in findings)


def test_different_jsx_identifier_expressions_do_not_associate_a_label() -> None:
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS.replace(
            '<label htmlFor="name">Name</label>\n      <input id="name" required />',
            "<label htmlFor={labelId}>Name</label>\n      <input id={controlId} required />",
        ),
    }
    findings = _ux_spec_mutation_findings(files)
    assert any(f.code == "frontend_ui_form_control_unlabelled" for f in findings)


def test_f_a_professional_multi_module_shell_structurally_passes() -> None:
    """Every declared navigation destination reachable, real forms with
    labels and validation, loading/empty/error/success states, and a
    confirmation step before the declared delete action -- the positive
    control proving these checks do not merely reject, they let a real,
    complete implementation through."""
    files = {**_valid_spec_files(), "frontend/src/App.js": _PROFESSIONAL_SHELL_JS}
    assert _ux_spec_shell_findings(files) == []
    assert _ux_spec_mutation_findings(files) == []
    assert _unreachable_module_findings(files) == []


def test_create_capability_requires_a_reachable_create_control_even_when_empty() -> None:
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS
        .replace('<Link to="/products/create">Create Product</Link>', "")
        .replace("function ProductForm() {", "function ProductForm() { createProduct(); "),
    }
    findings = _ux_spec_mutation_findings(files)
    assert any(f.code == "frontend_ui_create_unreachable_from_empty_state" for f in findings)


class TestEmptyStateCreateReachabilityControlFlow:
    """`F0099_CHECKER_FALSE_NEGATIVE` (real evidence: `factory-goal-
    mu1hy9w1-qn30iv`). `_create_access_findings` searched the entire
    concatenated frontend text for a matching create control, with no
    control-flow awareness -- a real zero-record early return (`if
    (clients.length === 0) return <div>No clients found</div>;`)
    genuinely occurred, in both real modules, BEFORE the real, later
    `return (...)` containing the real, correctly-worded `<Link
    to="/clients/create">Create Client</Link>`, so this check was
    satisfied even though the real create control is genuinely
    unreachable at zero records. `STAGED_GENERATION_STAGES.md#9`
    already states the correct invariant ("an empty-state branch must
    never hide the only path to its form"); this was checker under-
    enforcement, not a requirement gap. The same finding code
    (`frontend_ui_create_unreachable_from_empty_state`) is reused --
    no new taxonomy."""

    class _Module:
        def __init__(self, name: str, actions: tuple[str, ...]) -> None:
            self.name = name
            self.navigation_label = name.capitalize()
            self.actions = actions

    class _Spec:
        def __init__(self, modules: list) -> None:
            self.modules = modules

    @staticmethod
    def _finding(code: str, path: str, detail: str) -> object:
        return SemanticFinding(code=code, path=path, detail=detail)

    def _findings(self, frontend: str, module_names: tuple[str, ...] = ("clients",)) -> list:
        modules = [self._Module(n, ("create", "view")) for n in module_names]
        return _create_access_findings(self._Spec(modules), frontend, self._finding)

    def test_a_zero_state_without_create_is_flagged(self) -> None:
        frontend = "if (clients.length === 0) return <div>No clients found</div>;"
        codes = {f.code for f in self._findings(frontend)}
        assert "frontend_ui_create_unreachable_from_empty_state" in codes

    def test_b_create_inside_the_zero_state_branch_passes(self) -> None:
        frontend = (
            "if (clients.length === 0) return <div>No clients"
            "<Link to='/clients/create'>Create Client</Link></div>;"
        )
        assert self._findings(frontend) == []

    def test_c_no_zero_state_detected_falls_back_to_whole_file(self) -> None:
        """No recognized zero-record condition exists at all -- the
        existing, unchanged whole-file behavior is preserved."""
        frontend = "return <div><Link to='/clients/create'>Create Client</Link></div>;"
        assert self._findings(frontend) == []

    def test_d_loading_branch_then_zero_state_with_create_passes(self) -> None:
        frontend = (
            "if (loading) return <div>Loading</div>; "
            "if (clients.length === 0) return <div>No clients"
            "<Link to='/clients/create'>Create Client</Link></div>;"
        )
        assert self._findings(frontend) == []

    def test_e_create_only_after_the_early_return_is_flagged(self) -> None:
        """The real defect class: a real create control genuinely exists
        in the file, but only in code the zero-record branch's own
        early `return` makes unreachable."""
        frontend = (
            "if (clients.length === 0) return <div>No clients found</div>; "
            "return <div><Link to='/clients/create'>Create Client</Link></div>;"
        )
        codes = {f.code for f in self._findings(frontend)}
        assert "frontend_ui_create_unreachable_from_empty_state" in codes

    def test_f_a_different_modules_control_does_not_satisfy_this_module(self) -> None:
        frontend = (
            "if (clients.length === 0) return <div>No clients found</div>; "
            "return <div><Link to='/sessions/create'>Create Session</Link></div>;"
        )
        codes = {f.code for f in self._findings(frontend, ("clients",))}
        assert "frontend_ui_create_unreachable_from_empty_state" in codes

    def test_g_braced_zero_state_form_is_extracted_correctly(self) -> None:
        frontend = (
            "if (clients.length === 0) { return <div>No clients found</div>; } "
            "return <div><Link to='/clients/create'>Create Client</Link></div>;"
        )
        codes = {f.code for f in self._findings(frontend)}
        assert "frontend_ui_create_unreachable_from_empty_state" in codes

    def test_h_brace_less_zero_state_form_is_extracted_correctly(self) -> None:
        frontend = (
            "if (clients.length === 0) return <div>No clients"
            "<Link to='/clients/create'>Create Client</Link></div>;"
        )
        assert self._findings(frontend) == []

    def test_i_length_less_than_one_is_recognized(self) -> None:
        frontend = "if (clients.length < 1) return <div>No clients found</div>;"
        codes = {f.code for f in self._findings(frontend)}
        assert "frontend_ui_create_unreachable_from_empty_state" in codes

    def test_j_bang_length_is_recognized(self) -> None:
        frontend = "if (!clients.length) return <div>No clients found</div>;"
        codes = {f.code for f in self._findings(frontend)}
        assert "frontend_ui_create_unreachable_from_empty_state" in codes

    def test_k_unrecognized_zero_state_shape_falls_back_safely(self) -> None:
        """A zero-state condition with extra content the narrow regex
        does not recognize must never become a new false positive --
        the existing whole-file behavior is preserved."""
        frontend = (
            "if (clients.length === 0 && !loading) { return <div>Empty</div>; } "
            "return <div><Link to='/clients/create'>Create Client</Link></div>;"
        )
        assert self._findings(frontend) == []

    def test_l_frozen_photography_candidate_flags_both_modules(self) -> None:
        """Real, frozen, unmodified evidence: the real, on-disk
        `factory-goal-mu1hy9w1-qn30iv` candidate's own App.js, read
        verbatim (never copied inline) so this test cannot drift from
        the actual frozen bytes."""
        candidate_app_js = (
            pathlib.Path(__file__).resolve().parents[3]
            / "var" / "factory" / "candidates" / "factory-goal-mu1hy9w1-qn30iv"
            / "frontend" / "src" / "App.js"
        )
        app_js = candidate_app_js.read_text(encoding="utf-8")
        findings = self._findings(app_js, ("clients", "sessions"))
        codes = {f.code for f in findings}
        assert codes == {"frontend_ui_create_unreachable_from_empty_state"}
        assert len(findings) == 2


def test_recoverable_error_state_requires_an_interactive_recovery_control() -> None:
    files = {
        **_valid_spec_files(),
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS.replace(
            '<div>error <button onClick={retry}>Retry</button></div>', '<div>error</div>',
        ),
    }
    findings = _ux_spec_shell_findings(files)
    assert any(f.code == "frontend_ui_error_state_not_actionable" for f in findings)


def _with_products_edit_action(files: dict[str, str]) -> dict[str, str]:
    spec = json.loads(files["product/ux_spec.json"])
    for module in spec["modules"]:
        if module["name"] == "products":
            module["actions"] = ["create", "edit", "view"]
            module["forms"].append({"name": "EditProductForm", "fields": ["name"]})
    return {**files, "product/ux_spec.json": json.dumps(spec)}


def test_declares_edit_but_frontend_never_calls_an_update_function() -> None:
    """golden-work-080 (session evidence, frozen): products declared
    `["create", "edit", "view"]`, `frontend_client` exported a real
    `updateProduct`, and the assembled real frontend only ever called
    `createProduct` -- no edit route, button or form anywhere, confirmed
    in a real browser session (zero console/network errors, the app just
    never offered one). The prior rule ("a create/edit action needs *a*
    <form> somewhere") was satisfied vacuously by the create form alone."""
    files = _with_products_edit_action({
        **_valid_spec_files(),
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS,
    })
    findings = _ux_spec_mutation_findings(files)
    assert any(f.code == "frontend_ui_missing_edit_ui" for f in findings)


_UPDATE_PRODUCT_CLIENT_JS = "export function updateProduct(id, name) { return fetch('/products/' + id); }\n"


def test_is_silent_when_a_real_update_call_exists_for_the_edit_action() -> None:
    files = _with_products_edit_action({
        **_valid_spec_files(),
        "frontend/src/client.js": _UPDATE_PRODUCT_CLIENT_JS,
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS.replace(
            "function ProductForm() {",
            "function ProductForm() { updateProduct(id, name); ",
        ),
    })
    findings = _ux_spec_mutation_findings(files)
    assert not any(f.code == "frontend_ui_missing_edit_ui" for f in findings)


def test_is_silent_when_the_update_export_is_reused_by_reference_not_called_directly() -> None:
    """golden-work-081 (session evidence, frozen): a real model reused one
    form component for both create and edit, passing the real exported
    `updateStudent` BY REFERENCE (`<StudentForm onSubmit={updateStudent}
    />`, invoked generically inside `StudentForm` as `onSubmit(...)`)
    rather than calling it directly by name -- a real, idiomatic React
    pattern this check's prior regex-only version (requiring a literal
    `(` right after the name) rejected as a false positive, exhausting
    frontend_forms's anti-loop budget on a real, working implementation."""
    files = _with_products_edit_action({
        **_valid_spec_files(),
        "frontend/src/client.js": _UPDATE_PRODUCT_CLIENT_JS,
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS.replace(
            "function ProductForm() {",
            "function ProductForm({ onSubmit = updateProduct }) {",
        ),
    })
    findings = _ux_spec_mutation_findings(files)
    assert not any(f.code == "frontend_ui_missing_edit_ui" for f in findings)


def test_flags_the_edit_action_when_no_update_named_export_exists_at_all() -> None:
    files = _with_products_edit_action({
        **_valid_spec_files(),
        "frontend/src/client.js": "export function createProduct(name) { return fetch('/products'); }\n",
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS,
    })
    findings = _ux_spec_mutation_findings(files)
    assert any(f.code == "frontend_ui_missing_edit_ui" for f in findings)


def test_edit_call_check_ignores_the_client_files_own_function_definition() -> None:
    """A `*client*` file's own `function updateProduct(...)` definition
    must never satisfy this check on its own -- only a real call from a
    UI component does, exactly the gap golden-work-080 exposed."""
    files = _with_products_edit_action({
        **_valid_spec_files(),
        "frontend/src/apiClient.js": "export async function updateProduct(id, name) { return fetch('/products/' + id); }\n",
        "frontend/src/App.js": _PROFESSIONAL_SHELL_JS,
    })
    findings = _ux_spec_mutation_findings(files)
    assert any(f.code == "frontend_ui_missing_edit_ui" for f in findings)


def test_g_a_genuinely_single_purpose_product_is_not_forced_into_a_shell() -> None:
    """One read-only module, no dashboard declared -- a minimal frontend
    with no navigation, no dashboard surface and no form must still pass:
    nothing here demands an enterprise shell a simple product has no use
    for."""
    backend = {
        "backend/notes_model.json": json.dumps(
            {"table_name": "notes", "fields": {"id": {"type": "integer"}}}
        ),
        "backend/routes.json": json.dumps([{"path": "/notes", "method": "GET"}]),
    }
    spec = {
        "product_title": "Notes", "primary_roles": ["user"],
        "modules": [{
            "name": "notes", "navigation_label": "Notes", "presentation": "list",
            "actions": ["view"], "forms": [], "search_filter": False,
            "states": {"loading": True, "empty": True, "error": True, "success": False},
        }],
        "navigation_destinations": ["Notes"],
        "design_system": {
            "typography_scale": ["base"], "spacing_scale": ["sm"],
            "component_conventions": ["list"], "responsive": "desktop-first",
            "accessible_focus_contrast": True,
        },
    }
    files = {
        **backend, "product/ux_spec.json": json.dumps(spec),
        "frontend/src/NotesList.js": (
            "<ul>{notes.map(n => <li>{n.title}</li>)}</ul> notes "
            "<button onClick={retry}>Retry</button>"
        ),
    }
    assert _ux_spec_shell_findings(files) == []
    assert _ux_spec_mutation_findings(files) == []
    assert _unreachable_module_findings(files) == []


def test_a_broader_route_declared_first_shadows_a_more_specific_one() -> None:
    """golden-work-068 (real repository evidence, real qwen2.5-coder:14b,
    frozen): frontend_ui wrote `<Route path='/students'>` with no
    `exact`; frontend_forms then added `<Route path='/students/create'>`
    after it in the same <Switch>. A real browser navigated to
    `/students/create` and got the students LIST every time -- the real,
    present CreateStudentForm component never rendered at all."""
    files = {
        "frontend/src/App.js": (
            "<Switch>"
            "<Route path='/students'><h2>Students</h2></Route>"
            "<Route path='/students/create'><h2>Create Student</h2></Route>"
            "</Switch>"
        ),
    }
    findings = _shadowed_route_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_route_shadowed"
    assert "/students" in findings[0].detail
    assert "/students/create" in findings[0].detail


def test_is_silent_when_the_broader_route_is_marked_exact() -> None:
    files = {
        "frontend/src/App.js": (
            "<Switch>"
            "<Route exact path='/students'><h2>Students</h2></Route>"
            "<Route path='/students/create'><h2>Create Student</h2></Route>"
            "</Switch>"
        ),
    }
    assert _shadowed_route_findings(files) == []


def test_is_silent_when_the_specific_route_is_declared_first() -> None:
    files = {
        "frontend/src/App.js": (
            "<Switch>"
            "<Route path='/students/create'><h2>Create Student</h2></Route>"
            "<Route path='/students'><h2>Students</h2></Route>"
            "</Switch>"
        ),
    }
    assert _shadowed_route_findings(files) == []


def test_shadowed_route_findings_runs_unconditionally_without_a_ux_spec() -> None:
    """A general react-router correctness rule, not gated on product_ux_spec
    -- must still fire against a candidate with no spec artifact at all
    (e.g. the one-shot generation path)."""
    files = {
        "frontend/src/App.js": (
            "<Switch>"
            "<Route path='/students'><h2>Students</h2></Route>"
            "<Route path='/students/create'><h2>Create Student</h2></Route>"
            "</Switch>"
        ),
    }
    assert any(f.code == "frontend_ui_route_shadowed" for f in _ux_spec_mutation_findings(files))


def test_flags_a_used_react_router_identifier_never_imported() -> None:
    """golden-work-083 (session evidence, frozen): frontend/src/index.js
    imported only `BrowserRouter as Router` and then used `<Route
    path="/students" component={Students} />` directly -- a real, hard
    `ReferenceError: Route is not defined` at runtime, blanking the
    entire real production build in a real browser. `node --check`
    cannot see this: an undefined identifier is syntactically legal JS,
    only a real ReferenceError at execution."""
    files = {
        "frontend/src/index.js": (
            "import { BrowserRouter as Router } from 'react-router-dom';\n"
            "import Students from './Students';\n"
            "ReactDOM.render(<Router><Route path='/students' component={Students} /></Router>, "
            "document.getElementById('root'));\n"
        ),
    }
    findings = _react_router_missing_import_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_missing_react_router_import"
    assert "Route" in findings[0].detail


def test_is_silent_when_every_used_react_router_identifier_is_imported() -> None:
    files = {
        "frontend/src/App.js": (
            "import { Route, Switch, Link, useHistory } from 'react-router-dom';\n"
            "function App() { const history = useHistory(); return (<Switch>"
            "<Route path='/students'><Link to='/x'>x</Link></Route></Switch>); }\n"
        ),
    }
    assert _react_router_missing_import_findings(files) == []


def test_react_router_import_check_does_not_cross_file_boundaries() -> None:
    """An import in one component never brings a name into scope in a
    different file -- each file is checked against only its own imports."""
    files = {
        "frontend/src/App.js": "import { Route } from 'react-router-dom';\nfunction App() { return null; }\n",
        "frontend/src/Other.js": "function Other() { return <Route path='/x' />; }\n",
    }
    findings = _react_router_missing_import_findings(files)
    assert len(findings) == 1
    assert findings[0].path == "frontend/src/Other.js"


def test_react_router_import_check_runs_unconditionally_without_a_ux_spec() -> None:
    files = {
        "frontend/src/index.js": "ReactDOM.render(<Route path='/x' />, document.getElementById('root'));\n",
    }
    assert any(
        f.code == "frontend_missing_react_router_import" for f in _ux_spec_mutation_findings(files)
    )


def test_repair_merges_a_missing_name_into_an_existing_react_router_import() -> None:
    """golden-work-084 (session evidence, frozen): a real qwen2.5-coder:14b
    reproduced golden-work-083's own exact defect byte-for-byte-similar,
    then exhausted all 4 real frontend_forms attempts on the identical
    class -- frontend/src/index.js always missing Route from its
    existing `{ BrowserRouter as Router }` import -- even once told
    exactly which file and names."""
    files = {
        "frontend/src/index.js": (
            "import { BrowserRouter as Router } from 'react-router-dom';\n"
            "ReactDOM.render(<Router><Route path='/x' /></Router>, "
            "document.getElementById('root'));\n"
        ),
    }
    repaired = _repair_missing_react_router_imports(files)
    assert repaired is not None
    assert "BrowserRouter as Router, Route" in repaired["frontend/src/index.js"]
    assert _react_router_missing_import_findings(repaired) == []


def test_repair_adds_a_new_import_when_none_exists() -> None:
    files = {"frontend/src/App.js": "function App() { return <Route path='/x' />; }\n"}
    repaired = _repair_missing_react_router_imports(files)
    assert repaired is not None
    assert repaired["frontend/src/App.js"].startswith(
        "import { Route } from 'react-router-dom';\n"
    )
    assert _react_router_missing_import_findings(repaired) == []


def test_repair_is_a_noop_when_nothing_is_missing() -> None:
    files = {
        "frontend/src/App.js": (
            "import { Route } from 'react-router-dom';\nfunction App() { return <Route path='/x' />; }\n"
        ),
    }
    assert _repair_missing_react_router_imports(files) is None


def test_flags_a_route_component_whose_definition_destructures_a_custom_prop() -> None:
    """golden-work-085 (session evidence, frozen): Students/index.js
    mounted `<Route path="/students" component={StudentList} exact />`;
    StudentList destructures `{ students }` and calls `students.map(...)`.
    react-router's component= prop only ever injects match/location/
    history/staticContext, never a custom prop, so `students` was always
    `undefined` and a real browser threw `TypeError: Cannot read
    properties of undefined (reading 'map')`, blanking the page on real
    navigation to /students."""
    files = {
        "frontend/src/Students/index.js": (
            "import { Route } from 'react-router-dom';\n"
            "import StudentList from './StudentList';\n"
            "const Students = () => (<Route path='/students' component={StudentList} exact />);\n"
        ),
        "frontend/src/Students/StudentList.js": (
            "const StudentList = ({ students }) => (<ul>{students.map(s => <li>{s.name}</li>)}</ul>);\n"
        ),
    }
    findings = _route_component_missing_props_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_route_component_missing_props"
    assert "StudentList" in findings[0].detail
    assert "students" in findings[0].detail


def test_is_silent_when_the_routed_component_takes_no_custom_props() -> None:
    files = {
        "frontend/src/Students/index.js": (
            "import { Route } from 'react-router-dom';\n"
            "import CreateStudent from './CreateStudent';\n"
            "const Students = () => (<Route path='/students/create' component={CreateStudent} />);\n"
        ),
        "frontend/src/Students/CreateStudent.js": (
            "const CreateStudent = () => (<form><button>Create</button></form>);\n"
        ),
    }
    assert _route_component_missing_props_findings(files) == []


def test_is_silent_when_the_routed_component_only_destructures_route_injected_props() -> None:
    files = {
        "frontend/src/Students/index.js": (
            "import { Route } from 'react-router-dom';\n"
            "import EditStudent from './EditStudent';\n"
            "const Students = () => (<Route path='/students/:id/edit' component={EditStudent} />);\n"
        ),
        "frontend/src/Students/EditStudent.js": (
            "const EditStudent = ({ match }) => (<div>{match.params.id}</div>);\n"
        ),
    }
    assert _route_component_missing_props_findings(files) == []


def test_flags_a_relative_import_with_no_matching_real_file() -> None:
    """golden-work-086 (session evidence, frozen): frontend/src/App.js
    imported Courses from './Courses' and mounted <Route path="/courses"
    component={Courses} />, but no frontend/src/Courses.js (or
    Courses/index.js) was ever generated -- a real `npm run build`
    failed outright: "Module not found: Error: Can't resolve
    './Courses'". Syntactically legal JS; `node --check` cannot see it."""
    files = {
        "frontend/src/App.js": "import Courses from './Courses';\nfunction App() { return <Courses />; }\n",
    }
    findings = _frontend_local_import_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_local_import_unresolved"
    assert "./Courses" in findings[0].detail


def test_is_silent_when_the_relative_import_resolves_to_a_bare_file() -> None:
    files = {
        "frontend/src/App.js": "import Courses from './Courses';\nfunction App() { return <Courses />; }\n",
        "frontend/src/Courses.js": "const Courses = () => <div />;\nexport default Courses;\n",
    }
    assert _frontend_local_import_findings(files) == []


def test_is_silent_when_the_relative_import_resolves_to_a_module_index() -> None:
    files = {
        "frontend/src/App.js": "import Students from './Students';\nfunction App() { return <Students />; }\n",
        "frontend/src/Students/index.js": "const Students = () => <div />;\nexport default Students;\n",
    }
    assert _frontend_local_import_findings(files) == []


def test_is_silent_when_the_relative_import_resolves_to_a_jsx_file() -> None:
    files = {
        "frontend/src/App.js": (
            "import CourseForm from './CourseForm';\nfunction App() { return <CourseForm />; }\n"
        ),
        "frontend/src/CourseForm.jsx": (
            "const CourseForm = () => <form />;\nexport default CourseForm;\n"
        ),
    }
    assert _frontend_local_import_findings(files) == []


def test_local_import_resolution_is_relative_to_the_importing_files_own_directory() -> None:
    """A `../apiClient` import from a nested module file resolves against
    that file's own directory, not the frontend/src root."""
    files = {
        "frontend/src/apiClient.js": "export function getStudents() {}\n",
        "frontend/src/Students/EditStudent.js": (
            "import { getStudents } from '../apiClient';\nfunction EditStudent() { getStudents(); }\n"
        ),
    }
    assert _frontend_local_import_findings(files) == []


def test_flags_a_parameterized_route_never_linked_to_from_anywhere() -> None:
    """golden-work-088 (session evidence, frozen): frontend/src/index.js
    declared `<Route path="/students/edit/:id" component={EditStudent} />`
    -- a real, working form, confirmed correct by navigating directly to
    /students/edit/1 in a real browser -- but App.js's own real student
    list rendered a bare `<li>{student.name}</li>` with no Link, button
    or any other control anywhere in the real frontend ever constructing
    a matching URL. product_ux_spec declared students' actions as
    ["create", "edit", "delete", "view"]; a real end user, using only the
    rendered UI, could never reach a route a direct URL proves works."""
    files = {
        "frontend/src/index.js": (
            "import { Route } from 'react-router-dom';\n"
            "const x = <Route path='/students/edit/:id' component={EditStudent} />;\n"
        ),
        "frontend/src/App.js": "function App() { return <ul><li>{student.name}</li></ul>; }\n",
    }
    findings = _unreachable_parameterized_route_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_route_unreachable"
    assert "/students/edit/" in findings[0].detail


def test_is_silent_when_a_real_link_targets_the_parameterized_route() -> None:
    files = {
        "frontend/src/index.js": (
            "import { Route } from 'react-router-dom';\n"
            "const x = <Route path='/students/edit/:id' component={EditStudent} />;\n"
        ),
        "frontend/src/App.js": (
            "function App() { return <Link to={`/students/edit/${student.id}`}>Edit</Link>; }\n"
        ),
    }
    assert _unreachable_parameterized_route_findings(files) == []


def test_is_silent_for_a_non_parameterized_route() -> None:
    files = {
        "frontend/src/index.js": (
            "import { Route } from 'react-router-dom';\n"
            "const x = <Route path='/students' component={StudentList} exact />;\n"
        ),
    }
    assert _unreachable_parameterized_route_findings(files) == []


def test_root_route_check_runs_unconditionally_without_a_ux_spec() -> None:
    """golden-work-092 (session evidence, frozen): frontend_forms can
    rewrite index.js just as frontend_ui can (the same "wrong stage" shape
    `_react_router_missing_import_findings`/`_frontend_local_import_findings`
    are already wired here for), so this check must fire through
    `_ux_spec_mutation_findings` too, not only `frontend_ui`'s own
    validator -- proven here with no product/ux_spec.json artifact at
    all, the same shape the react-router-import wiring test above uses."""
    files = {
        "frontend/src/index.js": (
            "import { BrowserRouter as Router, Route, Switch } from 'react-router-dom';\n"
            "ReactDOM.render(<Router><Switch>"
            "<Route path='/students' component={App} exact />"
            "</Switch></Router>, document.getElementById('root'));\n"
        ),
    }
    assert any(
        f.code == "frontend_root_path_unreachable" for f in _ux_spec_mutation_findings(files)
    )


def test_exported_js_names_recognizes_a_real_commonjs_module() -> None:
    """golden-work-101 (session evidence, frozen): a real qwen2.5-coder:14b
    wrote a real, complete, correctly-wired apiClient.js using CommonJS
    (`module.exports = { getTasks, createTask, ... };`) -- a real,
    legitimate pattern a real `npm run build` has already proven
    compiles cleanly. Before this fix, neither export regex here
    recognized `module.exports`, so this extractor -- and every check
    built on it (`_unused_client_export_findings`,
    `_update_like_client_exports`) -- silently saw zero exports for any
    real candidate using this shape."""
    client_text = (
        "const getTasks = () => axios.get('/tasks');\n"
        "const createTask = (task) => axios.post('/tasks', task);\n"
        "module.exports = {\n"
        "  getTasks,\n"
        "  createTask\n"
        "};\n"
    )
    assert _exported_js_names(client_text) == frozenset({"getTasks", "createTask"})


def test_exported_js_names_recognizes_a_real_commonjs_alias_module() -> None:
    """F-0101 (real evidence: `factory-goal-mtz6bst2-myhr15`'s own
    `apiClient.js`): `const apiClient = {...}; module.exports = apiClient;`
    -- a real, statically-provable CommonJS re-export idiom distinct from
    `module.exports = { name, ... };` above, since the object literal
    sits on the declaration line, not the `module.exports =` line
    itself. Before this fix `_exported_js_names` saw zero exports for
    this real shape, exactly as it once did for the inline shape above."""
    client_text = (
        "const apiClient = {\n"
        "  getCustomers: async () => { return []; },\n"
        "  updateCustomer: async (id, data) => { return {}; }\n"
        "};\n"
        "module.exports = apiClient;\n"
    )
    names = _exported_js_names(client_text)
    assert {"getCustomers", "updateCustomer"} <= names


class TestAsyncEsmExportRecognition:
    """goal-mtzww02l-48k6h3 (session evidence, frozen): a real
    qwen2.5-coder:14b wrote a real, complete, correctly-wired
    `apiClient.js` declaring every real CRUD function as plain ESM
    `export async function name(...)`, no CommonJS -- `_INLINE_EXPORT_
    PATTERN` (byte-identical to `frontend_client_call_preflight
    ._CLIENT_INLINE_EXPORT`, independently duplicated) only ever allowed
    `const`/`function` directly after `export`, never an intervening
    `async`, so `_update_like_client_exports` came back empty and a
    real, correct edit route calling a real `updateDriver`/`updateOrder`
    was flagged as `frontend_ui_missing_edit_ui` -- the same
    false-positive shape golden-work-101/124 already fixed for two
    different CommonJS export shapes, now extended to this distinct,
    plain-ESM one."""

    def test_a_export_async_function_is_recognized_as_update_like(self) -> None:
        files = {
            "frontend/src/apiClient.js": (
                "export async function updateThing(id, data) { return fetch('/x/' + id); }\n"
            ),
        }
        assert "updateThing" in _update_like_client_exports(files)

    def test_b_valid_async_edit_ui_no_longer_triggers_missing_edit_ui(self) -> None:
        api_client = (
            "export async function getThings() { return []; }\n"
            "export async function updateThing(id, data) { return {}; }\n"
        )
        thing_form = (
            "import { updateThing } from './apiClient';\n"
            "function ThingForm({ id }) { updateThing(id, {}); return null; }\n"
        )
        spec = json.dumps({
            "product_title": "Things", "primary_roles": ["staff"],
            "modules": [{
                "name": "things", "navigation_label": "Things", "presentation": "table",
                "actions": ["create", "edit"],
                "forms": [{"name": "ThingForm", "fields": ["name"]}],
                "search_filter": False,
                "states": {"loading": True, "empty": True, "error": True, "success": True},
            }],
            "navigation_destinations": ["Things"],
            "design_system": {
                "typography_scale": ["base"], "spacing_scale": ["sm"],
                "component_conventions": ["table"], "responsive": "desktop-first",
                "accessible_focus_contrast": True,
            },
            "destructive_action_confirmation": False,
        })
        files = {
            "product/ux_spec.json": spec,
            "frontend/src/apiClient.js": api_client,
            "frontend/src/ThingForm.js": thing_form,
        }
        codes = {f.code for f in _ux_spec_mutation_findings(files)}
        assert "frontend_ui_missing_edit_ui" not in codes

    def test_c_a_plain_non_exported_update_function_does_not_count(self) -> None:
        files = {
            "frontend/src/apiClient.js": (
                "async function updateThing(id, data) { return fetch('/x/' + id); }\n"
            ),
        }
        assert "updateThing" not in _update_like_client_exports(files)

    def test_d_existing_commonjs_alias_support_from_f0101_is_unchanged(self) -> None:
        client_text = (
            "const apiClient = {\n"
            "  getCustomers: async () => { return []; },\n"
            "  updateCustomer: async (id, data) => { return {}; }\n"
            "};\n"
            "module.exports = apiClient;\n"
        )
        names = _exported_js_names(client_text)
        assert {"getCustomers", "updateCustomer"} <= names


class TestFrontendUiUnusedClientStageScope:
    """`FRONTEND_UI_UNUSED_CHECKER_STAGE_SCOPE_DEFECT` (real evidence:
    `factory-goal-mu0pvv20-b2uuo8`). `apiClient.js` genuinely, correctly
    declared `getInventoryItem(id)`; frontend_ui's own real, correct
    list-only rendering (`Inventory.js`/`Orders.js`, calling only the bulk
    `getInventory()`/`getOrders()`) never called it, and never needed to --
    a single-record getter's own real, established consumer is a later
    record-specific detail/edit view (frontend_forms's own concern, per
    #9's `initialData` convention), not this stage's list/collection
    shell. A read export whose own declared signature takes an argument
    is now exempt here exactly like a mutation export already is; a
    genuinely unused zero-argument (list/collection) read export must
    still be flagged, and total non-integration must still be flagged."""

    def test_a_a_used_list_getter_passes(self) -> None:
        client = "export function getThings() {}"
        assert _unused_client_export_findings(client, "getThings();") == []

    def test_b_an_unused_single_record_getter_is_exempt(self) -> None:
        client = "export function getThings() {}\nexport function getThing(id) {}"
        assert _unused_client_export_findings(client, "getThings();") == []

    def test_c_an_unused_list_getter_still_fails(self) -> None:
        client = "export function getThings() {}\nexport function getThing(id) {}"
        findings = _unused_client_export_findings(client, "nothing calls the client here")
        assert len(findings) == 1
        assert "getThings" in findings[0].detail
        assert "getThing'" not in findings[0].detail

    def test_d_a_full_crud_surface_with_only_the_list_getter_used_passes(self) -> None:
        client = (
            "export function getThings() {}\n"
            "export function getThing(id) {}\n"
            "export function createThing(t) {}\n"
            "export function updateThing(id, t) {}\n"
            "export function deleteThing(id) {}\n"
        )
        assert _unused_client_export_findings(client, "getThings();") == []

    def test_e_mutation_exports_remain_exempt_regardless_of_arity(self) -> None:
        client = "export function getThings() {}\nexport function createThing(t) {}"
        assert _unused_client_export_findings(client, "getThings();") == []

    def test_f_multiple_modules_each_still_require_their_own_list_getter(self) -> None:
        """Module A's own usage must never paper over module B's own,
        separate, genuinely unused list getter."""
        client = "export function getWidgets() {}\nexport function getGadgets() {}"
        findings = _unused_client_export_findings(client, "getWidgets();")
        assert len(findings) == 1
        assert "getGadgets" in findings[0].detail

    def test_g_the_single_record_exemption_is_generic_not_name_based(self) -> None:
        """The exemption is driven by the real declared signature (an
        argument), never a domain-specific name like 'Item' or 'ById'."""
        client = "export function fetchWidget(widgetId) {}\nexport function fetchWidgets() {}"
        assert _unused_client_export_findings(client, "fetchWidgets();") == []

    def test_h_total_non_integration_is_still_rejected(self) -> None:
        client = "export function getThings() {}"
        findings = _unused_client_export_findings(client, "return <div>static</div>;")
        assert len(findings) == 1
        assert "getThings" in findings[0].detail

    def test_i_the_former_substring_precision_defect_is_now_fixed(self) -> None:
        """`FRONTEND_UI_UNUSED_CHECKER_SUBSTRING_PRECISION_DEFECT`, real
        evidence-shaped (`factory-goal-mu0pvv20-b2uuo8`'s own `getOrder`/
        `getOrders` naming pair): `name not in ui` used to be plain
        substring containment, silently treating a genuinely-uncalled
        `getWork` as used purely because the real, called `getWorks()`
        contains it as a literal prefix. Usage detection is now a real
        JS-identifier-boundary match, so this genuinely-unused,
        zero-argument, stage-8-required export is correctly flagged."""
        client = "export function getWork() {}\nexport function getWorks() {}"
        findings = _unused_client_export_findings(client, "getWorks();")
        assert len(findings) == 1
        assert "getWork'" in findings[0].detail
        assert "getWorks" not in findings[0].detail


class TestFrontendUiUnusedClientIdentifierPrecision:
    """`FRONTEND_UI_UNUSED_CHECKER_SUBSTRING_PRECISION_DEFECT` (real
    evidence: `factory-goal-mu0pvv20-b2uuo8`'s own `getOrder(id)`/
    `getOrders()` naming pair). `name not in ui` was plain substring
    containment, not real JavaScript identifier matching: a genuinely
    uncalled export whose name happens to be a literal prefix, suffix, or
    otherwise-embedded substring of a different real identifier was
    silently treated as used. Replaced with a real identifier-boundary
    match (not immediately preceded or followed by a letter, digit, `_`,
    or `$`) so only a real standalone reference -- call or bare
    callback/binding -- counts as usage."""

    def test_a_an_exact_direct_call_is_recognized(self) -> None:
        client = "export function getThing() {}"
        assert _unused_client_export_findings(client, "getThing();") == []

    def test_b_an_exact_callback_reference_is_recognized(self) -> None:
        client = "export function getThing() {}"
        assert _unused_client_export_findings(client, "onClick={getThing}") == []
        assert _unused_client_export_findings(client, "const loader = getThing;") == []

    def test_c_a_prefix_collision_is_rejected(self) -> None:
        """`getThing` must not be considered used merely because the
        real, called `getThings()` contains it as a literal prefix."""
        client = "export function getThing() {}\nexport function getThings() {}"
        findings = _unused_client_export_findings(client, "getThings();")
        assert len(findings) == 1 and "getThing'" in findings[0].detail

    def test_d_a_suffix_collision_is_rejected(self) -> None:
        client = "export function getThing() {}"
        findings = _unused_client_export_findings(client, "getThingExtra();")
        assert len(findings) == 1 and "getThing" in findings[0].detail

    def test_e_an_underscore_collision_is_rejected(self) -> None:
        client = "export function getThing() {}"
        findings = _unused_client_export_findings(client, "helper_getThing();")
        assert len(findings) == 1 and "getThing" in findings[0].detail

    def test_f_a_dollar_sign_collision_is_rejected(self) -> None:
        client = "export function getThing() {}"
        assert len(_unused_client_export_findings(client, "$mygetThing")) == 1
        assert len(_unused_client_export_findings(client, "getThing$alias")) == 1

    def test_g_a_zero_argument_required_export_collision_is_reported(self) -> None:
        """A generic list/read pair the stage-scope fix never exempts
        (both zero-argument) -- proves this fix independently of the
        single-record exemption."""
        client = "export function getItem() {}\nexport function getItems() {}"
        findings = _unused_client_export_findings(client, "getItems();")
        assert len(findings) == 1
        assert findings[0].detail == "frontend_ui never calls client export(s) ['getItem']"

    def test_h_real_getorder_getorders_matcher_precision(self) -> None:
        """Exercises the matcher directly, not only final finding output
        -- the exact real naming pair from `factory-goal-mu0pvv20-b2uuo8`."""
        boundary = re.compile(rf"(?<![\w$]){re.escape('getOrder')}(?![\w$])")
        assert boundary.search("getOrders();") is None
        assert boundary.search("getOrder(id);") is not None

    def test_i_frozen_warehouse_replay_still_absent(self) -> None:
        """Composition proof: the stage-scope exemption and the identifier-
        precision fix must both hold simultaneously on the same real,
        frozen bytes this session's own two fixes were each evidenced by."""
        client = (
            "export async function getInventory() { return fetchWithCheck(); }\n"
            "export async function getInventoryItem(id) { return fetchWithCheck(); }\n"
            "export async function getOrders() { return fetchWithCheck(); }\n"
            "export async function getOrder(id) { return fetchWithCheck(); }\n"
        )
        ui = "getInventory(); getOrders();"
        assert _unused_client_export_findings(client, ui) == []


class TestFrontendUiSingleRecordGetterArityShapes:
    """`FRONTEND_UI_UNUSED_CHECKER_STAGE_SCOPE_DEFECT` recurrence (real
    evidence: `factory-goal-mu183yam-d09hsx`). The single-record arity
    check only ever recognized a name directly followed by `(` -- a
    real `const apiClient = { getBook: async (id) => {...}, ... };
    module.exports = apiClient;` (the same real, valid CommonJS
    object-property shape F-0101's own `_commonjs_alias_export_names`
    already recognizes for NAME discovery) puts `: async ` between the
    property name and its own real parameter list, so `getBook`/
    `getBorrower` -- real, genuine single-record getters -- were left
    in the required set. The arity regex now optionally skips a
    leading `:`/`=` and one bare keyword before requiring the real,
    non-empty parameter list. Classification is by syntax/arity only,
    never by singular/plural naming."""

    @staticmethod
    def _findings(client: str, ui: str) -> list:
        return _unused_client_export_findings(client, ui)

    def test_a_commonjs_zero_arg_async_arrow_is_required(self) -> None:
        client = "const c = { getThings: async () => {} }; module.exports = c;"
        assert self._findings(client, "") != []

    def test_b_commonjs_async_arrow_with_arg_is_deferred(self) -> None:
        client = (
            "const c = { getThings: async () => {}, getThing: async (id) => {} };"
            "module.exports = c;"
        )
        assert self._findings(client, "getThings();") == []

    def test_c_commonjs_zero_arg_plain_arrow_is_required(self) -> None:
        client = "const c = { getThings: () => {} }; module.exports = c;"
        assert self._findings(client, "") != []

    def test_d_commonjs_plain_arrow_with_arg_is_deferred(self) -> None:
        client = (
            "const c = { getThings: () => {}, getThing: (id) => {} };"
            "module.exports = c;"
        )
        assert self._findings(client, "getThings();") == []

    def test_e_direct_async_function_with_arg_is_deferred(self) -> None:
        client = "export async function getThing(id) { return id; }"
        assert self._findings(client, "") == []

    def test_f_direct_async_function_zero_arg_is_required(self) -> None:
        client = "export async function getThing() { return 1; }"
        assert self._findings(client, "") != []

    def test_g_const_async_arrow_with_arg_is_deferred(self) -> None:
        client = "export const getThing = async (id) => { return id; };"
        assert self._findings(client, "") == []

    def test_h_const_async_arrow_zero_arg_is_required(self) -> None:
        client = "export const getThing = async () => { return 1; };"
        assert self._findings(client, "") != []

    def test_i_multi_parameter_commonjs_arrow_is_deferred(self) -> None:
        client = (
            "const c = { getThings: async () => {}, "
            "getThing: async (id, options) => {} }; module.exports = c;"
        )
        assert self._findings(client, "getThings();") == []

    def test_j_whitespace_variations_are_tolerated(self) -> None:
        tight = "const c = { getThing:async(id)=>{} }; module.exports = c;"
        loose = "const c = { getThing : async ( id ) => {} }; module.exports = c;"
        for client in (tight, loose):
            assert self._findings(client, "") == []

    def test_k_frozen_library_getbook_getborrower_are_deferred(self) -> None:
        """Section 8: real, frozen `apiClient.js` (unmodified) -- `getBook`/
        `getBorrower` must now be classified as single-record getters."""
        api_client = """const apiClient = {
  getBooks: async () => { return []; },
  createBook: async (bookData) => { return {}; },
  getBook: async (id) => { return {}; },
  updateBook: async (id, bookData) => { return {}; },
  deleteBook: async (id) => { return {}; },
  getBorrowers: async () => { return []; },
  createBorrower: async (borrowerData) => { return {}; },
  getBorrower: async (id) => { return {}; },
  updateBorrower: async (id, borrowerData) => { return {}; },
  deleteBorrower: async (id) => { return {}; }
};
module.exports = apiClient;
"""
        ui = "getBooks(); getBorrowers();"
        assert self._findings(api_client, ui) == []

    def test_l_frozen_library_collection_getters_remain_required(self) -> None:
        api_client = """const apiClient = {
  getBooks: async () => { return []; },
  getBook: async (id) => { return {}; },
  getBorrowers: async () => { return []; },
  getBorrower: async (id) => { return {}; }
};
module.exports = apiClient;
"""
        findings = self._findings(api_client, "getBooks();")
        assert len(findings) == 1
        assert "getBorrowers" in findings[0].detail
        assert "getBorrower'" not in findings[0].detail


class TestFormControlAccessibleName:
    """F-0101B (`FRONTEND_UI_EDIT_EXPORT_MISDETECTION_AND_LABEL_HINT_GAP`,
    real evidence: `factory-goal-mtz6bst2-myhr15`). The checker's own
    real semantics, unchanged by this finding's fix -- proven both ways:
    every real, legal accessible-name mechanism still passes, and the
    real historical bare-sibling shape still fails."""

    @staticmethod
    def _unlabelled(frontend: str) -> bool:
        return any(
            f.code == "frontend_ui_form_control_unlabelled"
            for f in _form_quality_findings(frontend)
        )

    def test_a_htmlfor_id_pairing_passes(self) -> None:
        frontend = (
            "<form><label htmlFor='name'>Name</label>"
            "<input id='name' /></form>"
        )
        assert not self._unlabelled(frontend)

    def test_b_wrapping_label_passes(self) -> None:
        frontend = "<form><label>Name<input /></label></form>"
        assert not self._unlabelled(frontend)

    def test_c_aria_label_passes(self) -> None:
        frontend = "<form><input aria-label='Name' /></form>"
        assert not self._unlabelled(frontend)

    def test_d_aria_labelledby_passes(self) -> None:
        frontend = (
            "<form><span id='name-label'>Name</span>"
            "<input aria-labelledby='name-label' /></form>"
        )
        assert not self._unlabelled(frontend)

    def test_e_bare_sibling_label_and_input_fails(self) -> None:
        """The exact real historical shape: a visible `<label>` exists,
        immediately next to its `<input>`, associated with nothing."""
        frontend = "<form><label>Name</label><input /></form>"
        assert any(
            f.code == "frontend_ui_form_control_unlabelled"
            for f in _form_quality_findings(frontend)
        )


def test_f0101_historical_replay_edit_false_positive_gone_label_defect_remains() -> None:
    """F-0101's own real historical evidence (`factory-goal-mtz6bst2-
    myhr15`, no model call): merging the real persisted 8-stage workspace
    with the real terminal `frontend_forms` attempt's own frozen raw
    output (`sha256:70a83649...`) reproduces the exact real STAGE_FAILED
    finding pair. After this fix, `frontend_ui_missing_edit_ui` must be
    gone (the real update/edit exports are now recognized) while
    `frontend_ui_form_control_unlabelled` must still fire -- the checker
    fix and the generation-guidance fix are separate concerns; the real
    historical malformed accessibility output is never made to pass."""
    customer_form = (
        "import React, { useState, useEffect } from 'react';\n"
        "const CustomerForm = ({ onSubmit, id }) => {\n"
        "  const [formData, setFormData] = useState({ name: '', email: '', phone: '' });\n"
        "  return (\n"
        "    <form onSubmit={() => onSubmit(id, formData)}>\n"
        "      <div><label>Name:</label>"
        "<input type='text' name='name' value={formData.name} required /></div>\n"
        "      <div><label>Email:</label>"
        "<input type='email' name='email' value={formData.email} required /></div>\n"
        "      <button type='submit'>Save</button>\n"
        "    </form>\n"
        "  );\n"
        "};\n"
        "export default CustomerForm;\n"
    )
    app_js = (
        "import React from 'react';\n"
        "import { Route, Switch, useParams } from 'react-router-dom';\n"
        "import CustomerForm from './components/CustomerForm';\n"
        "import apiClient from './apiClient';\n"
        "const App = () => (\n"
        "  <Switch>\n"
        "    <Route path='/customers/edit/:id' component={() => {\n"
        "      const { id } = useParams();\n"
        "      return <CustomerForm onSubmit={apiClient.updateCustomer} id={id} />;\n"
        "    }} />\n"
        "  </Switch>\n"
        ");\n"
        "export default App;\n"
    )
    api_client = (
        "const apiClient = {\n"
        "  getCustomers: async () => { return []; },\n"
        "  updateCustomer: async (id, data) => { return {}; }\n"
        "};\n"
        "module.exports = apiClient;\n"
    )
    spec = json.dumps({
        "product_title": "Customer Support", "primary_roles": ["staff"],
        "modules": [{
            "name": "customers", "navigation_label": "Customers", "presentation": "table",
            "actions": ["create", "edit"],
            "forms": [{"name": "CustomerForm", "fields": ["name", "email"]}],
            "search_filter": False,
            "states": {"loading": True, "empty": True, "error": True, "success": True},
        }],
        "navigation_destinations": ["Customers"],
        "design_system": {
            "typography_scale": ["base"], "spacing_scale": ["sm"],
            "component_conventions": ["table"], "responsive": "desktop-first",
            "accessible_focus_contrast": True,
        },
        "destructive_action_confirmation": False,
    })
    files = {
        "product/ux_spec.json": spec,
        "frontend/src/App.js": app_js,
        "frontend/src/apiClient.js": api_client,
        "frontend/src/components/CustomerForm.js": customer_form,
    }
    findings = _ux_spec_mutation_findings(files)
    codes = {f.code for f in findings}
    assert "frontend_ui_missing_edit_ui" not in codes
    assert "frontend_ui_form_control_unlabelled" in codes
