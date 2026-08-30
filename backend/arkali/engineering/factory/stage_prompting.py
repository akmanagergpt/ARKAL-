"""Prompt construction for one staged-generation stage.

Owner: `engineering.factory`. Split out of `component_generation.py`
(ADR-0008 decomposition, not a GATE 8 exception): the module was already
at exactly its 400-logical-line ceiling before this session's manifests
dependency-convergence work (anti-loop retry logic, the `target_runtime`
signal below) pushed it over, measured by the real architecture-budget
gate, not assumed — the identical shape `manifest_context.py` was split
out for already. `_generate_one_stage`'s retry loop stays in
`component_generation.py`, since it also needs that module's own
`_StageEnvelope`/`_json_payload`/`_stage_findings`, and pulling those
across too would just move the circular-import problem rather than
solve it; this module owns only prompt construction, which has no such
dependency.

Convergence fix (real repository evidence: golden-work-113/119/122/125,
the identical shared-form-component callback-arity/route-identifier
defect recurring across 4 independent real qwen2.5-coder:14b runs, the
last exhausting all 4 real bounded attempts outright). Two additions:
`mutation_contracts` (`frontend_mutation_contract.py`) gives
`frontend_forms` the exact structured facts -- real client function
signature, route, route-supplied identifier, real user-entered form
fields -- prose guidance already tried twice (after golden-work-113/115
and golden-work-119) and failed to reliably convey a third time.
`repair_strategy` escalates from "default" to "structured_hint" starting
on a stage's own 2nd real attempt, adding an explicit worked example and
a named forbidden pattern, rather than resending the identical prompt
template on every retry with only `prior_attempt_failure`'s text
changed -- confirmed, before this fix, to be the ENTIRE difference
between one attempt's prompt and the next.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from arkali.control.specification.blueprint_contracts import RequirementBlueprint
from arkali.engineering.factory.frontend_mutation_contract import _mutation_contracts_for_stage
from arkali.engineering.factory.generation_stages import StageDeclaration

_DEFAULT_REPAIR_STRATEGY = "default"
_STRUCTURED_HINT_REPAIR_STRATEGY = "structured_hint"


def _repair_strategy_for_attempt(attempt_number: int) -> str:
    """The stage's own 1st real attempt gets the default prompt; every
    retry (2nd attempt onward, i.e. `prior_attempt_failure` is real and
    present) escalates to the structured, worked-example strategy rather
    than resending the identical prompt template with only the failure
    text changed -- confirmed, before this fix, to be the entire
    difference between one real attempt and the next."""
    return _DEFAULT_REPAIR_STRATEGY if attempt_number <= 1 else _STRUCTURED_HINT_REPAIR_STRATEGY


_STRUCTURED_HINT_TEXT = (
    "This is a retry. Do not simply reword the previous attempt -- apply this "
    "exact pattern. For any module's edit or delete action, the route (not the "
    "form) supplies the record's real identifier: read it as the FIRST line of "
    "the routed component's own function body via `const { id } = useParams();` "
    "(imported from 'react-router-dom'), then pass it explicitly, in order, to "
    "the real client function named in mutation_contracts. If a form component "
    "is shared between create and edit, wrap the mutation call in a closure "
    "that supplies every real argument explicitly -- for example: "
    "`onSubmit={async (name, email) => { const { id } = useParams(); "
    "await updateStudent(id, name, email); }}`. NEVER bind a mutation prop "
    "directly to a bare multi-parameter client function reference (for "
    "example `onSubmit={updateStudent}` is always wrong for a shared form "
    "component) -- a bare reference cannot supply the route's own identifier "
    "and silently shifts every other positional argument. A route's own "
    "identifier is never a user-entered form field -- do not render an input "
    "for it; mutation_contracts.form_fields already excludes it."
)


def _stage_prompt(
    declaration: StageDeclaration, blueprint: RequirementBlueprint,
    visible_files: Mapping[str, str], prior_failure: str | None,
    target_runtime: str | None = None, repair_strategy: str = _DEFAULT_REPAIR_STRATEGY,
) -> str:
    payload: dict[str, object] = {
        "role": "You are one bounded stage of a multi-stage software factory.",
        "stage": declaration.name,
        "task": declaration.rule,
        "output_contract": {
            "format": "one JSON object only; no markdown or commentary",
            "schema": {"files": [{"path": "relative/posix/path", "content": "complete text"}]},
            "json_encoding_rule": (
                "Every file content is a JSON string. Escape newlines as \\n and "
                "all other control characters per RFC 8259."
            ),
        },
        "goal": blueprint.goal.goal_text,
        "requirements": [item.statement for item in blueprint.requirements],
        "visible_prior_files": visible_files,
        "prior_attempt_failure": prior_failure,
        "convergence_rule": (
            "When prior_attempt_failure is present, correct that exact defect "
            "while retaining everything else already correct."
        ),
    }
    if target_runtime is not None:
        # golden-work-047 (session evidence, frozen): the model was never
        # told what Python version its declared dependencies had to run
        # on. Mirrors `model_product_generation._prompt`'s existing
        # `target_runtime` field exactly; only the `manifests` stage
        # passes this today, since it is the only stage whose declared
        # rule (STAGED_GENERATION_STAGES.md) depends on it.
        payload["target_runtime"] = {"python": target_runtime}
    mutation_contracts = _mutation_contracts_for_stage(declaration.inputs, visible_files)
    if mutation_contracts:
        payload["mutation_contracts"] = mutation_contracts
        payload["repair_strategy"] = repair_strategy
        if repair_strategy == _STRUCTURED_HINT_REPAIR_STRATEGY:
            payload["repair_hint"] = _STRUCTURED_HINT_TEXT
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
