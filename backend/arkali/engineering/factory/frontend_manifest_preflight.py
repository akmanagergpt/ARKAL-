"""Real, general checks that a react-scripts frontend can actually build.

Owner: `engineering.factory`. golden-work-058 (session evidence, frozen):
reached STAGED_GENERATION_PASS, all 4 real backend tests passed, real
isolated dependency install for both backend and frontend succeeded (`npm
install`, 1812 packages) — then `npm run build` failed outright:
`frontend/package.json` declared `react-scripts` as a dependency but had
no `scripts` object at all, so neither `build` nor `start` existed to
run. The one-shot generation path (`model_product_generation._prompt`)
has always explicitly required "runnable build and start scripts"; the
staged `manifests` stage rule never carried that requirement over, and
no validator ever checked for it.

golden-work-059 (session evidence, frozen) then fixed that gap for real —
`npm install` succeeded, `npm run build` actually ran — and failed for a
second, different real reason: `Could not find a required file. Name:
index.js. Searched in: frontend/src`. `react-scripts build`'s webpack
config hard-codes `src/index.js` as the entry point (not configurable
without ejecting). Requiring it at `manifests` (mirroring the working
`public/index.html` check) seemed consistent — but golden-work-061
(session evidence, frozen) exhausted `manifests`'s full budget on
exactly this finding, unchanged, every attempt: `manifests`' own reduced
context (`manifest_context.py`) deliberately strips real local file
names to keep its prompt small (the golden-046 timeout fix), so the
model at that stage cannot know which component to import into
`index.js` — a structurally different requirement from
`public/index.html`, which needs no local-file knowledge at all. Moved
to `frontend_ui`'s own stage validator instead
(`component_generation._frontend_ui_findings`), where the model has full
visibility into the exact component file it just wrote in the same call.

golden-work-070 (session evidence, frozen): `npm run build` failed a
third real way — package.json's `scripts` called `react-scripts build`,
but `react-scripts` was never declared in `dependencies` or
`devDependencies` at all, so `npm install` never installed it and the
command was not recognized. The scripts-completeness check above never
caught this: it only ever confirmed `start`/`build` existed, never that
the package the tautologically bare "react-scripts" substring test
detected was genuinely installable.

GENERAL, NOT GOLDEN-SPECIFIC. Checks the real, parsed JSON structure or
the real declared file set — never any specific script command text,
component name or app name.

golden-work-078 (real end-to-end execution evidence, frozen): reached
`STAGED_GENERATION_PASS`, real backend install/tests/runtime/CRUD/restart-
persistence all genuinely passed, `npm install` succeeded — then the real
production build failed outright: `Attempted import error: 'Switch' is
not exported from 'react-router-dom'`. `frontend_ui`/`frontend_forms`'s
own stage rule (`STAGED_GENERATION_STAGES.md`) has always assumed
react-router v5's `<Switch>` API (the same route-shadowing rule
golden-work-068 established), but nothing ever constrained `manifests`'
own package.json version choice to match: it picked react-router-dom
`^6.11.2`, a real, current, genuinely-installable version — whose own
real breaking change (v6 removed `Switch` and `Route`'s children-based
API entirely) no metadata-only check can see, the same class of gap
`dependency_resolution.py`'s module docstring already documents for
Flask/Werkzeug.
"""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding

_REQUIRED_SCRIPTS = ("start", "build")
#: Mechanical, not a full JS parser: matches a real ES-module import of
#: `Switch` from 'react-router-dom', the exact real signal
#: `frontend_ui`/`frontend_forms` leave behind when they use the v5 API
#: this pipeline's own stage rule documents.
_V5_SWITCH_IMPORT = re.compile(r"import\s*\{[^}]*\bSwitch\b[^}]*\}\s*from\s*['\"]react-router-dom['\"]")
_REACT_ROUTER_V5_PIN = "^5.3.4"


def _declared_npm_packages(parsed: dict) -> set[str]:
    declared: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        section = parsed.get(key)
        if isinstance(section, dict):
            declared.update(section)
    return declared


