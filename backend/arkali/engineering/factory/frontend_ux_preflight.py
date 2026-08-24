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

import re
from collections.abc import Mapping

from arkali.engineering.factory.frontend_manifest_preflight import (
    _frontend_local_import_findings,
    _react_router_missing_import_findings,
    _route_component_missing_props_findings,
)
from arkali.engineering.factory.frontend_root_route_preflight import (
    _missing_root_route_findings,
    _orphaned_router_root_findings,
)
from arkali.engineering.factory.frontend_route_shadowing_preflight import _shadowed_route_findings
from arkali.engineering.factory.semantic_finding import SemanticFinding
from arkali.engineering.factory.product_ux_spec import _backend_declared_models, _parse_ux_spec

_NAVIGATION_MARKERS = (
    "react-router", "<link", "<navlink", "<nav ", "<nav>", "usenavigate",
    "createbrowserrouter", "createhashrouter",
)
_INTERACTIVE_MARKERS = ("<form", "<input", "<button", "<select")
_CONFIRM_MARKERS = ("confirm(", "are you sure", "window.confirm")
#: golden-work-080 (session evidence, frozen): a module declared
#: `"actions": ["create", "edit", "delete", "view"]`, `frontend_client`
#: exported a real `updateStudent`, and the assembled real frontend never
#: referenced it anywhere -- only a create form existed, a real browser
#: session confirmed no edit route/control reached it -- yet
#: `_action_ui_findings`'s own prior rule ("a create/edit action needs
#: *a* `<form>` somewhere") was satisfied vacuously by the create form
#: alone.
_INLINE_EXPORT_PATTERN = re.compile(r"export\s+(?:const|function)\s+(\w+)")
#: golden-work-081 (session evidence, frozen): every real candidate this
#: session's own `frontend_client` output has actually used -- declare
#: every function as a plain top-level `async function name(...)`, then
#: export all of them together in one grouped statement at the bottom of
#: the file (`export { getStudents, createStudent, updateStudent, ... };`)
#: -- never the inline `export function name(...)` shape
#: `_INLINE_EXPORT_PATTERN` alone recognizes. That shape matched zero
#: names on every real candidate this session produced, silently, for
#: both this module's own `_update_like_client_exports` and
#: `component_generation._unused_client_export_findings` (same pattern,
#: reproduced there too) -- neither ever exercised on real output before.
_GROUPED_EXPORT_BLOCK = re.compile(r"export\s*\{([^}]*)\}")
#: golden-work-101 (session evidence, frozen): a real qwen2.5-coder:14b
#: wrote a real, complete, correctly-wired `apiClient.js` using CommonJS
#: (`module.exports = { getTasks, createTask, ... };`), a real pattern a
#: real `npm run build` has already proven compiles cleanly. Neither
#: export regex above recognizes it, so this extractor -- and every
#: check built on it -- silently saw zero exports for any real candidate
#: using this shape.
_COMMONJS_EXPORTS_BLOCK = re.compile(r"module\.exports\s*=\s*\{([^}]*)\}")
_UPDATE_OR_EDIT_NAME = re.compile(r"^(?:update|edit)", re.IGNORECASE)
#: golden-work-082 (session evidence, frozen): STAGED_GENERATION_STAGES.md#8
#: ("the UI calls every function frontend_client exports") and #9
#: ("mutating forms...are not this stage's concern -- that is
#: frontend_forms's job") directly contradicted each other for any real
#: product with mutations. Fixing `_exported_js_names` above made
#: `component_generation._unused_client_export_findings` enforce #8's
#: literal wording for the first time ever (previously silently inert)
#: and immediately exhausted frontend_ui's full attempt budget on every
#: declared create/update/delete export, since frontend_forms genuinely
#: has not run yet at this point. #8's own text is corrected alongside
#: this; a mutation-named export is real evidence's own naming
#: convention (createX/updateX/editX/deleteX), the same evidence
#: `_UPDATE_OR_EDIT_NAME` above already relies on.
_MUTATION_EXPORT_NAME = re.compile(r"^(?:create|update|edit|delete)", re.IGNORECASE)


