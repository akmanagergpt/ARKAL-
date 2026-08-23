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
