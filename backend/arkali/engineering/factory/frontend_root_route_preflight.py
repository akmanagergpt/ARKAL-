"""Root-path ("/") reachability for a generated react-router frontend.

Owner: `engineering.factory`. golden-work-092 (session evidence, frozen):
reached `STAGED_GENERATION_PASS`, real backend install/tests/runtime/CRUD/
restart-persistence all genuinely passed, `npm install` and the real
production build both succeeded -- then a real browser navigating to the
app's own base URL (`http://127.0.0.1:3000/`, exactly what `npm start`/a
deployed static build serves by default) rendered a genuinely blank page:
no console error, no crash, `document.body` reduced to the empty
`<div id="root">` react mounts into. `frontend/src/index.js` mounted a
real `<Switch>` with four real `<Route>` declarations (`/students`,
`/students/edit/:id`, `/courses`, `/payments`) and none of them ever
matches the bare root path "/" -- react-router only renders a route whose
`path` the current URL actually starts with, and "/" starts with none of
those literal segments. Confirmed distinct from a real defect by then
navigating to a declared route (`/students`), which rendered the full
real dashboard correctly. `node --check` cannot see this (syntactically
legal JSX, the same class of gap every other check in this bounded
context already exists to catch); only real route-matching semantics
prove it.

Lives in its own module rather than `frontend_manifest_preflight.py` or
`frontend_ux_preflight.py` (ADR-0008 decomposition, not a GATE 8
exception): both already sit at their own measured 400-logical-line
ceiling, the same real, live budget exhaustion that first forced
`frontend_client_call_preflight.py` out on its own earlier this session.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding

_ROUTE_OR_REDIRECT_TAG = re.compile(r"<(Route|Redirect)\b([^>]*)/?>")
_PATH_ATTR = re.compile(r"""\bpath=["']([^"']+)["']""")
_FROM_ATTR = re.compile(r"""\bfrom=["']([^"']+)["']""")


def _root_path_reachable(source: str) -> bool:
    for tag, attrs in _ROUTE_OR_REDIRECT_TAG.findall(source):
        if tag == "Route":
            path_match = _PATH_ATTR.search(attrs)
            if path_match is not None and path_match.group(1) == "/":
                return True
        else:  # Redirect -- no `from=` at all is a real, idiomatic v5
            # catch-all default that reaches every unmatched path,
            # including "/"; an explicit `from="/"` reaches it directly.
            from_match = _FROM_ATTR.search(attrs)
            if from_match is None or from_match.group(1) == "/":
                return True
    return False


def _missing_root_route_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Fires only when a file actually uses react-router's `<Switch>` with
    real `<Route>` children (a single unconditional `ReactDOM.render(<App
    />, ...)` with no router at all is not this defect -- root always
    renders the same component there) and none of its declared
    `<Route>`/`<Redirect>` children ever reaches "/". Runs unconditionally
    (no `product_ux_spec` dependency) -- a general react-router
    correctness rule, not specific to the staged pipeline, the same shape
    `frontend_manifest_preflight.py`'s own router checks already use. No
    deterministic repair exists (unlike a version pin or a missing import,
    picking which real destination "/" should show or redirect to is a
    genuine product decision, not a mechanically unambiguous fix) --
    finding-only, feeding the model concrete instructions, the same shape
    `frontend_manifest_preflight._route_component_missing_props_findings`
    already uses."""
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        if "<Switch" not in source or "<Route" not in source:
            continue
        if _root_path_reachable(source):
            continue
        findings.append(SemanticFinding(
            code="frontend_root_path_unreachable", path=path,
            detail=(
                f"{path} declares a <Switch> with <Route> children but none of them "
                "ever matches the bare root path \"/\" -- a real end user landing on "
                "the app's own base URL sees a blank page. Add <Route exact "
                "path=\"/\"> rendering something real, or a <Redirect exact from=\"/\" "
                "to=\"...\"> to a real existing route"
            ),
        ))
    return findings
