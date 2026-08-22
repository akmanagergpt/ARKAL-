from __future__ import annotations

import json

from arkali.engineering.factory.frontend_ux_preflight import _unreachable_module_findings

_STUDENT_MODEL = json.dumps({"table_name": "students", "fields": {"id": {"type": "integer"}}})
_COURSE_MODEL = json.dumps({"table_name": "courses", "fields": {"id": {"type": "integer"}}})
_PAYMENT_MODEL = json.dumps({"table_name": "payments", "fields": {"id": {"type": "integer"}}})


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
