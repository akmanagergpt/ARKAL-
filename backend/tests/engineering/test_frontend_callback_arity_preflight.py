from __future__ import annotations

from arkali.engineering.factory.frontend_callback_arity_preflight import (
    _callback_prop_arity_mismatch_findings,
)

#: golden-work-113/119 (real repository evidence, real qwen2.5-coder:14b,
#: frozen, independently reproduced twice): the real shape that reached a
#: real browser acceptance failure. The create usage (2 declared, 2 called)
#: is correct and must not be flagged; only the edit usage (3 declared, 2
#: called) is the real defect.
_STUDENT_FORM_JS = (
    "const StudentForm = ({ onSubmit }) => {"
    "  const handleSubmit = async (e) => {"
    "    e.preventDefault();"
    "    await onSubmit(name, email);"
    "  };"
    "  return <form onSubmit={handleSubmit}></form>;"
    "};"
)
_APP_JS_BOTH_ROUTES = (
    "<Route path='/students/create'>"
    "<StudentForm onSubmit={async (name, email) => { await createStudent(name, email); }} />"
    "</Route>"
    "<Route path='/students/edit/:id'>"
    "<StudentForm onSubmit={async (id, name, email) => { await updateStudent(id, name, email); }} />"
    "</Route>"
)


def test_catches_golden_work_113s_and_119s_own_real_defect() -> None:
    findings = _callback_prop_arity_mismatch_findings({
        "frontend/src/App.js": _APP_JS_BOTH_ROUTES,
        "frontend/src/StudentForm.js": _STUDENT_FORM_JS,
    })
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_callback_prop_arity_mismatch"
    assert "'id'" in findings[0].detail


def test_the_correct_create_usage_alone_is_not_flagged() -> None:
    app_js = (
        "<Route path='/students/create'>"
        "<StudentForm onSubmit={async (name, email) => { await createStudent(name, email); }} />"
        "</Route>"
    )
    findings = _callback_prop_arity_mismatch_findings({
        "frontend/src/App.js": app_js,
        "frontend/src/StudentForm.js": _STUDENT_FORM_JS,
    })
    assert findings == []


def test_a_matching_arity_everywhere_is_not_flagged() -> None:
    """StudentDelete.js's own real, correctly-fixed shape: onDelete(id)."""
    files = {
        "frontend/src/App.js": (
            "<Route path='/students/delete/:id'>"
            "<StudentDelete onDelete={async (id) => { await deleteStudent(id); }} />"
            "</Route>"
        ),
        "frontend/src/StudentDelete.js": (
            "const StudentDelete = ({ onDelete }) => {"
            "  const { id } = useParams();"
            "  const handleDelete = async () => { await onDelete(id); };"
            "  return <button onClick={handleDelete}>Delete</button>;"
            "};"
        ),
    }
    assert _callback_prop_arity_mismatch_findings(files) == []


def test_a_zero_arity_call_is_still_caught() -> None:
    """The pre-fix golden-work-113 delete shape: onDelete() called with
    zero arguments against a 1-parameter callback."""
    files = {
        "frontend/src/App.js": (
            "<Route path='/students/delete/:id'>"
            "<StudentDelete onDelete={async (id) => { await deleteStudent(id); }} />"
            "</Route>"
        ),
        "frontend/src/StudentDelete.js": (
            "const StudentDelete = ({ onDelete }) => {"
            "  const handleDelete = async () => { await onDelete(); };"
            "  return <button onClick={handleDelete}>Delete</button>;"
            "};"
        ),
    }
    findings = _callback_prop_arity_mismatch_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_callback_prop_arity_mismatch"


def test_a_destructured_parameter_is_not_miscounted() -> None:
    """`({ id }) => ...` is one real parameter, not comma-split garbage."""
    files = {
        "frontend/src/App.js": (
            "<StudentForm onSubmit={async ({ id, name }) => { await updateStudent(id, name); }} />"
        ),
        "frontend/src/StudentForm.js": (
            "const StudentForm = ({ onSubmit }) => {"
            "  const handleSubmit = async () => { await onSubmit({ id, name }); };"
            "  return <form onSubmit={handleSubmit}></form>;"
            "};"
        ),
    }
    assert _callback_prop_arity_mismatch_findings(files) == []


def test_a_non_mutation_prop_like_onclick_is_not_checked() -> None:
    files = {
        "frontend/src/App.js": (
            "<Button onClick={async (a, b, c) => { await doThing(a, b, c); }} />"
        ),
        "frontend/src/Button.js": (
            "const Button = ({ onClick }) => {"
            "  return <button onClick={() => onClick(a)}>Go</button>;"
            "};"
        ),
    }
    assert _callback_prop_arity_mismatch_findings(files) == []


def test_silent_when_the_component_definition_cannot_be_found() -> None:
    files = {
        "frontend/src/App.js": (
            "<StudentForm onSubmit={async (id, name, email) => { await updateStudent(id, name, email); }} />"
        ),
    }
    assert _callback_prop_arity_mismatch_findings(files) == []


def test_silent_when_no_frontend_files_exist() -> None:
    assert _callback_prop_arity_mismatch_findings({"backend/app.py": "onSubmit(a, b, c)"}) == []