def _missing_frontend_scripts_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    package_json = files.get("frontend/package.json", "")
    if "react-scripts" not in package_json:
        return []
    try:
        parsed = json.loads(package_json)
    except json.JSONDecodeError:
        return []  # a real JSON-syntax finding belongs to a different check
    if not isinstance(parsed, dict):
        return []
    scripts = parsed.get("scripts")
    scripts = scripts if isinstance(scripts, dict) else {}
    findings: list[SemanticFinding] = []
    missing = [name for name in _REQUIRED_SCRIPTS if not scripts.get(name)]
    if missing:
        findings.append(SemanticFinding(
            code="missing_frontend_runnable_scripts", path="frontend/package.json",
            detail=(
                f"react-scripts is declared but package.json's scripts object is "
                f"missing {missing!r} — react-scripts requires "
                "'\"scripts\": {\"start\": \"react-scripts start\", "
                "\"build\": \"react-scripts build\"}' (or equivalent) to be runnable"
            ),
        ))
    # golden-work-070 (session evidence, frozen): package.json's own
    # "scripts" object called "react-scripts build"/"react-scripts
    # start", but "react-scripts" was absent from both "dependencies" and
    # "devDependencies" entirely -- `npm install` silently installed only
    # react/react-dom/react-router-dom (19 packages, not the ~1800
    # react-scripts pulls in), and the real `npm run build` failed
    # outright: "'react-scripts' is not recognized as an internal or
    # external command". The check above only ever looked for the
    # substring "react-scripts" anywhere in the raw file text, which the
    # scripts commands themselves already satisfy -- it never checked
    # that the package was actually declared as an installable dependency.
    references_react_scripts = any("react-scripts" in str(scripts.get(name, "")) for name in _REQUIRED_SCRIPTS)
    if references_react_scripts and "react-scripts" not in _declared_npm_packages(parsed):
        findings.append(SemanticFinding(
            code="missing_react_scripts_dependency", path="frontend/package.json",
            detail=(
                "scripts references react-scripts (e.g. 'react-scripts build') but "
                "'react-scripts' is not declared in dependencies or devDependencies "
                "— npm install will not install it, and the command is not recognized"
            ),
        ))
    return findings