def _exported_js_names(client_text: str) -> frozenset[str]:
    """Real names a JS/TS file exports, covering every real shape this
    pipeline's own generated `frontend_client` output has used: inline
    (`export function name(...)`/`export const name = ...`), grouped
    (`export { name, other as alias };` -- the local declared name, the
    one actually called or referenced elsewhere in the same file, not
    any renamed alias) and CommonJS (`module.exports = { name, ... };`
    -- golden-work-101, session evidence, frozen)."""
    names = set(_INLINE_EXPORT_PATTERN.findall(client_text))
    for block in _GROUPED_EXPORT_BLOCK.findall(client_text):
        for part in block.split(","):
            local_name = part.strip().split(" as ")[0].strip()
            if local_name:
                names.add(local_name)
    for block in _COMMONJS_EXPORTS_BLOCK.findall(client_text):
        for part in block.split(","):
            name = part.strip().split(":")[0].strip()
            if name:
                names.add(name)
    return frozenset(names)


#: Deliberately excludes "error" -- an async-fetch error state (already
#: required by `_state_coverage_findings`/`_missing_ui_state_findings`) is
#: legitimately present in almost every real component regardless of
#: whether its forms validate anything, which would make this check pass
#: vacuously every time.
_VALIDATION_MARKERS = ("required", "invalid")
#: golden-work-065 (session evidence, frozen): a real qwen2.5-coder:14b
#: implemented a genuine empty-state branch three times over
#: (`students.length === 0 ? <p>No students found</p> : ...`) and every
#: one was a real false positive against a bare `"empty" in text`
#: check — the literal word never appears, only real, more specific
#: phrasing. Loading/error stay single-marker: real output overwhelmingly
#: uses those exact words, and no real evidence yet shows otherwise.
_EMPTY_STATE_MARKERS = ("empty", "no results", "nothing found", ".length === 0", ".length==0")


def _missing_ui_state_findings(ui: str) -> list[SemanticFinding]:
    """Moved from `component_generation.py` (ADR-0008 decomposition, not
    a GATE 8 exception: that module reached its own 400-logical-line
    ceiling, measured live by the real architecture gate, not assumed),
    to sit alongside `_state_coverage_findings`, the other real
    UI-state-completeness check this file already owns. "empty" was
    named in `frontend_ui`'s own rule text (STAGED_GENERATION_STAGES.md#8:
    "renders loading, empty and error states") but never actually
    checked here — a real gap in this check, not the rule, fixed
    alongside this session's wider UX-reconciliation work rather than
    left to drift further from its own rule."""
    lowered = ui.lower()
    missing = [state for state in ("loading", "error") if state not in lowered]
    if not any(marker in lowered for marker in _EMPTY_STATE_MARKERS) and not re.search(
        r"no\s+\w+\s+found", lowered
    ):
        missing.append("empty")
    return [
        SemanticFinding(
            code="frontend_ui_missing_state", path="frontend/src/",
            detail=f"frontend_ui renders no {state!r} state",
        )
        for state in missing
    ]


def _split_client_and_ui(files: Mapping[str, str]) -> tuple[str, str]:
    """A `*client*`-named file versus every other real `frontend/src/*`
    file -- moved here from `component_generation.py` (ADR-0008
    decomposition, not a GATE 8 exception: that module reached its
    400-logical-line ceiling, measured live by the real architecture
    gate, not assumed) to sit alongside every other real check that
    already needs this exact same split (`_frontend_ui_only_text`,
    `_update_like_client_exports`)."""
    client_paths = [
        path for path in files if path.startswith("frontend/src/") and "client" in path.lower()
    ]
    ui_paths = [
        path for path in files if path.startswith("frontend/src/") and "client" not in path.lower()
    ]
    client = "\n".join(files[path] for path in client_paths)
    ui = "\n".join(files[path] for path in ui_paths)
    return client, ui


def _unused_client_export_findings(client: str, ui: str) -> list[SemanticFinding]:
    # golden-work-081 (session evidence, frozen): every real candidate
    # this session's own frontend_client output has actually declared
    # every function as a plain top-level function and exported all of
    # them together in one grouped `export { name, ... };` statement at
    # the file's end -- the inline `export function name(...)` shape a
    # bare regex here originally assumed matched zero real names on every
    # one of them, so this check has been silently vacuous the entire
    # time it has run against real generated output.
    #
    # golden-work-082 (session evidence, frozen): fixing that extraction
    # bug made this check enforce STAGED_GENERATION_STAGES.md#8's literal
    # wording ("the UI calls every function frontend_client exports") for
    # the first time ever, and it immediately exhausted frontend_ui's
    # full attempt budget on every declared create/update/delete export
    # -- wiring those is frontend_forms's job, per #9 and
    # `component_generation._frontend_ui_findings`'s own docstring, and
    # frontend_forms has not run yet at this point. Only a non-mutating
    # (read) export can genuinely be "uncalled" here; #8's own text is
    # corrected alongside this fix.
    exported = _exported_js_names(client)
    read_only_exports = {name for name in exported if not _MUTATION_EXPORT_NAME.match(name)}
    uncalled = sorted(name for name in read_only_exports if name not in ui)
    if not uncalled:
        return []
    return [SemanticFinding(
        code="frontend_ui_client_unused", path="frontend/src/",
        detail=f"frontend_ui never calls client export(s) {uncalled!r}",
    )]


