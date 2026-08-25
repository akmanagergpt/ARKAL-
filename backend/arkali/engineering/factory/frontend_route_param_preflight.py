"""A declared route URL parameter that no component ever reads.

Owner: `engineering.factory`. `frontend_forms`'s own concern (mutation UI
correctness), the same seam `frontend_route_shadowing_preflight.py` and
`frontend_manifest_preflight.py::_route_component_missing_props_findings`
are already split along.

golden-work-113 (real repository evidence, real qwen2.5-coder:14b,
frozen): `App.js` declared `<Route path="/students/edit/:id">` and
`<Route path="/students/delete/:id">`, each wrapping a shared form/
confirmation component through react-router v5's CHILDREN form -
`<Route path="..."><StudentForm onSubmit={...} /></Route>` - which,
unlike `component=`/`render=`, never injects `match`/`location`/`history`
as props at all. Nothing anywhere in the frontend called `useParams()` or
read `match.params.id` (or any `props.match.params.*` variant either), so
neither edit nor delete route could ever know which record it was acting
on: `StudentForm`'s own `onSubmit(name, email)` call (2 arguments) was
wired to an outer handler declared `async (id, name, email) => {...}` (3
parameters), so `id` silently received the *name* value at runtime and
the update targeted a URL built from it — a real acceptance failure,
reached only by a real browser session, that `_route_component_missing_
props_findings` cannot see (it is scoped to the unrelated `component=`
injection failure mode, which this candidate's routes never use).

DELIBERATELY GENERAL, NOT GOLDEN-SPECIFIC. Any route path carrying a
`:name` segment obligates SOME real component reached from it to read
that exact name — via `useParams()` destructuring it (renamed or not),
via `useParams().name` accessed directly with no intermediate variable
(golden-work-121, session evidence, frozen: a real, valid, idiomatic
pattern this check's first version did not recognize, a real false
positive on an otherwise-correct candidate, caught by reading that
candidate's own frozen last-attempt output directly rather than assuming
the finding was right), or via a `match.params.name` /
`props.match.params.name` access anywhere in the frontend. Checked
across the whole frontend, not per file: a real, legal split (the router
config in one file, the params consumed in a
component it renders) must not be flagged just because the two live
apart.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.semantic_finding import SemanticFinding

_ROUTE_TAG = re.compile(r"<Route\s[^>]*?path=[\"']([^\"']+)[\"'][^>]*>")
_ROUTE_PARAM_NAME = re.compile(r":(\w+)")
#: Matches both `match.params.id` (and any `props.`/`this.` prefix on
#: `match`) and a bare `params.id` from `const { params } = match`.
_PARAM_MEMBER_ACCESS = re.compile(r"\bparams\s*\.\s*(\w+)\b")
#: `[^{}]`, not `[^}]`: a non-nesting match is required, or an enclosing
#: `{` (a function body, an outer object) preceding the real destructuring
#: makes the non-greedy group swallow everything up to the destructuring's
#: OWN closing brace instead of stopping at its opening one.
_USE_PARAMS_DESTRUCTURE = re.compile(r"\{([^{}]*)\}\s*=\s*useParams\s*\(")
#: golden-work-121 (real repository evidence, real qwen2.5-coder:14b,
#: frozen): `useParams().id`, called and immediately member-accessed with
#: no intermediate variable at all - equally valid, idiomatic JS, and a
#: real false positive against the destructure-only pattern above before
#: this was added (verified: golden-work-121's own frozen last-attempt
#: output used this pattern consistently and correctly, in both the edit
#: route's `onSuccess` callback and the delete route's `onClick` handler,
#: and this check still reported `id` as never read).
_USE_PARAMS_MEMBER_ACCESS = re.compile(r"useParams\s*\(\s*\)\s*\.\s*(\w+)")


def _frontend_files(files: Mapping[str, str]) -> dict[str, str]:
    return {
        path: source for path, source in files.items()
        if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
    }


def _declared_route_param_names(source: str) -> set[str]:
    names: set[str] = set()
    for match in _ROUTE_TAG.finditer(source):
        names |= set(_ROUTE_PARAM_NAME.findall(match.group(1)))
    return names


def _read_route_param_names(source: str) -> set[str]:
    read = set(_PARAM_MEMBER_ACCESS.findall(source)) | set(_USE_PARAMS_MEMBER_ACCESS.findall(source))
    for block in _USE_PARAMS_DESTRUCTURE.findall(source):
        for piece in block.split(","):
            # `{ id: studentId }` renames the *local* binding; the real
            # route param name being read is the part before the colon.
            name = piece.split(":")[0].strip()
            if name:
                read.add(name)
    return read


def _unread_route_param_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    frontend = _frontend_files(files)
    if not frontend:
        return []
    declared: dict[str, str] = {}
    for path, source in frontend.items():
        for name in _declared_route_param_names(source):
            declared.setdefault(name, path)
    if not declared:
        return []
    read: set[str] = set()
    for source in frontend.values():
        read |= _read_route_param_names(source)
    missing = sorted(set(declared) - read)
    if not missing:
        return []
    name = missing[0]
    return [SemanticFinding(
        code="frontend_ui_route_param_never_read", path=declared[name],
        detail=(
            f"<Route path> declares URL parameter {name!r} ({missing!r} total) that no "
            "component anywhere reads, so a mutation triggered from that route cannot "
            "know which record it targets. Fix: as the first line inside the function "
            "of whichever component that route renders, add exactly "
            f"`const {{ {name} }} = useParams();` (import useParams from "
            "'react-router-dom' if not already imported), then pass that "
            f"{name} value as the actual argument to the update/delete client call — "
            "never rely on a form's own onSubmit(name, email)-style arguments to carry "
            f"it. Do not add a `:{name}` prop to the routed component itself: the "
            "children <Route path=\"...\"><Comp /></Route> form used here never "
            "injects match/location/history as props the way component=/render= do."
        ),
    )]
