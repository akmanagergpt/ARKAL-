"""A caller passes an edit form real, fetched entity data -- the receiving
form component never reads it.

Owner: `engineering.factory`. `frontend_forms`'s own concern, the same
seam `frontend_callback_arity_preflight.py` and `frontend_route_param_
preflight.py` are already split along.

golden-work-127/128/129 (real repository evidence, real qwen2.5-coder:14b,
frozen, independently reproduced three times with zero variation --
`golden-work-129`'s own three real repair attempts, `golden-work-129-
repair-1/2/3`, each inherited the identical shape unchanged): a real
ARKALI LIVE PRODUCT CHECKPOINT against `golden-work-129`'s own real running
product found its edit route renders a genuinely blank form. The real
generated shape, unchanged across all three independent candidates:

    const StudentForm = ({ onSubmit, fields }) => {
      const [formData, setFormData] = useState({});
      ...
    };

    const StudentEdit = () => {
      const { id } = useParams();
      const [student, setStudent] = useState({});
      useEffect(() => { fetchStudent(); }, [id]);  // real, correct fetch
      ...
      return (
        <StudentForm onSubmit={handleSubmit} fields={['name', 'email']}
                     initialData={student} />
      );
    };

`StudentEdit` does everything right: it fetches the real record by the
route's own real id and threads it into `initialData={student}`, a real,
non-literal, non-trivial identifier value -- clearly a deliberate attempt
to pass real fetched data, not an incidental prop. `StudentForm` itself
never destructures `initialData` at all; its own `formData` state
initializes unconditionally to `{}`, with no path by which the caller's
real data could ever reach it. Confirmed as this pipeline's own real,
independently-repeated convention name, not one candidate's local
choice: `initialData` is the literal identifier name all three of
golden-work-127, -128 and -129's own independently generated
`StudentForm` call sites use, verified directly against each
candidate's own real source (`var/factory/candidates/golden-work-1{27,
28,29}/frontend/src/Students.js`) -- the same posture already taken for
`frontend_callback_arity_preflight._ROUTE_IDENTIFIER_PARAM_NAME = "id"`:
a real, evidenced, pipeline-wide naming convention this real model
consistently reaches for on its own, never declared by `product_ux_spec.
json` or any other schema, and named nowhere close to a golden-domain
concept (never "Student", "Payment", "name", "email").

GENERAL, NOT ROUTE- OR FIELD-SPECIFIC. The defect is a plain JSX prop
threaded to a real, by-name-resolvable component definition that never
consumes it -- no field name, resource name or domain concept appears
anywhere in this check. `_form_initial_data_ignored_findings` below
covers two distinct depths of the same gap: (1) the call site passes
`initialData={<a real identifier>}` and the receiving component's own
definition does not destructure a prop of that name at all -- the exact
`golden-work-127/128/129` shape; and (2) the receiving component DOES
destructure `initialData` but the name never appears again anywhere else
in its own body -- accepted, then silently dropped, a real retry
producing the shallowest patch that satisfies (1) without wiring any
state, the same one-step-further shape `frontend_callback_arity_
preflight._route_id_read_but_not_passed_findings` already treats as
equally real for `useParams()`'s own `id`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.frontend_js_semantics import (
    _balanced_brace_body,
    _component_destructured_props,
)
#: Imported via `product_preflight`'s own established re-export, not
#: directly from `semantic_finding` -- `semantic_finding`'s own fan-in was
#: already at its `AUTHORITY_MAP.yaml` ceiling (15) before this module
#: existed; a direct import here would have been the 16th edge and failed
#: `architecture_budget_violation` live. `product_preflight` already
#: re-exports it for the identical reason (`component_generation.py`'s own
#: `from arkali.engineering.factory.product_preflight import SemanticFinding`).
from arkali.engineering.factory.product_preflight import SemanticFinding

#: This pipeline's own real, independently-repeated convention name for
#: "the record's existing data, threaded into a shared create/edit form" --
#: see this module's own docstring for the real, frozen, three-candidate
#: evidence. Never a golden-domain concept.
_INITIAL_DATA_PROP_NAME = "initialData"
#: `<StudentForm ... initialData={student} ...>` -- a bare identifier
#: value only (never a string/number/boolean/object literal): the real
#: evidenced shape is always a variable reference to fetched state, and a
#: literal value at this exact prop name is not evidence of a caller
#: intending to thread through a real record's data.
_JSX_INITIAL_DATA_PROP = re.compile(
    rf"<(?P<comp>[A-Z]\w*)\b[^>]*?\b{_INITIAL_DATA_PROP_NAME}"
    r"=\{\s*(?P<value>[A-Za-z_$][\w$]*)\s*\}"
)
#: `const Name = ({ ... }) => {` or `function Name({ ... }) {` -- the same
#: destructured-single-props-object shape `_component_destructured_props`
#: already matches, extended just far enough to also capture the real
#: function body's own opening brace, so `_balanced_brace_body` can pull
#: the real body text out from there.
_COMPONENT_BODY_OPEN_BRACE = (
    r"(?:const\s+{name}\s*=\s*\(\s*\{{[^{{}}]*\}}\s*\)\s*=>\s*\{{"
    r"|function\s+{name}\s*\(\s*\{{[^{{}}]*\}}\s*\)\s*\{{)"
)


def _frontend_files(files: Mapping[str, str]) -> dict[str, str]:
    return {
        path: source for path, source in files.items()
        if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
    }


def _component_body(name: str, source: str) -> str | None:
    """The real text of `name`'s own function body (after its destructured
    single-props-object parameter) -- `None` if `source` never defines it
    this way. Reuses `_balanced_brace_body` for the same reason
    `frontend_callback_arity_preflight` already does: a naive `[^}]*`
    match stops at the first inner `}` a real nested object or JSX block
    already contains."""
    match = re.search(_COMPONENT_BODY_OPEN_BRACE.format(name=re.escape(name)), source)
    if match is None:
        return None
    return _balanced_brace_body(source, match.end() - 1)


def _form_initial_data_ignored_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    frontend = _frontend_files(files)
    if not frontend:
        return []
    all_source = "\n".join(frontend.values())
    findings: list[SemanticFinding] = []
    seen: set[str] = set()
    for path, source in frontend.items():
        for match in _JSX_INITIAL_DATA_PROP.finditer(source):
            comp = match.group("comp")
            if comp in seen:
                continue
            declared = _component_destructured_props(comp, all_source)
            if declared is None:
                continue
            seen.add(comp)
            if _INITIAL_DATA_PROP_NAME not in declared:
                findings.append(SemanticFinding(
                    code="frontend_ui_form_initial_data_never_consumed", path=path,
                    detail=(
                        f"<{comp} {_INITIAL_DATA_PROP_NAME}={{{match.group('value')}}}> in "
                        f"{path} passes {comp} a real record's own data, but {comp}'s own "
                        f"definition never destructures a {_INITIAL_DATA_PROP_NAME!r} prop -- "
                        f"an edit route rendering a form this way always shows it genuinely "
                        f"blank, never this record's real current values. Fix {comp}'s own "
                        f"parameter list to destructure {_INITIAL_DATA_PROP_NAME} (e.g. "
                        f"`({{ onSubmit, fields, {_INITIAL_DATA_PROP_NAME} }}) => ...`), then "
                        f"seed its own form state from it, e.g. `useState({_INITIAL_DATA_PROP_NAME} "
                        f"|| {{}})`, and add a `useEffect(() => setFormData({_INITIAL_DATA_PROP_NAME} "
                        f"|| {{}}), [{_INITIAL_DATA_PROP_NAME}])` so the real values populate once "
                        f"the caller's own async fetch actually resolves, not only on first render"
                    ),
                ))
                continue
            body = _component_body(comp, all_source)
            if body is not None and _INITIAL_DATA_PROP_NAME not in body:
                findings.append(SemanticFinding(
                    code="frontend_ui_form_initial_data_destructured_but_unused", path=path,
                    detail=(
                        f"{comp}'s own definition destructures a {_INITIAL_DATA_PROP_NAME!r} "
                        f"prop but never references it again anywhere in its own body -- "
                        f"accepting the name without using it leaves the form genuinely blank "
                        f"exactly like never destructuring it at all, the same shape "
                        "frontend_ui_route_id_read_but_not_passed already treats as equally "
                        f"real for useParams()'s own id. Seed {comp}'s own form state from "
                        f"{_INITIAL_DATA_PROP_NAME} (e.g. `useState({_INITIAL_DATA_PROP_NAME} "
                        f"|| {{}})`) and add a `useEffect(() => setFormData("
                        f"{_INITIAL_DATA_PROP_NAME} || {{}}), [{_INITIAL_DATA_PROP_NAME}])` so "
                        "the real values populate once the caller's own async fetch resolves"
                    ),
                ))
    return findings


__all__ = ["_form_initial_data_ignored_findings"]
