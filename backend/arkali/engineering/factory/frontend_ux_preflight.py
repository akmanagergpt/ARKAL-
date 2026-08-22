"""Structural navigation/reachability checks for a generated frontend.

Owner: `engineering.factory`. Two independent layers, both real evidence:

`_unreachable_module_findings` is real evidence this session, read directly
out of this repository's own generated-candidate store
(`var/factory/candidates/dershane-demo-003/`): `backend/student_model.json`,
`backend/course_model.json` and `backend/payment_model.json` each declare a
real, distinct "fields" data model, but the entire generated frontend
(`frontend/src/StudentList.js`) is one component rendering one bare `<ul>` of
student names — no navigation element, no route, no form, no control of any
kind reaching the other two backend-declared models. It needs nothing but
`backend_contract`'s own JSON, so it runs on every candidate regardless of
which generation path produced it (staged or one-shot).

`_ux_spec_shell_findings` and `_ux_spec_mutation_findings` are the deeper,
real `product_ux_spec` reconciliation, split along the same seam
`frontend_ui`/`frontend_forms` are split along (golden-work-065, session
evidence, frozen — see `STAGED_GENERATION_STAGES.md#9`): the shell slice
checks every declared navigation destination is reachable and no raw JSON
is dumped as primary content; the mutation slice checks every declared
create/edit action has real, labelled, validated form UI, a declared
delete action is confirmed before it fires, and a mutation leaves visible
success feedback. Both are silent (no findings, never a `ux_spec_missing`
failure) when no `product/ux_spec.json` exists — the one-shot generation
path (`model_product_generation.py`) has no such stage and must not be
penalized for a stage it never runs; `product_ux_spec`'s own stage
validator, not this whole-product-gate layer, is what refuses a missing
or invalid spec on the staged path.

DELIBERATELY NARROW, NOT A DESIGN-QUALITY GATE. Both layers check
reachability and structural completeness — whether a real control exists to
reach each declared destination, whether a declared action has real UI,
whether a state is present — never visual polish, color, spacing or
"professional" appearance; those are subjective and not machine-verifiable
without a canonical authority this repository has not granted (VDC "Real
user journeys" names navigation and dead controls as browser-automation
checks, not a design-quality score).
"""

from __future__ import annotations

from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding
from arkali.engineering.factory.product_ux_spec import _backend_declared_models, _parse_ux_spec

_NAVIGATION_MARKERS = (
    "react-router", "<link", "<navlink", "<nav ", "<nav>", "usenavigate",
    "createbrowserrouter", "createhashrouter",
)
_INTERACTIVE_MARKERS = ("<form", "<input", "<button", "<select")
_CONFIRM_MARKERS = ("confirm(", "are you sure", "window.confirm")
#: Deliberately excludes "error" -- an async-fetch error state (already
#: required by `_state_coverage_findings`/`_missing_ui_state_findings`) is
#: legitimately present in almost every real component regardless of
#: whether its forms validate anything, which would make this check pass
#: vacuously every time.
_VALIDATION_MARKERS = ("required", "invalid")


def _frontend_source_text(files: Mapping[str, str]) -> str:
    return "\n".join(
        source.lower() for path, source in files.items()
        if path.startswith("frontend/src/")
    )