def _frontend_ui_only_text(files: Mapping[str, str]) -> str:
    """Lowercased UI-only source (client files excluded) -- needed because
    a `*client*` file's own function DEFINITION (e.g. `async function
    updateStudent(...)`) would otherwise satisfy a regex looking for a
    real UI-side reference to it."""
    return _split_client_and_ui(files)[1].lower()


def _update_like_client_exports(files: Mapping[str, str]) -> frozenset[str]:
    """Real update/edit-named functions `frontend_client` actually exports
    -- golden-work-081 (session evidence, frozen): a real model reused one
    form component for both create and edit, passing the real exported
    `updateStudent` BY REFERENCE (`<StudentForm onSubmit={updateStudent}
    />`, invoked generically inside `StudentForm` as `onSubmit(...)`)
    rather than calling it directly by name (`updateStudent(...)`) -- a
    real, idiomatic React pattern this check's own first version (a regex
    requiring a literal `(` right after the name) rejected as a false
    positive on the very next real candidate. Matching the real declared
    name itself, the same mechanism `_unused_client_export_findings`
    already uses successfully, is robust to a call, a prop reference, or
    any other real way of using it."""
    client = "\n".join(
        source for path, source in files.items()
        if path.startswith("frontend/src/") and "client" in path.lower()
    )
    return frozenset(
        name for name in _exported_js_names(client)
        if _UPDATE_OR_EDIT_NAME.match(name)
    )


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


def _action_ui_findings(
    spec: object, frontend: str, ui_only: str, update_like_exports: frozenset[str],
) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    needs_mutation_ui = any(
        action in ("create", "edit")
        for module in spec.modules for action in module.actions  # type: ignore[attr-defined]
    )
    if needs_mutation_ui and "<form" not in frontend:
        findings.append(SemanticFinding(
            code="frontend_ui_missing_mutation_ui", path="frontend/src/",
            detail="product_ux_spec declares a create/edit action but the frontend "
                   "contains no <form> anywhere",
        ))
    # golden-work-080 (session evidence, frozen): the check above is
    # satisfied by ANY single `<form>` anywhere, so a module declaring
    # "edit" alongside "create" was silently treated as covered by the
    # create form alone -- a real generated frontend exported a real
    # `updateStudent` from frontend_client and never referenced it from
    # any component; no edit route, button or form existed anywhere,
    # proven in a real browser session. Checked against `ui_only`, never
    # `frontend`: `frontend_client`'s own file defines
    # `function updateStudent(...)`, which would otherwise satisfy a
    # name search on its own definition line, not a real UI-side use.
    needs_edit_ui = any(
        "edit" in module.actions for module in spec.modules  # type: ignore[attr-defined]
    )
    if needs_edit_ui and not any(
        re.search(rf"\b{re.escape(name.lower())}\b", ui_only) for name in update_like_exports
    ):
        findings.append(SemanticFinding(
            code="frontend_ui_missing_edit_ui", path="frontend/src/",
            detail="product_ux_spec declares an edit action but the frontend never "
                   "references an update/edit-named client function anywhere -- a "
                   "create form alone does not satisfy a declared edit action",
        ))
    return findings


