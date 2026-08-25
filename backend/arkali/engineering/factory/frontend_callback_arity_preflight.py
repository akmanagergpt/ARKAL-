"""A mutation callback prop invoked with fewer arguments than it declares.

Owner: `engineering.factory`. `frontend_forms`'s own concern, the same seam
`frontend_route_param_preflight.py` is split along.

golden-work-113/119 (real repository evidence, real qwen2.5-coder:14b,
frozen, both independently reproduced): `App.js` rendered the SAME shared
`StudentForm` component at both `/students/create` and
`/students/edit/:id`:

    <Route path="/students/create">
      <StudentForm onSubmit={async (name, email) => {
        await createStudent(name, email); ... }} />
    </Route>
    <Route path="/students/edit/:id">
      <StudentForm onSubmit={async (id, name, email) => {
        await updateStudent(id, name, email); ... }} />
    </Route>

`StudentForm`'s own `handleSubmit` always calls `onSubmit(name, email)` -
2 arguments, unconditionally, since it has no idea which route rendered
it. At `/students/create` that matches the 2-parameter callback exactly.
At `/students/edit/:id` the 3-parameter callback receives only 2
arguments: `id` silently binds to the real `name` value, `name` binds to
the real `email` value, and `email` is `undefined` - a real acceptance
failure (a live browser session's PUT request targeted a URL built from
the student's own name), not merely a route-param problem
(`frontend_route_param_preflight.py` does not catch this: `:id` genuinely
IS read elsewhere in the same app, by `StudentDelete.js` - a real,
independent, correctly-wired sibling component for the delete route).

GENERAL, NOT ROUTE-SPECIFIC. The defect is a plain JavaScript arity
mismatch between a callback prop's declaration and its one real
invocation site, in the same component that receives it - correct at one
call site (create), wrong at another (edit) that shares the receiving
component. Scoped to mutation-shaped prop names
(`onSubmit`/`onCreate`/`onUpdate`/`onEdit`/`onSave`/`onDelete`/
`onConfirm`), not every `on*` prop: a native-event-shaped handler
(`onClick`, `onChange`) commonly has looser, legitimate arity variance
this check has no evidence about and no business flagging.

golden-work-122 (real repository evidence, real qwen2.5-coder:14b,
frozen): the identical defect, one syntactic layer removed -
`onSubmit={updateStudent}`, a BARE reference to the real, imported
`updateStudent(id, name, email)` client function, not an inline arrow
function at all. The first version of this check only recognized an
inline `async (...) => ...` prop value and missed this entirely.
`updateStudent`'s own real declared arity (3, read from its own
definition - here `apiClient.js`, found by name across the whole
frontend since it is imported, not locally inlined) is compared against
the same `StudentForm.onSubmit(name, email)` call site (2) the inline
case already checked - the identical shift, `id` again silently
receiving the real `name` value.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.semantic_finding import SemanticFinding

_MUTATION_PROP = r"on(?:Submit|Create|Update|Edit|Save|Delete|Confirm)"
_JSX_INLINE_CALLBACK_PROP = re.compile(
    rf"<(?P<comp>[A-Z]\w*)\b[^>]*?\b(?P<prop>{_MUTATION_PROP})"
    r"=\{\s*(?:async\s*)?\(\s*(?P<params>[^)]*)\)\s*=>"
)
#: `onSubmit={updateStudent}` - a bare reference to a real, elsewhere-defined
#: function, not an inline arrow at all. Excludes `{` / `(` immediately after
#: the prop so this never doubly matches what the inline pattern above
#: already covers (an inline arrow's own opening `(` or a destructuring `{`).
_JSX_BARE_CALLBACK_PROP = re.compile(
    rf"<(?P<comp>[A-Z]\w*)\b[^>]*?\b(?P<prop>{_MUTATION_PROP})=\{{\s*(?P<name>\w+)\s*\}}"
)


def _component_definition_pattern(name: str) -> str:
    escaped = re.escape(name)
    return rf"(?:function\s+{escaped}\s*\(|const\s+{escaped}\s*=)"


def _function_definition_params(name: str, source: str) -> str | None:
    """The raw parameter text of `name`'s own real definition, wherever in
    the frontend it lives - `async function name(...)` or
    `const name = (...) =>`. `None` if this file does not define it (most
    files: a bare-reference prop almost always names an IMPORTED client
    function, defined in a different file than the one rendering the JSX)."""
    escaped = re.escape(name)
    match = re.search(
        rf"(?:async\s+)?function\s+{escaped}\s*\(([^)]*)\)"
        rf"|(?:const|let|var)\s+{escaped}\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>",
        source,
    )
    if match is None:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def _split_top_level(text: str) -> list[str]:
    return [piece.strip() for piece in text.split(",") if piece.strip()]


def _frontend_files(files: Mapping[str, str]) -> dict[str, str]:
    return {
        path: source for path, source in files.items()
        if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
    }


def _arity_mismatch_finding(
    frontend: Mapping[str, str], path: str, comp: str, prop: str,
    declared: list[str], declared_as: str,
) -> SemanticFinding | None:
    """`declared` parameters/arguments for `prop`, spelled `declared_as` for
    the message, compared against `comp`'s own real call to `prop`."""
    definition_pattern = _component_definition_pattern(comp)
    defined_in = next(
        ((def_path, def_source) for def_path, def_source in frontend.items()
         if re.search(definition_pattern, def_source)),
        None,
    )
    if defined_in is None:
        return None
    def_path, def_source = defined_in
    call_match = re.search(rf"\b{re.escape(prop)}\s*\(([^)]*)\)", def_source)
    if call_match is None:
        return None
    called = _split_top_level(call_match.group(1))
    if len(called) >= len(declared):
        return None
    return SemanticFinding(
        code="frontend_ui_callback_prop_arity_mismatch", path=path,
        detail=(
            f"<{comp} {prop}={{{declared_as}}}> in {path} declares {len(declared)} "
            f"parameter(s) ({', '.join(declared)}), but {comp}'s own call to "
            f"{prop}({', '.join(called) or ''}) in {def_path} passes only "
            f"{len(called)} argument(s). Positional arguments silently shift: the "
            f"first declared parameter ({declared[0]!r}) receives whatever the "
            f"first real argument actually is, not what its name implies — a real "
            f"acceptance failure if this prop is reused at more than one route with "
            f"a different real arity. Fix by changing {comp}'s own call to "
            f"{prop}(...) to pass all {len(declared)} arguments in the same order "
            f"(reading any extra ones, such as a route id, from useParams() inside "
            f"{comp} itself if {comp} needs to know them), or by removing the "
            f"unused leading parameter(s) from this {prop} declaration"
        ),
    )


