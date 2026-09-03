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

F-0069 (`FRONTEND_FORMS_MULTI_FINDING_CONVERGENCE_GAP`, real repository
evidence: `golden-work-088/089` and, independently, `golden-work-131` --
a real, fresh Task/Work Management attempt, a different family, same
class). The structured-hint escalation above was scoped to exactly one
of `frontend_forms`'s own several real, independently-enforced structural
invariants (callback arity / route-identifier binding). Every OTHER
finding class this stage's own preflight suite enforces -- a declared
parameterized route never reached by any real navigation control, the
application root never resolving to anything, a form missing its own
validation markers, a component calling a client function it never
imports -- retried with nothing beyond the raw `prior_attempt_failure`
string, the exact "resending the identical prompt template on every
retry" shape already named above as the pre-fix callback-arity problem.
`_prior_finding_hint_blocks` extends coverage to those four real,
already-existing finding codes, additively: the original callback-arity
hint text is byte-unchanged, and each new block is built only from real
facts this candidate's own already-computed `SemanticFinding`s already
carry (`code`/`path`/`detail`) paired with one fixed, domain-independent
sentence per code naming WHICH kind of structural invariant needs
restoring -- never a literal repair, never a code snippet, never a
domain-specific example. The real repair decision stays the model's own,
exactly as `mutation_contracts`'s own worked example already leaves the
exact code unstated for every other stage.
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


def _worked_example_from_contracts(mutation_contracts: list[dict[str, object]]) -> str:
    """A real worked example derived from THIS candidate's own real
    `mutation_contracts` -- never a fixed example naming a field or
    function from some other, unrelated domain. A pipeline that must
    generate an inventory or task-management product just as reliably
    as a student/fee one must never see a worked example whose names
    only make sense for a different domain than the one it is actually
    generating."""
    for contract in mutation_contracts:
        actions = contract.get("actions") if isinstance(contract, dict) else None
        edit = actions.get("edit") if isinstance(actions, dict) else None
        if not isinstance(edit, dict):
            continue
        function = edit.get("client_function")
        signature = edit.get("signature")
        route_param = edit.get("route_param")
        if not (function and isinstance(signature, list) and route_param):
            continue
        form_args = [p for p in signature if p != route_param]
        return (
            f"`onSubmit={{async ({', '.join(form_args)}) => {{ const {{ {route_param} }} "
            f"= useParams(); await {function}({', '.join(signature)}); }}}}`"
        )
    return (
        "`onSubmit={async (...formFields) => { const { id } = useParams(); "
        "await updateResource(id, ...formFields); }}`"
    )


#: F-0069. One fixed, domain-independent sentence per real, already-existing
#: `frontend_forms` finding code -- names WHICH structural invariant a real
#: candidate violated, never a literal repair. Deliberately closed and small:
#: only codes this stage's own preflight suite already enforces belong here,
#: never a new check invented to have something to hint about.
_SUPPORTED_HINT_INVARIANTS: dict[str, str] = {
    "frontend_route_unreachable": (
        "a declared parameterized route must be reachable through a real Link, "
        "button, or navigation call somewhere else in the frontend, built from "
        "the same static path prefix the route itself declares"
    ),
    "frontend_root_path_unreachable": (
        "the application's own root path (\"/\") must resolve to a real render "
        "or a real redirect to an existing route -- a router with no route or "
        "redirect matching \"/\" leaves a real user's own base URL blank"
    ),
    "frontend_ui_form_missing_validation": (
        "a rendered form's own required fields must carry real, generated "
        "validation/error semantics -- a visible marker shown for an empty or "
        "invalid required field, not merely present as plain markup"
    ),
    "frontend_client_call_missing_import": (
        "every client function a component's own code calls must be imported "
        "(or otherwise defined) in that same file's own scope -- calling an "
        "undeclared name is a real runtime error, not a syntax error"
    ),
}


def _prior_finding_hint_blocks(prior_findings: tuple[tuple[str, str, str], ...]) -> list[str]:
    """One structured hint block per real, supported finding code the
    previous attempt actually produced (`(code, path, detail)`, the same
    real facts `_generate_one_stage` already computed and would otherwise
    only ever fold into the raw `prior_attempt_failure` string) -- never
    invented, never a repeat of an unsupported code, never more than one
    block for the same code. Each block pairs that real, candidate-owned
    fact with the fixed invariant sentence naming what kind of structural
    fix restores it; the real repair decision stays the model's own."""
    blocks: list[str] = []
    seen_codes: set[str] = set()
    for code, path, detail in prior_findings:
        invariant = _SUPPORTED_HINT_INVARIANTS.get(code)
        if invariant is None or code in seen_codes:
            continue
        seen_codes.add(code)
        blocks.append(f"- {code} ({invariant}). Observed at {path!r}: {detail}")
    return blocks


def _structured_hint_text(
    mutation_contracts: list[dict[str, object]],
    prior_findings: tuple[tuple[str, str, str], ...] = (),
) -> str:
    example = _worked_example_from_contracts(mutation_contracts)
    text = (
        "This is a retry. Do not simply reword the previous attempt -- apply this "
        "exact pattern. For any resource's edit or delete action, the route (not "
        "the form) supplies the record's real identifier: read it as the FIRST "
        "line of the routed component's own function body via "
        "`const { id } = useParams();` (imported from 'react-router-dom'), then "
        "pass it explicitly, in order, to the real client function named in "
        "mutation_contracts. If a form component is shared between create and "
        "edit, wrap the mutation call in a closure that supplies every real "
        "argument explicitly -- for example, derived from this candidate's own "
        f"real edit contract: {example}. NEVER bind a mutation prop directly to "
        "a bare multi-parameter client function reference -- a bare reference "
        "cannot supply the route's own identifier and silently shifts every "
        "other positional argument. A route's own identifier is never a "
        "user-entered form field -- do not render an input for it; "
        "mutation_contracts.form_fields already excludes it."
    )
    blocks = _prior_finding_hint_blocks(prior_findings)
    if blocks:
        text += (
            "\n\nThe previous attempt's own real findings also include the "
            "following -- each names a real structural invariant THIS candidate's "
            "own generated code violates; resolve every one below without "
            "reintroducing any defect already fixed:\n" + "\n".join(blocks)
        )
    return text


def _stage_prompt(
    declaration: StageDeclaration, blueprint: RequirementBlueprint,
    visible_files: Mapping[str, str], prior_failure: str | None,
    target_runtime: str | None = None, repair_strategy: str = _DEFAULT_REPAIR_STRATEGY,
    prior_findings: tuple[tuple[str, str, str], ...] = (),
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
            payload["repair_hint"] = _structured_hint_text(mutation_contracts, prior_findings)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
