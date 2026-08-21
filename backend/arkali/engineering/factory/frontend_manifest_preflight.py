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
without ejecting); no stage's rule or validator had ever required it,
mirroring exactly the same gap class `_manifest_findings`'s existing
`missing_frontend_entry` check already closed for `public/index.html`
under this same react-scripts condition — `index.js` is the other half
of the identical CRA convention.

GENERAL, NOT GOLDEN-SPECIFIC. Both checks look at the real, parsed JSON
structure or the real declared file set — never any specific script
command text, component name or app name.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding

_REQUIRED_SCRIPTS = ("start", "build")


def _missing_frontend_scripts_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    package_json = files.get("frontend/package.json", "")
    if "react-scripts" not in package_json:
        return []
    try:
        parsed = json.loads(package_json)
    except json.JSONDecodeError:
        return []  # a real JSON-syntax finding belongs to a different check
    scripts = parsed.get("scripts") if isinstance(parsed, dict) else None
    scripts = scripts if isinstance(scripts, dict) else {}
    missing = [name for name in _REQUIRED_SCRIPTS if not scripts.get(name)]
    if not missing:
        return []
    return [SemanticFinding(
        code="missing_frontend_runnable_scripts", path="frontend/package.json",
        detail=(
            f"react-scripts is declared but package.json's scripts object is "
            f"missing {missing!r} — react-scripts requires "
            "'\"scripts\": {\"start\": \"react-scripts start\", "
            "\"build\": \"react-scripts build\"}' (or equivalent) to be runnable"
        ),
    )]


def _missing_frontend_entry_point_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    package_json = files.get("frontend/package.json", "")
    if "react-scripts" not in package_json or "frontend/src/index.js" in files:
        return []
    return [SemanticFinding(
        code="missing_frontend_entry_point", path="frontend/src/index.js",
        detail=(
            "react-scripts is declared but frontend/src/index.js does not "
            "exist — react-scripts build hard-codes this exact path as its "
            "webpack entry point and fails outright without it"
        ),
    )]
