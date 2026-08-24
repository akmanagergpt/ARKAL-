from __future__ import annotations

import json

from arkali.engineering.factory.frontend_invented_mutation_preflight import (
    _invented_mutation_ui_findings,
    _repair_invented_mutation_ui,
)

_DESIGN_SYSTEM = {
    "typography_scale": ["h1", "body"], "spacing_scale": ["sm"],
    "component_conventions": ["button"], "responsive": True,
    "accessible_focus_contrast": True,
}


def _task_ux_spec(actions: list[str]) -> str:
    return json.dumps({
        "product_title": "Task Management System", "primary_roles": ["Task Manager"],
        "modules": [{
            "name": "task_model", "navigation_label": "Tasks", "presentation": "table",
            "actions": actions,
            "forms": [{"name": "create_task", "fields": ["title"]}] if actions else [],
            "states": {"loading": True, "empty": True, "error": True, "success": True},
        }],
        "navigation_destinations": ["Tasks"],
        "design_system": _DESIGN_SYSTEM,
    })


def test_flags_a_real_delete_call_with_no_declared_delete_action() -> None:
    """golden-work-099 (session evidence, frozen): golden-work-098's own
    real backend never implemented a DELETE route for /tasks;
    product_ux_spec's own over-declared-action check correctly forced
    this candidate's spec to declare only ["create", "edit", "view"] --
    no "delete" anywhere. frontend_forms still wrote a real TaskDelete.js
    calling a real deleteTask(id) on a real onClick handler anyway,
    reproducing this exact mistake unchanged across all 4 real attempts
    and exhausting the stage's full attempt budget."""
    files = {
        "product/ux_spec.json": _task_ux_spec(["create", "edit", "view"]),
        "frontend/src/TaskDelete.js": (
            "import { deleteTask } from './apiClient';\n"
            "function TaskDelete({ id }) { return "
            "<button onClick={() => deleteTask(id)}>Delete</button>; }\n"
        ),
    }
    findings = _invented_mutation_ui_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_invented_mutation_ui"
    assert findings[0].path == "frontend/src/TaskDelete.js"
    assert "deleteTask" in findings[0].detail
    assert "'delete'" in findings[0].detail


def test_is_silent_when_the_action_is_genuinely_declared() -> None:
    files = {
        "product/ux_spec.json": _task_ux_spec(["create", "edit", "delete", "view"]),
        "frontend/src/TaskDelete.js": (
            "import { deleteTask } from './apiClient';\n"
            "function TaskDelete({ id }) { return "
            "<button onClick={() => deleteTask(id)}>Delete</button>; }\n"
        ),
    }
    assert _invented_mutation_ui_findings(files) == []


def test_is_silent_when_no_ux_spec_exists() -> None:
    """The one-shot generation path has no product_ux_spec stage at all --
    never penalized here, the same guard every other spec-dependent check
    in this bounded context already uses."""
    files = {
        "frontend/src/TaskDelete.js": "import { deleteTask } from './apiClient';\ndeleteTask(1);\n",
    }
    assert _invented_mutation_ui_findings(files) == []


def test_does_not_flag_a_call_inside_a_wrapper_named_handle_delete() -> None:
    """`\bdelete` requires a word boundary immediately before the verb --
    `handleDelete` is a real, common wrapper name that must never match."""
    files = {
        "product/ux_spec.json": _task_ux_spec(["view"]),
        "frontend/src/TaskDelete.js": (
            "function handleDelete() { console.log('confirm only, no client call'); }\n"
        ),
    }
    assert _invented_mutation_ui_findings(files) == []


def test_does_not_flag_the_client_files_own_function_definition() -> None:
    files = {
        "product/ux_spec.json": _task_ux_spec(["view"]),
        "frontend/src/apiClient.js": (
            "async function deleteTask(id) { return fetch('/tasks/' + id, {method: 'DELETE'}); }\n"
            "export { deleteTask };\n"
        ),
    }
    assert _invented_mutation_ui_findings(files) == []