def _unreachable_module_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`frontend_ui`'s multi-module reachability backstop.

    Fires only when backend_contract declares two or more distinct models
    AND the frontend shows no navigation marker AND the frontend contains no
    interactive control (form/input/button/select) — the exact shape of
    `dershane-demo-003`'s real single-`<ul>` output. Runs unconditionally,
    with or without a `product_ux_spec` artifact, since it needs nothing but
    `backend_contract`'s own JSON.
    """
    models = _backend_declared_models(files)
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


def _navigation_reconciliation_findings(spec: object, frontend: str) -> list[SemanticFinding]:
    labels = [module.navigation_label for module in spec.modules]  # type: ignore[attr-defined]
    if spec.dashboard is not None:  # type: ignore[attr-defined]
        labels.append(spec.dashboard.navigation_label)  # type: ignore[attr-defined]
    unreachable = sorted({label for label in labels if label.lower() not in frontend})
    if not unreachable:
        return []
    return [SemanticFinding(
        code="frontend_ui_navigation_destination_unreachable", path="frontend/src/",
        detail=(
            f"product_ux_spec declares navigation destination(s) {unreachable!r} "
            "with no matching text anywhere in the rendered frontend"
        ),
    )]


def _action_ui_findings(spec: object, frontend: str) -> list[SemanticFinding]:
    needs_mutation_ui = any(
        action in ("create", "edit")
        for module in spec.modules for action in module.actions  # type: ignore[attr-defined]
    )
    if needs_mutation_ui and "<form" not in frontend:
        return [SemanticFinding(
            code="frontend_ui_missing_mutation_ui", path="frontend/src/",
            detail="product_ux_spec declares a create/edit action but the frontend "
                   "contains no <form> anywhere",
        )]
    return []


def _form_quality_findings(frontend: str) -> list[SemanticFinding]:
    if "<form" not in frontend:
        return []
    findings: list[SemanticFinding] = []
    if "<label" not in frontend and "aria-label=" not in frontend:
        findings.append(SemanticFinding(
            code="frontend_ui_form_missing_labels", path="frontend/src/",
            detail="a <form> exists but the frontend contains no <label> or aria-label",
        ))
    if not any(marker in frontend for marker in _VALIDATION_MARKERS):
        findings.append(SemanticFinding(
            code="frontend_ui_form_missing_validation", path="frontend/src/",
            detail="a <form> exists but the frontend shows no required/error/invalid "
                   "validation marker",
        ))
    return findings


def _state_coverage_findings(spec: object, frontend: str) -> list[SemanticFinding]:
    needs_success = any(
        action in ("create", "edit", "delete")
        for module in spec.modules for action in module.actions  # type: ignore[attr-defined]
    )
    if not needs_success or "success" in frontend:
        return []
    return [SemanticFinding(
        code="frontend_ui_missing_success_feedback", path="frontend/src/",
        detail="product_ux_spec declares a mutating action but the frontend shows no "
               "success/feedback marker after it",
    )]


def _destructive_confirmation_findings(spec: object, frontend: str) -> list[SemanticFinding]:
    needs_confirmation = spec.destructive_action_confirmation and any(  # type: ignore[attr-defined]
        "delete" in module.actions for module in spec.modules  # type: ignore[attr-defined]
    )
    if not needs_confirmation or any(marker in frontend for marker in _CONFIRM_MARKERS):
        return []
    return [SemanticFinding(
        code="frontend_ui_missing_destructive_confirmation", path="frontend/src/",
        detail="product_ux_spec requires destructive-action confirmation and a module "
               "declares a delete action, but the frontend shows no confirmation marker",
    )]


def _raw_json_dump_findings(frontend: str) -> list[SemanticFinding]:
    if "{json.stringify(" not in frontend:
        return []
    return [SemanticFinding(
        code="frontend_ui_raw_json_primary_content", path="frontend/src/",
        detail="frontend renders {JSON.stringify(...)} directly in JSX -- raw JSON is "
               "not a primary UI",
    )]


def _parsed_spec_and_frontend(files: Mapping[str, str]) -> tuple[object, str] | tuple[None, None]:
    spec, _parse_findings = _parse_ux_spec(files)
    frontend = _frontend_source_text(files)
    if spec is None or not frontend:
        return None, None
    return spec, frontend


def _ux_spec_shell_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`frontend_ui`'s own reconciliation slice: navigation reachability and
    no-raw-JSON, never the mutation-UI concerns `frontend_forms` owns.
    Silent when no spec exists — this is not the layer that refuses a
    missing/invalid spec (`product_ux_spec._ux_spec_stage_findings` is), so
    a candidate from a pipeline with no such stage is never penalized
    here."""
    spec, frontend = _parsed_spec_and_frontend(files)
    if spec is None:
        return []
    return _navigation_reconciliation_findings(spec, frontend) + _raw_json_dump_findings(frontend)


def _ux_spec_mutation_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`frontend_forms`'s own reconciliation slice: real mutation UI for
    every declared create/edit action, labelled and validated, a
    confirmation step before delete, and success feedback after a
    mutation. Split out from the shell checks above (golden-work-065,
    session evidence, frozen) alongside the stage split itself — see
    `STAGED_GENERATION_STAGES.md#9`'s own rule text for the real evidence.
    Silent when no spec exists, for the same reason the shell slice is."""
    spec, frontend = _parsed_spec_and_frontend(files)
    if spec is None:
        return []
    return (
        _action_ui_findings(spec, frontend)
        + _form_quality_findings(frontend)
        + _state_coverage_findings(spec, frontend)
        + _destructive_confirmation_findings(spec, frontend)
    )


__all__ = ["_unreachable_module_findings", "_ux_spec_shell_findings", "_ux_spec_mutation_findings"]
