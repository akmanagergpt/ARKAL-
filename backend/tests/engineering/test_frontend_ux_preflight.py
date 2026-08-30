from __future__ import annotations

import json

from arkali.engineering.factory.frontend_manifest_preflight import (
    _frontend_local_import_findings,
    _react_router_missing_import_findings,
    _repair_missing_react_router_imports,
    _route_component_missing_props_findings,
)
from arkali.engineering.factory.frontend_ux_preflight import (
    _exported_js_names,
    _shadowed_route_findings,
    _unreachable_parameterized_route_findings,
    _ux_spec_mutation_findings,
    _ux_spec_shell_findings,
    _unreachable_module_findings,
)
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
      <Link to="/categories">Categories</Link>
      <Link to="/orders">Orders</Link>
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
  if (error) return <div>error</div>;
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
        "frontend/src/NotesList.js": "<ul>{notes.map(n => <li>{n.title}</li>)}</ul> notes",
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