def test_flags_a_create_call_with_no_declared_create_action() -> None:
    """Generalizes across every real mutation verb this pipeline's own
    naming convention uses (create/update/edit/delete), not only delete."""
    files = {
        "product/ux_spec.json": _task_ux_spec(["view"]),
        "frontend/src/TaskCreate.js": (
            "import { createTask } from './apiClient';\ncreateTask({title: 'x'});\n"
        ),
    }
    findings = _invented_mutation_ui_findings(files)
    assert len(findings) == 1
    assert "'create'" in findings[0].detail


def test_flags_an_update_call_as_the_edit_action() -> None:
    files = {
        "product/ux_spec.json": _task_ux_spec(["view"]),
        "frontend/src/TaskEdit.js": (
            "import { updateTask } from './apiClient';\nupdateTask(1, {title: 'x'});\n"
        ),
    }
    findings = _invented_mutation_ui_findings(files)
    assert len(findings) == 1
    assert "'edit'" in findings[0].detail


#: golden-work-099 through golden-work-106 (session evidence, frozen): a
#: real qwen2.5-coder:14b reproduced this exact invented-delete-control
#: mistake across eight separate real candidates, exhausting
#: frontend_forms's full attempt budget every time.
_REAL_APP_JS = """import React from "react";
import { BrowserRouter as Router, Route, Switch } from "react-router-dom";
import TaskList from "./TaskList";
import TaskCreate from "./TaskCreate";
import TaskEdit from "./TaskEdit";
import TaskDelete from "./TaskDelete";

const App = () => (
  <Router>
    <Switch>
      <Route exact path="/tasks" component={TaskList} />
      <Route path="/tasks/create" component={TaskCreate} />
      <Route path="/tasks/edit/:id" component={TaskEdit} />
      <Route path="/tasks/delete/:id" component={TaskDelete} />
    </Switch>
  </Router>
);
export default App;
"""
_REAL_TASK_DELETE_JS = """import { deleteTask } from './apiClient';
function TaskDelete({ id }) { return <button onClick={() => deleteTask(id)}>Delete</button>; }
export default TaskDelete;
"""


def test_repair_removes_the_invented_file_and_its_app_js_reference() -> None:
    stage_files = {
        "frontend/src/App.js": _REAL_APP_JS,
        "frontend/src/TaskCreate.js": "x",
        "frontend/src/TaskEdit.js": "y",
        "frontend/src/TaskDelete.js": _REAL_TASK_DELETE_JS,
    }
    merged = {"product/ux_spec.json": _task_ux_spec(["create", "edit", "view"]), **stage_files}
    repaired = _repair_invented_mutation_ui(merged, stage_files)
    assert repaired is not None
    assert "frontend/src/TaskDelete.js" not in repaired
    assert "TaskDelete" not in repaired["frontend/src/App.js"]
    assert "TaskCreate" in repaired["frontend/src/App.js"]
    assert "TaskEdit" in repaired["frontend/src/App.js"]
    final = {"product/ux_spec.json": _task_ux_spec(["create", "edit", "view"]), **repaired}
    assert _invented_mutation_ui_findings(final) == []


def test_repair_is_a_noop_when_the_action_is_genuinely_declared() -> None:
    stage_files = {
        "frontend/src/App.js": _REAL_APP_JS,
        "frontend/src/TaskDelete.js": _REAL_TASK_DELETE_JS,
    }
    merged = {
        "product/ux_spec.json": _task_ux_spec(["create", "edit", "delete", "view"]), **stage_files,
    }
    assert _repair_invented_mutation_ui(merged, stage_files) is None


def test_repair_is_a_noop_when_no_ux_spec_exists() -> None:
    stage_files = {"frontend/src/TaskDelete.js": _REAL_TASK_DELETE_JS}
    assert _repair_invented_mutation_ui(stage_files, stage_files) is None


def test_repair_is_a_noop_when_the_offending_file_is_not_this_stages_own_output() -> None:
    """`frontend_ui` never writes a mutation component -- if the offending
    path is only visible through an earlier stage's own output, this
    stage cannot remove a file it did not write."""
    merged = {
        "product/ux_spec.json": _task_ux_spec(["view"]),
        "frontend/src/TaskDelete.js": _REAL_TASK_DELETE_JS,
    }
    assert _repair_invented_mutation_ui(merged, {}) is None
