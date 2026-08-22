"""Structural navigation/reachability checks for a generated frontend.

Owner: `engineering.factory`. Real evidence this session, read directly out
of this repository's own generated-candidate store
(`var/factory/candidates/dershane-demo-003/`): `backend/student_model.json`,
`backend/course_model.json` and `backend/payment_model.json` each declare a
real, distinct "fields" data model, but the entire generated frontend
(`frontend/src/StudentList.js`) is one component rendering one bare `<ul>` of
student names — no navigation element, no route, no form, no control of any
kind reaching the other two backend-declared models. `frontend_ui`'s existing
rule (STAGED_GENERATION_STAGES.md#7) already requires calling every
`frontend_client` export and rendering loading/empty/error states; nothing
before this checked whether more than one backend-declared model was
actually reachable in the rendered UI at all. Every model that stage renders
correctly, in isolation, still lets exactly this candidate through.

DELIBERATELY NARROW, NOT A DESIGN-QUALITY GATE. This checks reachability —
whether a real control exists to reach each backend-declared module — never
visual polish, color, spacing or "professional" appearance; those are
subjective and not machine-verifiable without a canonical authority this
repository has not granted (VDC "Real user journeys" names navigation and
dead controls as browser-automation checks, not a design-quality score).
Only fires when `backend_contract`'s own JSON already declares two or more
distinct data models — a single-module product (e.g. a plain task list) is
never required to show navigation it has nothing to navigate to.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding

_NAVIGATION_MARKERS = (
    "react-router", "<link", "<navlink", "<nav ", "<nav>", "usenavigate",
    "createbrowserrouter", "createhashrouter",
)
_INTERACTIVE_MARKERS = ("<form", "<input", "<button", "<select")


def _declared_backend_model_names(files: Mapping[str, str]) -> set[str]:
    names: set[str] = set()
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".json")):
            continue
        try:
            parsed = json.loads(source)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "fields" in parsed:
            names.add(parsed.get("table_name") or path)
    return names


def _frontend_source_text(files: Mapping[str, str]) -> str:
    return "\n".join(
        source.lower() for path, source in files.items()
        if path.startswith("frontend/src/")
    )


def _unreachable_module_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`frontend_ui`'s multi-module reachability rule.

    Fires only when backend_contract declares two or more distinct data
    models AND the frontend shows no navigation marker AND the frontend
    contains no interactive control (form/input/button/select) — the exact
    shape of `dershane-demo-003`'s real single-`<ul>` output. A product with
    real forms or a real nav bar, even an inelegant one, does not trip this;
    it checks reachability, not aesthetics.
    """
    models = _declared_backend_model_names(files)
    if len(models) < 2:
        return []
    frontend = _frontend_source_text(files)
    if not frontend:
        return []
    has_navigation = any(marker in frontend for marker in _NAVIGATION_MARKERS)
    has_interactive_control = any(marker in frontend for marker in _INTERACTIVE_MARKERS)
    if has_navigation or has_interactive_control:
        return []
    return [SemanticFinding(
        code="frontend_ui_unreachable_modules", path="frontend/src/",
        detail=(
            f"backend_contract declares {len(models)} distinct data models "
            f"({sorted(models)!r}) but the frontend has no navigation "
            "element (react-router, <Link>/<NavLink>, <nav>) and no "
            "interactive control (form/input/button/select) reaching any "
            "of them beyond a single rendered list — a multi-module "
            "product may not ship as one bare list with the rest of the "
            "backend's declared models unreachable"
        ),
    )]


__all__ = ["_unreachable_module_findings"]
