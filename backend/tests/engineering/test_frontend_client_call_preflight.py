from __future__ import annotations

from arkali.engineering.factory.frontend_client_call_preflight import (
    _client_call_missing_import_findings,
    _repair_missing_client_call_imports,
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


_API_CLIENT = (
    "async function getStudent(id) { return fetch('/students/' + id); }\n"
    "async function createStudent(name) { return fetch('/students', {method: 'POST'}); }\n"
    "async function updateStudent(id, name) { return fetch('/students/' + id, {method: 'PUT'}); }\n"
    "export { getStudent, createStudent, updateStudent };\n"
)


def test_repair_merges_a_missing_call_into_an_existing_client_import() -> None:
    """golden-work-091 (session evidence, frozen): StudentForm.js called
    getStudent(id) inside a real useEffect, but its own import line
    (`import { createStudent, updateStudent } from './apiClient';`)
    never named it, and a real qwen2.5-coder:14b exhausted all 4 real
    frontend_forms attempts on this exact class even with accurate
    per-attempt feedback."""
    stage_files = {
        "frontend/src/StudentForm.js": (
            "import { createStudent, updateStudent } from './apiClient';\n"
            "function StudentForm({ id }) { getStudent(id); }\n"
        ),
    }
    merged = {"frontend/src/apiClient.js": _API_CLIENT, **stage_files}
    repaired = _repair_missing_client_call_imports(merged, stage_files)
    assert repaired is not None
    assert "createStudent, updateStudent, getStudent" in repaired["frontend/src/StudentForm.js"]
    assert _client_call_missing_import_findings({**merged, **repaired}) == []


def test_repair_is_a_noop_when_no_client_like_import_exists_to_merge_into() -> None:
    """Inventing a relative import path here could easily be wrong --
    different files sit at different directory depths -- so a file that
    calls a client export with no existing client-like import at all is
    left for the model, not guessed."""
    stage_files = {
        "frontend/src/StudentForm.js": "function StudentForm({ id }) { getStudent(id); }\n",
    }
    merged = {"frontend/src/apiClient.js": _API_CLIENT, **stage_files}
    assert _repair_missing_client_call_imports(merged, stage_files) is None


def test_repair_is_a_noop_when_the_stage_did_not_write_the_calling_file() -> None:
    merged = {
        "frontend/src/apiClient.js": _API_CLIENT,
        "frontend/src/StudentForm.js": (
            "import { createStudent } from './apiClient';\nfunction StudentForm() { getStudent(1); }\n"
        ),
    }
    assert _repair_missing_client_call_imports(merged, {}) is None
