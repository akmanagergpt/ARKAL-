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
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding

_REQUIRED_SCRIPTS = ("start", "build")


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
