from __future__ import annotations

from arkali.engineering.factory.frontend_client_call_preflight import (
    _client_call_missing_import_findings,
)


def test_flags_a_client_export_called_but_never_imported() -> None:
    """golden-work-090 (session evidence, frozen): App.js's real student
    list gained a real, correct edit Link and a real inline delete
    button calling `deleteStudent(student.id)` directly on click -- but
    App.js's own import line was never updated to include
    `deleteStudent`, a real export apiClient.js genuinely declares. A
    real, hard `ReferenceError: deleteStudent is not defined` the moment
    a real user clicks Delete -- syntactically legal JS, `node --check`
    cannot see a bare identifier reference."""
    files = {
        "frontend/src/apiClient.js": (
            "async function getStudents() { return fetch('/students'); }\n"
            "async function deleteStudent(id) { return fetch('/students/' + id, {method: 'DELETE'}); }\n"
            "export { getStudents, deleteStudent };\n"
        ),
        "frontend/src/App.js": (
            "import { getStudents } from './apiClient';\n"
            "function App() { getStudents(); "
            "return <button onClick={() => deleteStudent(1)}>Delete</button>; }\n"
        ),
    }
    findings = _client_call_missing_import_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_client_call_missing_import"
    assert "deleteStudent" in findings[0].detail


def test_is_silent_when_the_call_is_properly_imported() -> None:
    files = {
        "frontend/src/apiClient.js": (
            "async function deleteStudent(id) { return fetch('/students/' + id, {method: 'DELETE'}); }\n"
            "export { deleteStudent };\n"
        ),
        "frontend/src/App.js": (
            "import { deleteStudent } from './apiClient';\n"
            "function App() { return <button onClick={() => deleteStudent(1)}>Delete</button>; }\n"
        ),
    }
    assert _client_call_missing_import_findings(files) == []


def test_is_silent_when_a_locally_declared_name_shadows_the_export() -> None:
    files = {
        "frontend/src/apiClient.js": (
            "async function deleteStudent(id) { return fetch('/students/' + id); }\nexport { deleteStudent };\n"
        ),
        "frontend/src/Other.js": (
            "function deleteStudent() { console.log('local'); }\ndeleteStudent();\n"
        ),
    }
    assert _client_call_missing_import_findings(files) == []


def test_does_not_flag_the_client_file_itself() -> None:
    files = {
        "frontend/src/apiClient.js": (
            "async function deleteStudent(id) { return fetch('/students/' + id); }\n"
            "async function callDeleteStudent() { deleteStudent(1); }\n"
            "export { deleteStudent, callDeleteStudent };\n"
        ),
    }
    assert _client_call_missing_import_findings(files) == []


def test_is_silent_when_no_client_file_exists_yet() -> None:
    files = {"frontend/src/App.js": "function App() { deleteStudent(1); return null; }\n"}
    assert _client_call_missing_import_findings(files) == []
