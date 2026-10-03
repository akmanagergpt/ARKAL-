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
from arkali.engineering.factory.stage_repair_hints import (
    _SUPPORTED_HINT_INVARIANTS,
    _prior_finding_hint_blocks,
    _structured_hint_text,
)
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




def _stage_prompt(
    declaration: StageDeclaration, blueprint: RequirementBlueprint,
    visible_files: Mapping[str, str], prior_failure: str | None,
    target_runtime: str | None = None, repair_strategy: str = _DEFAULT_REPAIR_STRATEGY,
    prior_findings: tuple[tuple[str, str, str], ...] = (),
    previous_attempt_files: Mapping[str, str] | None = None,
    unit_scope: str | None = None,
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
    if previous_attempt_files:
        # FACTORY RELIABILITY CONVERGENCE. The exact bytes this stage itself
        # wrote on its immediately-prior parseable attempt -- never the
        # declared-input files above, never a paraphrase. Without this, a
        # location- or name-anchored `prior_attempt_failure` (e.g. "line 42:
        # unterminated string literal", or "invented module ['book_id']")
        # named a place in a file the model could no longer see, since its
        # own prior output was discarded every retry.
        payload["previous_attempt_output"] = dict(previous_attempt_files)
        payload["convergence_rule"] = (
            "previous_attempt_output is the exact content you wrote on your "
            "immediately-prior attempt for THIS stage. prior_attempt_failure "
            "names the exact defect a real, mechanical check found in it. "
            "Start from previous_attempt_output, make the minimal edit that "
            "resolves prior_attempt_failure at the exact location/name it "
            "names, and retain everything else already correct -- do not "
            "regenerate unrelated content from scratch, and do not repeat "
            "the same wrong value again."
        )
    if unit_scope is not None:
        # FRONTEND_FORMS_OUTPUT_BOUNDARY (real evidence: `factory-garden-
        # 1790744835`, `finish_reason: "length"` at exactly the shared
        # output-token ceiling). One bounded call now covers one
        # product_ux_spec-declared module at a time; this additive field
        # is the only real difference from an unscoped call to this same
        # stage -- 'task' below still states every other requirement.
        payload["generation_scope"] = (
            f"Generate real, complete mutation UI ONLY for the {unit_scope!r} module "
            "named in product_ux_spec; other modules' own forms are generated "
            "separately and must not be touched here -- every other requirement in "
            "'task' still applies fully to this module's own forms."
        )
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
    #: F-0097. `mutation_contracts` is `None` for any stage with no real
    #: frontend mutation concern at all (e.g. `backend_contract`, stage 1)
    #: -- before this fix, such a stage could never receive `repair_
    #: strategy`/`repair_hint` at all, regardless of `_SUPPORTED_HINT_
    #: INVARIANTS`'s own contents, since both were nested entirely inside
    #: `if mutation_contracts:` above. A stage with real, supported prior
    #: findings but no mutation contract now still escalates and receives
    #: its own structural-finding hint (via `_structured_hint_text`'s own
    #: no-mutation-contracts branch) -- additive only: every stage that
    #: already had `mutation_contracts` keeps the exact same payload it
    #: always did.
    has_supported_findings = bool(_prior_finding_hint_blocks(prior_findings))
    if mutation_contracts or (
        repair_strategy == _STRUCTURED_HINT_REPAIR_STRATEGY and has_supported_findings
    ):
        payload["repair_strategy"] = repair_strategy
        if repair_strategy == _STRUCTURED_HINT_REPAIR_STRATEGY:
            payload["repair_hint"] = _structured_hint_text(mutation_contracts or [], prior_findings)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