def _missing_frontend_entry_point_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Unconditional — checked at `frontend_ui`, which has no visibility
    into `package.json`/`react-scripts` yet (that is declared later, at
    `frontend_tests_config`/`manifests`). Every real candidate this
    session has produced a react-scripts frontend, and any React app
    needs some entry point mounting a component into the DOM regardless
    of exact build-tool choice, so this does not wait to confirm
    react-scripts specifically."""
    if "frontend/src/index.js" in files:
        return []
    return [SemanticFinding(
        code="missing_frontend_entry_point", path="frontend/src/index.js",
        detail=(
            "no frontend/src/index.js exists — react-scripts build hard-codes "
            "this exact path as its webpack entry point and fails outright "
            "without it; import the real component this stage just wrote and "
            "mount it with ReactDOM.render(<Component />, "
            "document.getElementById('root'))"
        ),
    )]


#: The exact extracted-signal path `manifest_context._manifest_context`
#: writes when it detects real v5 `Switch` usage in the full source it
#: receives before reducing it away — golden-work-079 (session evidence,
#: frozen): this check's own first version depended on raw
#: `frontend/src/*` text, which `manifests`' real reduced context never
#: carries, so it silently never fired there even though it worked in
#: isolation against full files. Shared by both sides (the extractor and
#: this reader) so they cannot drift to different path strings.
FRONTEND_USES_REACT_ROUTER_V5_SWITCH_MARKER = "_extracted/frontend_uses_react_router_v5_switch.txt"


def _uses_react_router_v5_switch(files: Mapping[str, str]) -> bool:
    if files.get(FRONTEND_USES_REACT_ROUTER_V5_SWITCH_MARKER) == "true":
        return True
    return any(
        _V5_SWITCH_IMPORT.search(content)
        for path, content in files.items()
        if path.startswith("frontend/src/")
    )


def _declared_react_router_dom_specifier(parsed: dict) -> str | None:
    for key in ("dependencies", "devDependencies"):
        section = parsed.get(key)
        if isinstance(section, dict) and "react-router-dom" in section:
            return str(section["react-router-dom"])
    return None


def _specifier_major_version(specifier: str) -> int | None:
    match = re.search(r"\d+", specifier)
    return int(match.group()) if match else None


def _react_router_version_mismatch_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """golden-work-078 (session evidence, frozen): `manifests` declared
    `react-router-dom: ^6.11.2` — a real, current, genuinely-installable
    version — while `frontend_ui`/`frontend_forms` had already written
    real v5-API source (`import { Route, Switch } from 'react-router-dom'`).
    `npm install` succeeded (both are real, resolvable packages); the real
    production build then failed outright: react-router-dom 6 removed
    `Switch` entirely. Checked only when the real source mechanically
    proves v5-API usage — this never guesses at a "correct" react-router
    major version in the abstract, only at a proven real mismatch."""
    if not _uses_react_router_v5_switch(files):
        return []
    try:
        parsed = json.loads(files.get("frontend/package.json", ""))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict):
        return []
    specifier = _declared_react_router_dom_specifier(parsed)
    if specifier is None:
        return []
    major = _specifier_major_version(specifier)
    if major is None or major < 6:
        return []
    return [SemanticFinding(
        code="react_router_version_mismatch", path="frontend/package.json",
        detail=(
            "frontend source imports Switch from react-router-dom (the real "
            f"react-router v5 API) but package.json declares "
            f"'react-router-dom': {specifier!r} — react-router-dom 6 removed "
            "Switch entirely, so a real production build fails outright with "
            "\"Attempted import error: 'Switch' is not exported from "
            "'react-router-dom'\"; declare a v5 version instead, e.g. "
            f"'react-router-dom': {_REACT_ROUTER_V5_PIN!r}"
        ),
    )]


def _repair_react_router_version_mismatch(
    merged_files: Mapping[str, str], stage_files: Mapping[str, str],
) -> dict[str, str] | None:
    """Deterministic repair mirroring `dependency_resolution.py`'s
    `Werkzeug<3` repair (golden-work-050/051's own lesson: once the exact,
    unambiguous fix for a real, verified defect is known, applying it and
    re-validating is more honest than another blind model retry). Checked
    against `merged_files` (this stage's real inputs plus its own new
    output, the same view `_stage_findings` validates) since the proving
    signal — real v5-API source — lives in an earlier stage's output, not
    this stage's own; only ever rewrites `stage_files`' own
    `frontend/package.json`, since no other stage writes it."""
    package_json = stage_files.get("frontend/package.json")
    if package_json is None or not _react_router_version_mismatch_findings(merged_files):
        return None
    try:
        parsed = json.loads(package_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    patched = dict(parsed)
    for key in ("dependencies", "devDependencies"):
        section = patched.get(key)
        if isinstance(section, dict) and "react-router-dom" in section:
            patched[key] = {**section, "react-router-dom": _REACT_ROUTER_V5_PIN}
    return {**stage_files, "frontend/package.json": json.dumps(patched, indent=2) + "\n"}


#: golden-work-083 (session evidence, frozen): `frontend/src/index.js`
#: imported only `BrowserRouter as Router` from 'react-router-dom' and
#: then used `<Route path="/students" component={Students} />` directly
#: -- a real, hard `ReferenceError: Route is not defined` at runtime,
#: blanking the entire real production build in a real browser. `node
#: --check` (javascript_syntax_preflight.py) cannot see this: an
#: undefined identifier is syntactically legal JS, only a real
#: ReferenceError at execution. Scoped to the v5 API this pipeline's
#: package.json is pinned to (STAGED_GENERATION_STAGES.md#11); deliberately
#: excludes Router/BrowserRouter/HashRouter, which real evidence shows are
#: routinely imported under an alias (`BrowserRouter as Router`) --
#: checking those would need to resolve the alias back to its real export
#: name, a real but distinct concern this narrow check does not yet cover.
#: Lives here, not `frontend_ux_preflight.py`, alongside every other
#: real react-router correctness concern this module already owns
#: (ADR-0008: `frontend_ux_preflight.py` reached its own 400-logical-line
#: ceiling).
_REACT_ROUTER_DOM_IDENTIFIERS = (
    "Route", "Switch", "Link", "NavLink", "Redirect",
    "useHistory", "useParams", "useLocation", "useRouteMatch",
)
_REACT_ROUTER_IMPORT_BLOCK = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]react-router-dom['\"]")


def _react_router_missing_import_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Every real react-router-dom identifier a file actually uses
    (`<Route`, `useHistory(`, ...) must be locally imported in that same
    file -- checked per file, not on the whole frontend joined together,
    since an import in one component never brings a name into scope in
    another. Runs unconditionally (no `product_ux_spec` dependency), the
    same shape `frontend_ux_preflight._shadowed_route_findings` already
    uses -- a general react-router correctness rule, not specific to the
    staged pipeline."""
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        imported_locals: set[str] = set()
        for block in _REACT_ROUTER_IMPORT_BLOCK.findall(source):
            for part in block.split(","):
                local_name = part.strip().split(" as ")[-1].strip()
                if local_name:
                    imported_locals.add(local_name)
        missing = sorted(
            name for name in _REACT_ROUTER_DOM_IDENTIFIERS
            if name not in imported_locals and re.search(rf"\b{name}\b", source)
        )
        if missing:
            findings.append(SemanticFinding(
                code="frontend_missing_react_router_import", path=path,
                detail=(
                    f"{path} uses {missing!r} but never imports them from "
                    "'react-router-dom' in this same file -- a real runtime "
                    "ReferenceError, not a syntax error `node --check` can see"
                ),
            ))
    return findings