def _inline_arrow_findings(
    frontend: Mapping[str, str], path: str, source: str,
) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for match in _JSX_INLINE_CALLBACK_PROP.finditer(source):
        comp, prop, params_text = match.group("comp", "prop", "params")
        # A destructured or array-pattern parameter (`({ id }) => ...`) is one
        # real parameter, not several comma-separated ones; a naive split
        # would over-count it. Too coarse to disambiguate safely, so this
        # shape is skipped rather than risking a false positive.
        if "{" in params_text or "[" in params_text:
            continue
        declared = _split_top_level(params_text)
        if not declared:
            continue
        finding = _arity_mismatch_finding(
            frontend, path, comp, prop, declared, f"async ({', '.join(declared)}) => ...",
        )
        if finding is not None:
            findings.append(finding)
    return findings


def _bare_reference_declared_params(name: str, frontend: Mapping[str, str]) -> str | None:
    """`name`'s own real parameter text, searched across every frontend file
    - a bare-reference prop almost always names an imported client function,
    defined in a different file than the one rendering the JSX."""
    return next(
        (found for found in (_function_definition_params(name, source) for source in frontend.values())
         if found is not None),
        None,
    )


def _bare_reference_findings(
    frontend: Mapping[str, str], path: str, source: str,
) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for match in _JSX_BARE_CALLBACK_PROP.finditer(source):
        comp, prop, name = match.group("comp", "prop", "name")
        params_text = _bare_reference_declared_params(name, frontend)
        if params_text is None or "{" in params_text or "[" in params_text:
            continue
        declared = _split_top_level(params_text)
        if not declared:
            continue
        finding = _arity_mismatch_finding(frontend, path, comp, prop, declared, name)
        if finding is not None:
            findings.append(finding)
    return findings


def _callback_prop_arity_mismatch_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    frontend = _frontend_files(files)
    findings: list[SemanticFinding] = []
    for path, source in frontend.items():
        findings.extend(_inline_arrow_findings(frontend, path, source))
        findings.extend(_bare_reference_findings(frontend, path, source))
    return findings
