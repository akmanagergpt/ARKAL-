from __future__ import annotations

from arkali.engineering.factory.frontend_client_call_preflight import (
    _client_call_missing_import_findings,
    _phantom_client_import_findings,
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


def test_flags_an_imported_name_the_client_module_never_exports() -> None:
    """golden-work-097 (session evidence, frozen): TaskDelete.js wrote
    `import { deleteTask } from './apiClient'` and called
    `deleteTask(id)` inside a real onClick handler -- apiClient.js's own
    grouped export statement (`export { getTasks, createTask, getTask,
    updateTask };`) never named `deleteTask` at all. A real `npm run
    build` compiled successfully (a named ES-module import of a name the
    target module never exports is not a build-time error); only a real
    click in a real browser would throw `TypeError: deleteTask is not a
    function`."""
    files = {
        "frontend/src/apiClient.js": (
            "async function getTasks() { return fetch('/tasks'); }\n"
            "async function createTask(t) { return fetch('/tasks', {method: 'POST'}); }\n"
            "async function getTask(id) { return fetch('/tasks/' + id); }\n"
            "async function updateTask(id, t) { return fetch('/tasks/' + id, {method: 'PUT'}); }\n"
            "export { getTasks, createTask, getTask, updateTask };\n"
        ),
        "frontend/src/TaskDelete.js": (
            "import { deleteTask } from './apiClient';\n"
            "function TaskDelete({ id }) { return "
            "<button onClick={() => deleteTask(id)}>Delete</button>; }\n"
        ),
    }
    findings = _phantom_client_import_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_phantom_client_import"
    assert findings[0].path == "frontend/src/TaskDelete.js"
    assert "deleteTask" in findings[0].detail


def test_is_silent_when_every_imported_name_is_a_real_export() -> None:
    files = {
        "frontend/src/apiClient.js": _API_CLIENT,
        "frontend/src/StudentForm.js": (
            "import { getStudent, createStudent } from './apiClient';\n"
            "function StudentForm() { getStudent(1); createStudent('x'); }\n"
        ),
    }
    assert _phantom_client_import_findings(files) == []


def test_phantom_import_check_is_silent_when_no_client_file_exists_yet() -> None:
    files = {
        "frontend/src/TaskDelete.js": "import { deleteTask } from './apiClient';\ndeleteTask(1);\n",
    }
    assert _phantom_client_import_findings(files) == []


#: golden-work-101 (session evidence, frozen), verbatim real apiClient.js.
_COMMONJS_API_CLIENT = """const axios = require('axios');

const API_BASE_URL = 'http://localhost:5000';

const getTasks = () => axios.get(`${API_BASE_URL}/tasks`);
const createTask = (task) => axios.post(`${API_BASE_URL}/tasks`, task);
const getTask = (id) => axios.get(`${API_BASE_URL}/tasks/${id}`);
const updateTask = (id, task) => axios.put(`${API_BASE_URL}/tasks/${id}`, task);

module.exports = {
  getTasks,
  createTask,
  getTask,
  updateTask
};
"""


def test_is_silent_for_a_real_commonjs_client_module() -> None:
    """golden-work-101 (session evidence, frozen): a real qwen2.5-coder:14b
    wrote a real, complete, correctly-wired apiClient.js using CommonJS
    (`module.exports = { getTasks, createTask, ... };`) -- a real,
    legitimate pattern a real `npm run build` has already proven
    compiles cleanly with ES-module imports on the consuming side.
    Before this fix, neither export regex recognized `module.exports`,
    so `exported` came back completely empty and EVERY real file's
    every real import was flagged as phantom -- a false-positive hard
    block on an otherwise entirely valid candidate that exhausted all 4
    real frontend_forms attempts."""
    files = {
        "frontend/src/apiClient.js": _COMMONJS_API_CLIENT,
        "frontend/src/TaskList.js": "import { getTasks } from './apiClient';\ngetTasks();\n",
        "frontend/src/TaskCreate.js": "import { createTask } from './apiClient';\ncreateTask({});\n",
        "frontend/src/TaskEdit.js": (
            "import { getTask, updateTask } from './apiClient';\ngetTask(1); updateTask(1, {});\n"
        ),
    }
    assert _phantom_client_import_findings(files) == []


def test_flags_a_genuinely_phantom_import_against_a_commonjs_client() -> None:
    """The CommonJS fix must not become blind in the other direction --
    a real phantom import against a real CommonJS client is still
    caught."""
    files = {
        "frontend/src/apiClient.js": _COMMONJS_API_CLIENT,
        "frontend/src/TaskDelete.js": "import { deleteTask } from './apiClient';\ndeleteTask(1);\n",
    }
    findings = _phantom_client_import_findings(files)
    assert len(findings) == 1
    assert "deleteTask" in findings[0].detail


def test_phantom_import_check_does_not_flag_the_client_file_itself() -> None:
    """A client file importing from another client-like file is not this
    defect's concern -- only real UI-side phantom imports are checked."""
    files = {
        "frontend/src/apiClient.js": _API_CLIENT,
        "frontend/src/otherClient.js": (
            "import { deleteTask } from './apiClient';\nexport { deleteTask };\n"
        ),
    }
    assert _phantom_client_import_findings(files) == []