def _repair_missing_imports_in_source(source: str) -> str | None:
    """One file's own repair: merges into an existing `react-router-dom`
    import statement when one exists, or adds a new one at the top when
    it does not. Returns `None` when nothing is missing. Extracted from
    `_repair_missing_react_router_imports` (ADR-0008 decomposition, not a
    GATE 8 exception: that function's own measured complexity exceeded
    its ceiling) so the per-file decision logic is measured on its own."""
    imported_locals: set[str] = set()
    import_match = _REACT_ROUTER_IMPORT_BLOCK.search(source)
    if import_match:
        for part in import_match.group(1).split(","):
            local_name = part.strip().split(" as ")[-1].strip()
            if local_name:
                imported_locals.add(local_name)
    missing = sorted(
        name for name in _REACT_ROUTER_DOM_IDENTIFIERS
        if name not in imported_locals and re.search(rf"\b{name}\b", source)
    )
    if not missing:
        return None
    if import_match is None:
        return "import { " + ", ".join(missing) + " } from 'react-router-dom';\n" + source
    existing_names = [n.strip() for n in import_match.group(1).split(",") if n.strip()]
    new_import = "import { " + ", ".join(existing_names + missing) + " } from 'react-router-dom'"
    return source[:import_match.start()] + new_import + source[import_match.end():]


def _repair_missing_react_router_imports(stage_files: Mapping[str, str]) -> dict[str, str] | None:
    """Deterministic repair mirroring this module's own `Werkzeug<3`-style
    repairs (golden-work-050/051's own lesson: once the exact, unambiguous
    fix for a real, verified defect is known, applying it and
    re-validating is more honest than another blind model retry).
    golden-work-084 (session evidence, frozen): a real qwen2.5-coder:14b
    reproduced golden-work-083's own exact defect byte-for-byte-similar,
    then exhausted all 4 real `frontend_forms` attempts on the identical
    class -- `frontend/src/index.js` always missing `Route` from its
    existing `{ BrowserRouter as Router }` import -- even once told
    exactly which file and which names. Never patches any other file or
    invents a name this same check did not itself already prove is used
    and missing."""
    patched: dict[str, str] | None = None
    for path, source in stage_files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        repaired_source = _repair_missing_imports_in_source(source)
        if repaired_source is None:
            continue
        if patched is None:
            patched = dict(stage_files)
        patched[path] = repaired_source
    return patched


#: golden-work-085 (session evidence, frozen): `Students/index.js` mounted
#: `<Route path="/students" component={StudentList} exact />`; `StudentList`
#: destructures `{ students }` and calls `students.map(...)` -- react-
#: router's `component=` prop only ever injects `match`/`location`/
#: `history`/`staticContext`, never a custom prop, so `students` is always
#: `undefined` and a real browser threw `TypeError: Cannot read properties
#: of undefined (reading 'map')`, blanking the page on real navigation to
#: `/students`. The identical class recurred in the same file:
#: `<Route path="/students/:id/edit" component={EditStudent} />` with
#: `EditStudent` destructuring `{ studentId }`. No deterministic repair
#: exists for this (unlike a version pin or a missing import, the actual
#: fix is real application logic -- either the routed component fetches
#: its own data, matching `EditStudent`/`DeleteStudent`'s own real pattern
#: elsewhere in this same candidate, or the parent uses `render=` to
#: thread real data through); finding-only, feeding the model concrete
#: instructions.
_ROUTE_COMPONENT_PROP = re.compile(r"<Route\s[^>]*?component=\{(\w+)\}")
_COMPONENT_PROPS_PATTERN = r"(?:const|function)\s+{name}\s*=?\s*\(\s*\{{\s*([^}}]*)\}}"
_STANDARD_ROUTE_INJECTED_PROPS = frozenset({"match", "location", "history", "staticContext"})


