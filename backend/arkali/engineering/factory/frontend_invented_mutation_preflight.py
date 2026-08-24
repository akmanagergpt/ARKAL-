"""Frontend mutation UI must never exceed what product_ux_spec declares.

Owner: `engineering.factory`. golden-work-099 (session evidence, frozen):
golden-work-098's own real backend never implemented a DELETE route for
`/tasks`; `product_ux_spec`'s own new over-declared-action check (see
`product_ux_spec._module_action_findings`) correctly forced this
candidate's spec to declare only `["create", "edit", "view"]` for its
one module -- no "delete" anywhere. `frontend_forms` (whose own stage
rule text conditions every mutation control on "for every module
product_ux_spec declares a 'create'/'edit'/'delete' action for") still
wrote a real `TaskDelete.js` calling a real `deleteTask(id)` on a real
onClick handler anyway, reproducing this exact mistake unchanged across
all 4 real attempts and exhausting the stage's full attempt budget --
`frontend_client_call_preflight._phantom_client_import_findings` (the
first real symptom this produces: `apiClient.js` never exports
`deleteTask`, since `frontend_client` correctly followed the real
backend's own route set) correctly identified the resulting phantom
import, but its own accurate feedback ("this module never exports it")
gives the model no way to know that the REAL fix is to remove the
invented control entirely, not add the missing export -- doing the
latter would just resurface golden-work-098's own already-fixed
over-declared-action defect one layer down.

Lives in its own module rather than `frontend_ux_preflight.py`
(ADR-0008 decomposition, not a GATE 8 exception: that module is already
at its own measured 400-logical-line ceiling).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.product_ux_spec import _parse_ux_spec
from arkali.engineering.factory.semantic_finding import SemanticFinding

#: The same four real mutation verbs `frontend_ux_preflight._MUTATION_
#: EXPORT_NAME` already recognizes as this pipeline's own naming
#: convention (createX/updateX/editX/deleteX) -- captured here, not
#: imported, since a real call site (`deleteTask(id)`) needs a `\b`
#: boundary immediately before the verb (never matching inside
#: `handleDelete`, a real, common wrapper name), a different shape from
#: that module's own export-name extraction.
_MUTATION_CALL = re.compile(r"\b(create|update|edit|delete)([A-Z]\w*)\s*\(")
_VERB_TO_ACTION = {"create": "create", "update": "edit", "edit": "edit", "delete": "delete"}


def _invented_mutation_ui_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Fires only when a real frontend file calls a real mutation-named
    function (`deleteTask(id)`, `createStudent(name)`, ...) for an action
    no module in the real, parsed `product_ux_spec` declares anywhere.
    Silent when no spec exists (the one-shot generation path has no such
    stage) -- the same guard every other spec-dependent check in this
    bounded context already uses. Deliberately whole-spec, not per-module
    (the same coarse tolerance `_unreachable_module_findings` already
    accepts): no real evidence yet shows a multi-module product leaking
    this across modules, only within one."""
    spec, _findings = _parse_ux_spec(files)
    if spec is None:
        return []
    declared_actions = {action for module in spec.modules for action in module.actions}
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        if "client" in path.lower():
            continue
        for match in _MUTATION_CALL.finditer(source):
            verb = match.group(1).lower()
            action = _VERB_TO_ACTION[verb]
            if action in declared_actions:
                continue
            findings.append(SemanticFinding(
                code="frontend_invented_mutation_ui", path=path,
                detail=(
                    f"{path} calls {match.group(0).rstrip('(')!r}(...) -- a real "
                    f"{verb}-prefixed mutation call -- but no module in "
                    f"product_ux_spec declares a {action!r} action anywhere. Remove "
                    "this control/call rather than inventing UI for a capability "
                    "the spec (and the real backend it was reconciled against) "
                    "never asked for"
                ),
            ))
    return findings


def _module_stem(path: str) -> str:
    name = path.rsplit("/", 1)[-1]
    for suffix in (".jsx", ".js"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _strip_component_references(source: str, name: str) -> str:
    """Removes a real `import {name} from './{name}';` line and any real
    `<Route ... component={{{name}}} ... />` (self-closing -- the only
    real shape `component=` routing has ever used this session, since
    `component=` cannot take children) referencing an invented,
    now-removed component. Scoped to exactly the two real reference
    shapes this pipeline's own generated App.js has produced; a
    different reference shape is left untouched rather than guessed at."""
    import_pattern = re.compile(
        rf"""^import\s+{re.escape(name)}\s+from\s+['"]\./{re.escape(name)}['"];?\n?""",
        re.MULTILINE,
    )
    route_pattern = re.compile(
        rf"""[ \t]*<Route\b[^>]*?component=\{{{re.escape(name)}\}}[^>]*/>\n?""",
    )
    return route_pattern.sub("", import_pattern.sub("", source))


def _drop_offending_files_and_references(
    stage_files: Mapping[str, str], offending_paths: set[str],
) -> dict[str, str]:
    """The two mechanical steps once `offending_paths` is known: drop
    those files entirely, then strip every other real frontend file's
    own import/`<Route>` reference to each removed component. Extracted
    from `_repair_invented_mutation_ui` (ADR-0008 decomposition, not a
    GATE 8 exception: that function's own measured complexity exceeded
    its ceiling)."""
    patched = {path: source for path, source in stage_files.items() if path not in offending_paths}
    for offending_path in offending_paths:
        name = _module_stem(offending_path)
        for path, source in list(patched.items()):
            if path.startswith("frontend/src/") and path.endswith((".js", ".jsx")):
                patched[path] = _strip_component_references(source, name)
    return patched


def _repair_invented_mutation_ui(
    merged_files: Mapping[str, str], stage_files: Mapping[str, str],
) -> dict[str, str] | None:
    """Deterministic repair mirroring this pipeline's own Werkzeug<3-style
    repairs (golden-work-050/051's own lesson: once the exact,
    unambiguous fix for a real, verified defect is known, applying it
    and re-validating is more honest than another blind model retry).

    golden-work-099 through golden-work-106 (session evidence, frozen):
    a real qwen2.5-coder:14b reproduced this exact invented-delete-
    control mistake across eight separate real candidates, exhausting
    frontend_forms's full attempt budget every time -- clear, accurate,
    finding-only feedback alone was never enough for it to self-correct.
    Once `_invented_mutation_ui_findings` proves a specific file's own
    mutation call has no ux_spec-declared authorization, that file's
    entire real purpose is invented: dropping it from `stage_files`
    (`frontend_ui` never writes it -- this is exclusively
    `frontend_forms`'s own new output) and stripping the matching
    import/`<Route>` reference any OTHER file in `stage_files` declares
    is the same class of mechanical, unambiguous transform as every
    other repair in this pipeline, not a guess. Checked, not assumed:
    only applied when it actually resolves every real finding, so a
    reference shape this repair does not recognize is left for the
    model rather than silently leaving a dangling import behind."""
    findings = _invented_mutation_ui_findings(merged_files)
    offending_paths = {f.path for f in findings if f.path in stage_files}
    if not offending_paths:
        return None
    patched = _drop_offending_files_and_references(stage_files, offending_paths)
    verification = {k: v for k, v in merged_files.items() if k not in offending_paths}
    verification.update(patched)
    if _invented_mutation_ui_findings(verification):
        return None
    return patched
