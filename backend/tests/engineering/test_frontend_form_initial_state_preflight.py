from __future__ import annotations

from arkali.engineering.factory.frontend_form_initial_state_preflight import (
    _form_initial_data_ignored_findings,
)

#: golden-work-127/128/129 (real repository evidence, real qwen2.5-coder:14b,
#: frozen, independently reproduced three times with zero variation) --
#: the exact real shape that reached a real browser acceptance failure:
#: `StudentForm` never destructures `initialData` at all.
_GOLDEN_WORK_129_STUDENT_FORM = """
const StudentForm = ({ onSubmit, fields }) => {
  const [formData, setFormData] = useState({});
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };
  return React.createElement('form', null);
};
"""
_GOLDEN_WORK_129_STUDENT_EDIT_CALL_SITE = (
    "<StudentForm onSubmit={handleSubmit} fields={['name', 'email']} initialData={student} />"
)

#: The fix this same module's own finding `detail` text recommends --
#: destructure, seed, and resync via useEffect on the real prop itself.
_FIXED_STUDENT_FORM = """
const StudentForm = ({ onSubmit, fields, initialData }) => {
  const [formData, setFormData] = useState(initialData || {});
  useEffect(() => { setFormData(initialData || {}); }, [initialData]);
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };
  return React.createElement('form', null);
};
"""

#: A real, plausible "shallowest patch that satisfies the naive check"
#: shape: the retry adds `initialData` to the destructure list but never
#: actually wires it into any state -- accepted, then silently dropped.
_DESTRUCTURED_BUT_UNUSED_STUDENT_FORM = """
const StudentForm = ({ onSubmit, fields, initialData }) => {
  const [formData, setFormData] = useState({});
  const handleChange = (e) => {
    const { name, value } = e.target;
    setFormData({ ...formData, [name]: value });
  };
  return React.createElement('form', null);
};
"""


def _files(form_source: str, call_site: str) -> dict[str, str]:
    return {"frontend/src/Students.js": form_source + "\n" + call_site}


def test_a_create_form_with_no_initial_data_prop_is_never_flagged() -> None:
    """Property A: normal create-form generation (no edit route, no
    initialData anywhere) is completely untouched by this check."""
    files = {
        "frontend/src/Students.js": (
            "const StudentForm = ({ onSubmit, fields }) => { "
            "const [formData, setFormData] = useState({}); return null; };\n"
            "<StudentForm onSubmit={handleSubmit} fields={['name', 'email']} />"
        ),
    }
    assert _form_initial_data_ignored_findings(files) == []


def test_b_and_g_a_correctly_wired_edit_form_is_never_flagged() -> None:
    """Properties B and G: the exact recommended fix -- destructured AND
    genuinely referenced beyond the destructure itself -- is a real PASS."""
    files = _files(_FIXED_STUDENT_FORM, _GOLDEN_WORK_129_STUDENT_EDIT_CALL_SITE)
    assert _form_initial_data_ignored_findings(files) == []


def test_f_catches_golden_work_129s_own_real_defect() -> None:
    """Property F: the caller passes real, fetched initial data; the
    generated component ignores it entirely -- a real FAIL, the exact
    golden-work-127/128/129 shape."""
    files = _files(_GOLDEN_WORK_129_STUDENT_FORM, _GOLDEN_WORK_129_STUDENT_EDIT_CALL_SITE)
    findings = _form_initial_data_ignored_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_form_initial_data_never_consumed"
    assert "StudentForm" in findings[0].detail
    assert "initialData" in findings[0].detail


def test_f_also_catches_the_shallow_destructure_without_state_state_wiring() -> None:
    """The deeper tier of property F: a real retry could satisfy the
    shallow "is initialData destructured" check without genuinely wiring
    it into any state -- the same one-step-further shape
    `frontend_ui_route_id_read_but_not_passed` already treats as equally
    real for `useParams()`'s own id."""
    files = _files(_DESTRUCTURED_BUT_UNUSED_STUDENT_FORM, _GOLDEN_WORK_129_STUDENT_EDIT_CALL_SITE)
    findings = _form_initial_data_ignored_findings(files)
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_form_initial_data_destructured_but_unused"


def test_h_a_structurally_different_domain_reproduces_the_identical_behavior() -> None:
    """Properties C/H: the identical check, over a structurally unrelated
    domain (task/title, never student/name) -- proves no hardcoding."""
    broken = {
        "frontend/src/Tasks.js": (
            "const TaskForm = ({ onSubmit, fields }) => { "
            "const [formData, setFormData] = useState({}); return null; };\n"
            "<TaskForm onSubmit={handleSubmit} fields={['title', 'due_date']} "
            "initialData={task} />"
        ),
    }
    findings = _form_initial_data_ignored_findings(broken)
    assert len(findings) == 1
    assert findings[0].code == "frontend_ui_form_initial_data_never_consumed"
    assert "TaskForm" in findings[0].detail

    fixed = {
        "frontend/src/Tasks.js": (
            "const TaskForm = ({ onSubmit, fields, initialData }) => { "
            "const [formData, setFormData] = useState(initialData || {}); "
            "useEffect(() => { setFormData(initialData || {}); }, [initialData]); "
            "return null; };\n"
            "<TaskForm onSubmit={handleSubmit} fields={['title', 'due_date']} "
            "initialData={task} />"
        ),
    }
    assert _form_initial_data_ignored_findings(fixed) == []


def test_a_literal_value_is_never_treated_as_real_threaded_data() -> None:
    """`initialData={{}}` (an inline empty-object literal) is not evidence
    a caller is threading through a real fetched record -- only a bare
    identifier reference is."""
    files = {
        "frontend/src/Students.js": (
            "const StudentForm = ({ onSubmit, fields }) => { return null; };\n"
            "<StudentForm onSubmit={handleSubmit} fields={['name']} initialData={{}} />"
        ),
    }
    assert _form_initial_data_ignored_findings(files) == []


def test_silent_when_the_component_definition_cannot_be_found() -> None:
    files = {
        "frontend/src/App.js": (
            "<StudentForm onSubmit={handleSubmit} fields={['name']} initialData={student} />"
        ),
    }
    assert _form_initial_data_ignored_findings(files) == []


def test_silent_when_no_frontend_files_exist() -> None:
    assert _form_initial_data_ignored_findings({"backend/app.py": "x = 1"}) == []


def test_only_one_finding_per_component_even_with_multiple_call_sites() -> None:
    files = _files(
        _GOLDEN_WORK_129_STUDENT_FORM,
        _GOLDEN_WORK_129_STUDENT_EDIT_CALL_SITE + "\n" + _GOLDEN_WORK_129_STUDENT_EDIT_CALL_SITE,
    )
    findings = _form_initial_data_ignored_findings(files)
    assert len(findings) == 1
