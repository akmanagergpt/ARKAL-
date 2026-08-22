from __future__ import annotations

import json

from arkali.engineering.factory.frontend_ux_preflight import (
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
