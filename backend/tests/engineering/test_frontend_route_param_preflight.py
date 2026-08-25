from __future__ import annotations

from arkali.engineering.factory.frontend_route_param_preflight import (
    _unread_route_param_findings,
)

#: golden-work-113 (real repository evidence, real qwen2.5-coder:14b,
#: frozen): the real shape that reached a real browser acceptance
#: failure - neither useParams() nor match.params is ever read anywhere.
_GOLDEN_WORK_113_APP_JS = (
    "<Switch>"
    "<Route path='/students/edit/:id'>"
    "<StudentForm onSubmit={async (id, name, email) => {"
    "await updateStudent(id, name, email);"
    "}} />"
    "</Route>"
    "<Route path='/students/delete/:id'>"
    "<StudentDelete onDelete={async (id) => { await deleteStudent(id); }} />"
    "</Route>"
    "</Switch>"
)


def test_catches_golden_work_113s_own_real_defect() -> None:
    findings = _unread_route_param_findings(
        {"frontend/src/App.js": _GOLDEN_WORK_113_APP_JS}
    )
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_route_param_never_read"
    assert "'id'" in findings[0].detail


def test_the_finding_gives_a_literal_copy_pasteable_fix() -> None:
    """golden-work-115 (session evidence, frozen): the first, prose-only
    wording of this finding was fed back verbatim on every retry and the
    model still exhausted the frontend_forms stage's full 4-attempt
    budget without ever satisfying it. Reworded to name the exact line to
    add, the same lesson the golden-work-050/051 Werkzeug<3 finding
    already established for this pipeline."""
    findings = _unread_route_param_findings(
        {"frontend/src/App.js": _GOLDEN_WORK_113_APP_JS}
    )
    assert "const { id } = useParams();" in findings[0].detail


def test_use_params_destructure_satisfies_the_route() -> None:
    files = {
        "frontend/src/App.js": (
            "<Route path='/students/edit/:id'><EditStudent /></Route>"
        ),
        "frontend/src/EditStudent.js": (
            "function EditStudent() { const { id } = useParams(); "
            "return updateStudent(id); }"
        ),
    }
    assert _unread_route_param_findings(files) == []


def test_a_renamed_use_params_destructure_still_satisfies_the_route() -> None:
    files = {
        "frontend/src/App.js": (
            "<Route path='/students/edit/:id'><EditStudent /></Route>"
        ),
        "frontend/src/EditStudent.js": (
            "function EditStudent() { const { id: studentId } = useParams(); "
            "return updateStudent(studentId); }"
        ),
    }
    assert _unread_route_param_findings(files) == []


def test_direct_use_params_member_access_satisfies_the_route() -> None:
    """golden-work-121 (real repository evidence, real qwen2.5-coder:14b,
    frozen): `useParams().id`, called and immediately member-accessed
    with no intermediate variable - equally valid, idiomatic JS, and a
    real false positive against the destructure-only pattern before this
    was recognized (verified directly against golden-work-121's own
    frozen last-attempt output, which used exactly this pattern in both
    the edit route's onSuccess callback and the delete route's onClick
    handler and was still, wrongly, flagged)."""
    files = {
        "frontend/src/App.js": (
            "<Route path='/students/edit/:id'><StudentForm "
            "onSuccess={() => setStudents(students.map(s => "
            "s.id === parseInt(useParams().id) ? s : s))} /></Route>"
        ),
    }
    assert _unread_route_param_findings(files) == []


def test_match_params_access_satisfies_the_route() -> None:
    files = {
        "frontend/src/App.js": (
            "<Route path='/students/edit/:id' render={({ match }) => "
            "<EditStudent studentId={match.params.id} />} />"
        ),
    }
    assert _unread_route_param_findings(files) == []


def test_reads_the_param_in_a_different_file_than_the_route_declaration() -> None:
    """A real, legal split: the router config and the component consuming
    the param can live apart. The check must not require them colocated."""
    files = {
        "frontend/src/App.js": "<Route path='/students/edit/:id'><EditStudent /></Route>",
        "frontend/src/EditStudent.js": "const { id } = useParams();",
    }
    assert _unread_route_param_findings(files) == []


def test_a_route_with_no_parameter_is_not_flagged() -> None:
    files = {"frontend/src/App.js": "<Route path='/students'><Students /></Route>"}
    assert _unread_route_param_findings(files) == []


def test_silent_when_no_frontend_files_exist() -> None:
    assert _unread_route_param_findings({"backend/app.py": "id = ':id'"}) == []


def test_only_the_missing_parameter_is_named_when_others_are_read() -> None:
    files = {
        "frontend/src/App.js": (
            "<Route path='/students/edit/:id'><EditStudent /></Route>"
            "<Route path='/payments/edit/:paymentId'><EditPayment /></Route>"
        ),
        "frontend/src/EditStudent.js": "const { id } = useParams();",
    }
    findings = _unread_route_param_findings(files)
    assert len(findings) == 1
    assert "paymentId" in findings[0].detail
    assert "'id'" not in findings[0].detail