def _form_quality_findings(frontend: str) -> list[SemanticFinding]:
    if "<form" not in frontend:
        return []
    findings: list[SemanticFinding] = []
    if "<label" not in frontend and "aria-label=" not in frontend:
        findings.append(SemanticFinding(
            code="frontend_ui_form_missing_labels", path="frontend/src/",
            detail="a <form> exists but the frontend contains no <label> or aria-label",
        ))
    controls = re.findall(r"<(?:input|select|textarea)\b[^>]*>", frontend, re.IGNORECASE)
    label_blocks = re.findall(
        r"<label\b[^>]*>.*?</label>", frontend, re.DOTALL | re.IGNORECASE,
    )
    labelled_ids = set(re.findall(
        r"<label\b[^>]*\b(?:htmlFor|for)=[\"']([^\"']+)[\"']", frontend,
        re.IGNORECASE,
    ))

    def has_accessible_name(control: str) -> bool:
        if re.search(r"\baria-(?:label|labelledby)=[\"'][^\"']+[\"']", control):
            return True
        control_id = re.search(r"\bid=[\"']([^\"']+)[\"']", control)
        if control_id and control_id.group(1) in labelled_ids:
            return True
        return any(control in block for block in label_blocks)

    if controls and any(not has_accessible_name(control) for control in controls):
        findings.append(SemanticFinding(
            code="frontend_ui_form_control_unlabelled", path="frontend/src/",
            detail=(
                "every input/select/textarea must have an accessible name: associate "
                "a label with htmlFor+id, wrap the control in its label, or use a "
                "non-empty aria-label/aria-labelledby; adjacent label text alone is "
                "not exposed as the control's accessible name"
            ),
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


#: golden-work-088 (session evidence, frozen): frontend/src/index.js
#: declared `<Route path="/students/edit/:id" component={EditStudent} />`
#: and `<Route path="/students/delete/:id" component={DeleteStudent} />`
#: -- both real, working forms, confirmed correct by navigating directly
#: to `/students/edit/1` in a real browser -- but App.js's own real
#: student list rendered a bare `<li>{student.name}</li>` with no
#: `<Link>`, button or any other control anywhere in the real frontend
#: pointing at either route's own static path prefix
#: (`/students/edit/`/`/students/delete/`, confirmed absent by a real
#: grep of the whole candidate). product_ux_spec declared
#: `"actions": ["create", "edit", "delete", "view"]` for students; a
#: real end user, using only the rendered UI, could never reach a route
#: that a direct URL proves works. Scoped to the common, real, observed
#: shape where the URL param is the route's OWN LAST segment (`/x/:id`,
#: not `/x/:id/y`) -- the only shape any real candidate this session has
#: produced.
_PARAMETERIZED_ROUTE = re.compile(r"""<Route\s[^>]*?path=["']([^"']*/:[^/"']+)["']""")


def _route_static_prefix(route_path: str) -> str | None:
    param_start = route_path.index(":")
    slash = route_path.rfind("/", 0, param_start)
    return route_path[:slash + 1] if slash >= 0 else None


def _unreachable_parameterized_route_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """A parameterized route's own static prefix must appear somewhere in
    the real frontend beyond its own declaration -- a real templated Link
    target or history.push call built from that same prefix plus a real
    id -- or no real code path anywhere ever constructs a matching URL.
    Runs unconditionally (no `product_ux_spec` dependency), the same
    shape `_shadowed_route_findings` already uses."""
    all_source = "\n".join(
        source for path, source in files.items()
        if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
    )
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        for match in _PARAMETERIZED_ROUTE.finditer(source):
            route_path = match.group(1)
            prefix = _route_static_prefix(route_path)
            if not prefix or all_source.count(prefix) > 1:
                continue
            findings.append(SemanticFinding(
                code="frontend_route_unreachable", path=path,
                detail=(
                    f"<Route path={route_path!r}> in {path} is never reached from "
                    f"anywhere else in the real frontend -- {prefix!r} appears nowhere "
                    "but this exact declaration, so no real Link, button or navigation "
                    "call anywhere ever constructs a matching URL"
                ),
            ))
    return findings


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
    confirmation step before delete, success feedback after a mutation,
    and (unconditionally, with or without a spec) no added route silently
    shadowed by a broader existing one. Split out from the shell checks
    above (golden-work-065, session evidence, frozen) alongside the stage
    split itself — see `STAGED_GENERATION_STAGES.md#9`'s own rule text
    for the real evidence. The spec-dependent checks are silent when no
    spec exists, for the same reason the shell slice is."""
    findings = (
        _shadowed_route_findings(files)
        + _react_router_missing_import_findings(files)
        + _route_component_missing_props_findings(files)
        + _frontend_local_import_findings(files)
        + _unreachable_parameterized_route_findings(files)
        + _missing_root_route_findings(files)
        + _orphaned_router_root_findings(files)
    )
    spec, frontend = _parsed_spec_and_frontend(files)
    if spec is None:
        return findings
    return findings + (
        _action_ui_findings(
            spec, frontend, _frontend_ui_only_text(files), _update_like_client_exports(files),
        )
        + _form_quality_findings(frontend)
        + _state_coverage_findings(spec, frontend)
        + _destructive_confirmation_findings(spec, frontend)
    )


__all__ = ["_unreachable_module_findings", "_ux_spec_shell_findings", "_ux_spec_mutation_findings"]
