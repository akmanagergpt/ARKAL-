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
