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

from arkali.engineering.factory.semantic_finding import SemanticFinding

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


#: golden-work-097 (session evidence, frozen): `frontend/src/App.js`
#: declared a real, fully correct `<Router><Switch>` with all four real
#: routes wired (create/edit/delete/list, even a `/` -> `/tasks` redirect)
#: -- but `frontend/src/index.js` never imported or mounted `App` at all;
#: it rendered `<TaskList />` directly. A real production build compiled
#: successfully and a real browser, tied to that exact build's own script
#: hash, crashed outright with a real react-router `Invariant failed`
#: (`<Link>` used with no `<Router>` ancestor anywhere in the real render
#: tree) -- the entire app rendered nothing, and every route App.js
#: declared (the whole create/edit/delete feature set) was unreachable
#: dead code.
_ROUTER_TAG = re.compile(r"<(?:Router|BrowserRouter|HashRouter)\b")
_RENDER_ROOT_TAG = re.compile(r"ReactDOM\.render\(\s*(?:<React\.StrictMode>\s*)?<(\w+)")


def _module_stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    for suffix in (".jsx", ".js"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _router_root_path(files: Mapping[str, str]) -> str | None:
    return next(
        (
            path for path, source in files.items()
            if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
            and path != "frontend/src/index.js"
            and _ROUTER_TAG.search(source)
        ),
        None,
    )


def _orphaned_router_root_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Fires only when some OTHER file (never index.js itself -- a router
    declared inline in index.js is `_missing_root_route_findings`'s own
    concern, not this one) declares a real
    `<Router>`/`<BrowserRouter>`/`<HashRouter>` and index.js's own
    `ReactDOM.render(...)` call never mounts that exact component. No
    blind mechanical guess exists for a genuinely NEW candidate (picking
    the app's real root requires knowing which component that is) --
    `_repair_orphaned_router_root`, below, instead restores a real,
    already-proven-correct prior version when one exists, the one case
    this can be resolved mechanically without guessing."""
    index_source = files.get("frontend/src/index.js")
    if index_source is None:
        return []
    router_root_path = _router_root_path(files)
    if router_root_path is None:
        return []
    router_root_name = _module_stem(router_root_path)
    match = _RENDER_ROOT_TAG.search(index_source)
    if match is not None and match.group(1) == router_root_name:
        return []
    return [SemanticFinding(
        code="frontend_router_root_orphaned", path="frontend/src/index.js",
        detail=(
            f"{router_root_path} declares a real <Router>/<Switch> but "
            f"frontend/src/index.js never mounts {router_root_name!r} -- every "
            "route it declares is unreachable dead code, and any react-router "
            "component/hook used elsewhere without that Router ancestor throws a "
            f"real runtime crash. Import and mount <{router_root_name} /> in "
            "index.js instead of a leaf component that bypasses the app's own "
            "routing tree"
        ),
    )]


def _repair_orphaned_router_root(
    visible_files: Mapping[str, str], stage_files: Mapping[str, str],
) -> dict[str, str] | None:
    """golden-work-100/102/103 (session evidence, frozen -- the identical
    compound failure reproduced across three independent candidates,
    the last two byte-for-byte identical): `frontend_ui`'s own attempt
    already proved index.js correctly mounts the real router root --
    `frontend_ui`'s own validator runs this exact check before
    `frontend_forms` ever starts, so `visible_files`' own real index.js
    (`frontend_ui`'s declared output, one of `frontend_forms`'s own
    declared inputs per `STAGED_GENERATION_STAGES.md#9`) is always
    already known-good. That same stage rule explicitly says not to
    rewrite `frontend_ui`'s own navigation -- "add the missing mutation
    UI onto them, do not rewrite them" -- but a real qwen2.5-coder:14b
    exhausted all 4 real attempts on three separate real candidates
    regenerating index.js incorrectly anyway. Restoring the known-good
    prior version enforces the stage's own explicit instruction
    mechanically rather than guessing at new behavior -- checked, not
    assumed, that doing so actually resolves the real defect (and does
    not silently mask some other, genuinely different mistake) before
    ever applying it."""
    index_path = "frontend/src/index.js"
    prior = visible_files.get(index_path)
    current = stage_files.get(index_path)
    if prior is None or current is None or prior == current:
        return None
    if not _orphaned_router_root_findings({**visible_files, **stage_files}):
        return None
    restored = {**stage_files, index_path: prior}
    if _orphaned_router_root_findings({**visible_files, **restored}):
        return None
    return restored