def _destructured_param_names(props_block: str) -> set[str]:
    return {
        part.strip().split(":")[0].split("=")[0].strip()
        for part in props_block.split(",") if part.strip()
    }


def _route_component_missing_props_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """A component reached only through `<Route ... component={X} />` can
    never receive a custom prop -- if `X`'s own definition (anywhere in
    the real frontend, not just the file declaring the route) destructures
    one, that prop is always `undefined` at runtime. Runs unconditionally
    (no `product_ux_spec` dependency), the same shape
    `_react_router_missing_import_findings` already uses."""
    all_source = "\n".join(
        source for path, source in files.items()
        if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
    )
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        for route_match in _ROUTE_COMPONENT_PROP.finditer(source):
            component_name = route_match.group(1)
            def_match = re.search(
                _COMPONENT_PROPS_PATTERN.format(name=component_name), all_source,
            )
            if def_match is None:
                continue
            unexpected = sorted(
                _destructured_param_names(def_match.group(1)) - _STANDARD_ROUTE_INJECTED_PROPS
            )
            if unexpected:
                findings.append(SemanticFinding(
                    code="frontend_route_component_missing_props", path=path,
                    detail=(
                        f"<Route component={{{component_name}}}> in {path} never passes "
                        f"custom props, but {component_name} destructures {unexpected!r} -- "
                        "react-router's component= only ever injects match/location/history/"
                        "staticContext. Either make the routed component fetch its own data "
                        "(the same real pattern this candidate's own EditStudent/DeleteStudent "
                        "components already use) or replace component={...} with "
                        "render={props => <Component {...props} ... />} and pass the real data"
                    ),
                ))
    return findings


#: golden-work-086 (session evidence, frozen): `frontend/src/App.js`
#: imported `Courses from './Courses'` and mounted
#: `<Route path="/courses" component={Courses} />`, but no
#: `frontend/src/Courses.js` (or `Courses/index.js`) was ever generated --
#: real `npm run build` failed outright: "Module not found: Error: Can't
#: resolve './Courses'". Syntactically legal JS (`node --check` cannot
#: see it, same class of gap as every other webpack-only build failure
#: this module already exists to catch); only a real module-resolution
#: attempt proves it. Mechanical, not a real bundler: resolves exactly
#: webpack's own default extension/index rules
#: (`X`, `X.js`, `X.jsx`, `X/index.js`, `X/index.jsx`), matched against
#: the real candidate's own declared file set.
_RELATIVE_IMPORT = re.compile(r"""(?:from|require\()\s*['"](\.\.?/[^'"]+)['"]""")


def _relative_import_resolves(importer_path: str, target: str, files: Mapping[str, str]) -> bool:
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(importer_path), target))
    return any(
        candidate in files
        for candidate in (resolved, f"{resolved}.js", f"{resolved}.jsx",
                          f"{resolved}/index.js", f"{resolved}/index.jsx")
    )


def _frontend_local_import_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Every real relative import (`from './X'`/`require('../X')`) in a
    generated frontend file must resolve to a real file this candidate
    actually wrote -- checked per file, since a resolution is always
    relative to the importing file's own real directory, the same
    per-file shape `_react_router_missing_import_findings` already uses.
    Runs unconditionally (no `product_ux_spec` dependency) -- a general
    module-resolution rule, not specific to the staged pipeline."""
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        for match in _RELATIVE_IMPORT.finditer(source):
            target = match.group(1)
            if not _relative_import_resolves(path, target, files):
                findings.append(SemanticFinding(
                    code="frontend_local_import_unresolved", path=path,
                    detail=(
                        f"{path} imports {target!r} but no such file exists anywhere in "
                        "this real candidate -- a real webpack build fails outright with "
                        f"\"Module not found: Error: Can't resolve {target!r}\""
                    ),
                ))
    return findings


