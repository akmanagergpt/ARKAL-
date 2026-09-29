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
    "frontend_ui_missing_destructive_confirmation": (
        "for each module with a delete action, put a reachable delete control "
        "on its rendered record/list surface and require a real user "
        "confirmation before invoking the delete client function. If the "
        "existing list component owns the delete button, modify that file; "
        "an unrelated route or an unused confirmation helper is insufficient"
    ),
    "test_hardcoded_created_id": (
        "after a test creates a row, capture the create response and use its "
        "returned id for every read, update or delete of that row in the "
        "same test. Never assume a literal id such as 1: AUTOINCREMENT can "
        "advance even if a setup fixture deletes all prior rows"
    ),
    "test_database_state_leaks_between_cases": (
        "isolate the file-backed database independently per test: use a "
        "temporary database path wired into the real application before "
        "each test runs, or perform reliable cleanup/rollback between tests. "
        "Make every mutating test independent of execution order; merely "
        "repeating schema initialization does not remove prior rows. Merely "
        "importing tempfile/os is not isolation: the fixture must actually "
        "create and use the temporary path or execute cleanup/rollback"
    ),
    "test_database_path_mismatch": (
        "when a test verifies persisted rows with sqlite3.connect, connect to the exact "
        "database path the application under test uses, or explicitly override the "
        "application's database path before creating its client. Initializing and "
        "inspecting a separate test database does not verify the application's writes"
    ),
    "python_syntax": (
        "the emitted Python file is incomplete or syntactically invalid. Repair "
        "the exact parser-reported location in the previous attempt, completing "
        "every opened string, bracket, call, and statement, then return the whole "
        "valid file rather than repeating or continuing the broken fragment"
    ),
    #: BACKEND_IMPLEMENTATION_LOCAL_FILE_COMPLETENESS_GAP (real evidence:
    #: `factory-ea9cba11-89be-4b41-895f-5ea0069b495b`, `missing_api_routes`,
    #: ARK-ERR-0116 exhausted, session evidence, frozen). The real checker
    #: fires correctly -- the emitted backend source contains no resolvable
    #: route declaration -- but had no entry here, so a retry received only
    #: the raw finding text and the generic "make the minimal edit"
    #: convergence rule, never an explicit repair action; the same two
    #: dangling Blueprint imports (`backend/routes/members.py`,
    #: `backend/routes/classes.py`, both referenced by `app.py`, neither
    #: ever emitted) survived all 4 real attempts. This is the identical
    #: structural gap `frontend_local_import_unresolved` already names for
    #: frontend local imports, restated here for backend Python local
    #: imports; `STAGED_GENERATION_STAGES.md#3`'s own rule now states this
    #: same invariant at generation time, this hint restates it only for a
    #: retry that already violated it.
    "missing_api_routes": (
        "the emitted backend source declares no HTTP route the real checker "
        "can resolve. This can happen because no route exists yet, or "
        "because real routes exist only in a separate local Python module "
        "(for example a Flask Blueprint file) that the application file "
        "imports but this response never emitted. Repair by doing exactly "
        "one of: emit every such locally-imported route module, with real, "
        "working route-decorated implementation content, in this same "
        "response; or remove that import and instead declare those routes "
        "directly on the application instance in the same file. Never leave "
        "the import in place while assuming a later stage or a future "
        "attempt will create the missing module -- no later stage re-emits "
        "backend_implementation's own files"
    ),
    #: F-0099 recurrence (real evidence: `factory-goal-mtzkvowr-998jly`,
    #: `frontend_route_unreachable` x4, ARK-ERR-0116 exhausted). This hint
    #: already existed and was already delivered; the recurrence traced to
    #: real generated `CustomerList.js`/`TicketList.js`-shaped components
    #: (names withheld here deliberately -- domain-independent) rendering
    #: only bare `<li>{record.field}</li>` with zero interactive elements,
    #: while the model's own retry output added new files (routes, forms)
    #: without ever touching that existing list component -- even though
    #: `STAGED_GENERATION_STAGES.md#9` already names this exact required
    #: edit (golden-work-088/089). The wording below now names the
    #: existing list/item surface as the relevant place to fix, explicitly
    #: states that route/App.js/form-only changes do not resolve this
    #: while that surface stays unreachable, and directs a retry to modify
    #: that existing component when the gap is there -- never a stricter
    #: DOM shape, button text, or route string requirement.
    "frontend_route_unreachable": (
        "a declared parameterized route must be reachable through a real Link, "
        "button, or navigation call somewhere else in the frontend, built from "
        "the same static path prefix the route itself declares -- a declared "
        "route alone is never sufficient. The relevant place to add this is "
        "the resource's own existing rendered list/item surface: each record "
        "shown there must expose a real, accessible edit and/or delete action "
        "associated with that specific record, built from that record's own "
        "real id. Changing only the route declarations, App.js, or a form "
        "component does not resolve this finding while the existing list/item "
        "component still renders no reachable action for any record -- if the "
        "reachability gap is in that existing component, modify that existing "
        "component; adding the action anywhere else does not fix it. No exact "
        "button text, route string, DOM shape, or styling is required -- what "
        "matters is that a real, accessible path from the rendered list to "
        "that route exists"
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
    #: F-0097 (`BACKEND_CONTRACT_MULTI_MODEL_CONVERGENCE_GAP`, real evidence:
    #: `factory-goal-mtw5byq6-irjabg` -- two otherwise-complete model
    #: objects wrapped in one top-level JSON array) and F-0098 (`BACKEND_
    #: CONTRACT_MULTI_MODEL_KEY_CONVENTION_GAP`, real evidence: `factory-
    #: goal-mtxqltea-oatre4` -- two otherwise-complete model objects keyed
    #: directly by their own names at the top level), both the identical
    #: structural fingerprint on both permitted attempts, both real
    #: evidence that PROSE ALONE describing the legal shape is not
    #: sufficient: F-0098's own real failure reproduced a literal reading
    #: of this very hint's own pre-F-0098 wording ("nest every model's own
    #: fields under that model's own key") as "the model's OWN NAME becomes
    #: a top-level key" rather than the intended "under a literal top-level
    #: `fields` key" -- a real, self-diagnosed ambiguity, not model
    #: unreliability. This hint now states one canonical target only (one
    #: file per model, `STAGED_GENERATION_STAGES.md#1`'s own new-generation
    #: rule) with a literal worked example, and names both rejected shapes
    #: explicitly and literally rather than describing them in words a
    #: retry could reasonably misread.
    "backend_contract_no_models": (
        "produce ONE JSON FILE PER MODEL, never a single combined file -- "
        "for two models, write two separate files, each its own top-level "
        "OBJECT carrying real \"table_name\"/\"fields\" content, for "
        "example one file as {\"table_name\": \"members\", \"fields\": "
        "{...}} and a second, separate file as {\"table_name\": "
        "\"trainers\", \"fields\": {...}}. Never a top-level ARRAY "
        "([{...}, {...}]). Never a top-level object keyed directly by "
        "each model's own name ({\"members\": {...}, \"trainers\": "
        "{...}}). Preserve every real field and table_name already "
        "written; correct only which file(s) they live in and each "
        "file's own top-level shape"
    ),
    #: F-0099 (`FRONTEND_FORMS_LIST_LINK_WIRING_CONVERGENCE_GAP`, real
    #: evidence: `factory-goal-mty4pvfe-vxppwp`). Wave B's own new
    #: `frontend_ui_create_unreachable_from_empty_state` check (`_create_
    #: access_findings`) fires correctly -- a module declares "create" but
    #: no interactive create control remains reachable once the collection
    #: is empty -- but had no entry here, so a retry sharing this exact
    #: fingerprint with the already-hinted `frontend_route_unreachable`
    #: findings above received guidance for those two but nothing for this
    #: third, simultaneous one. Never a literal repair, never a required
    #: label -- `STAGED_GENERATION_STAGES.md#9`'s own rule already states
    #: this same invariant at generation time; this hint restates it only
    #: for a retry that already violated it.
    #: F-0099 recurrence (real evidence: `factory-goal-mtzkvowr-998jly`,
    #: `frontend_ui_create_unreachable_from_empty_state` x2, same run as
    #: the `frontend_route_unreachable` recurrence above). Real generated
    #: list components' own empty-state branches rendered only static text
    #: with zero controls, and the retry never touched those existing
    #: components. Extended below to name the existing list/empty-state
    #: component as the place to fix when it owns that branch, and to
    #: state explicitly that a route declared elsewhere, or a control
    #: reachable only once records exist, does not resolve this.
    "frontend_ui_create_unreachable_from_empty_state": (
        "a module that declares create must expose a real, accessible "
        "interactive control that lets a user start creating a new item "
        "for that module, and that control must remain reachable even "
        "when the collection currently holds zero records -- a toolbar "
        "action, a page-level primary action, and an empty-state "
        "call-to-action are all real, legal choices. Never render the "
        "only such control inside a map/list of existing items, since it "
        "then disappears exactly when the collection is empty and the "
        "control is needed most. If the module's own existing list/"
        "collection component owns the branch that renders when there are "
        "zero records, that existing component is where the reachable "
        "control is missing and must be modified -- declaring a create "
        "route elsewhere, or leaving the control reachable only once "
        "records already exist, does not resolve this finding. Preserve "
        "the existing list's own already-correct loading/error/populated-"
        "state rendering while adding the missing reachable action. No "
        "specific label, wording, or styling is required -- what matters "
        "is that the control exists in the rendered output and stays "
        "reachable independent of how many records the collection holds"
    ),
    #: F-0101B (`FRONTEND_UI_EDIT_EXPORT_MISDETECTION_AND_LABEL_HINT_GAP`,
    #: real evidence: `factory-goal-mtz6bst2-myhr15`). Every generated
    #: form control had a real, visible `<label>` immediately next to it,
    #: but never associated by any mechanism a screen reader recognizes --
    #: `STAGED_GENERATION_STAGES.md#9`'s own rule already says "labelled",
    #: which the model satisfied literally (a label exists) without
    #: satisfying what the real checker requires (the label is exposed as
    #: the control's own accessible name). No exact wording or one single
    #: mechanism is prescribed; any real association the checker already
    #: accepts is a legal fix.
    "frontend_ui_form_control_unlabelled": (
        "every real input, select, or textarea must have a real accessible "
        "name a screen reader can expose -- visible adjacent label text "
        "alone, with no programmatic association, does not count. Any of "
        "the following real, legal mechanisms is enough: a `<label "
        "htmlFor=\"x\">` paired with a matching `id=\"x\"` on the control; "
        "wrapping the control directly inside its own `<label>` element; "
        "or a non-empty `aria-label`/`aria-labelledby` on the control "
        "itself. Fix the association, not the visible wording -- no "
        "specific label text or styling is required"
    ),
    #: FRONTEND_FORMS_LOCAL_COMPONENT_COMPLETENESS_GAP (real evidence:
    #: `factory-goal-mu1oieg4-3bye3k`, `frontend_local_import_unresolved`
    #: x2, ARK-ERR-0116 exhausted, session evidence, frozen). The real
    #: checker fires correctly -- this stage's own generated code imports
    #: a local file that does not exist anywhere in the candidate -- but
    #: had no entry here, so a retry received only the raw finding text
    #: and the generic "make the minimal edit" convergence rule, never an
    #: explicit repair action; the same two dangling imports survived all
    #: 4 real attempts. `STAGED_GENERATION_STAGES.md#9`'s own rule already
    #: states this same invariant at generation time; this hint restates
    #: it only for a retry that already violated it.
    "frontend_local_import_unresolved": (
        "a relative import in a generated frontend file does not resolve "
        "to any real file in this candidate. Repair by doing exactly one "
        "of: emit the missing imported local file, with real, working "
        "implementation content, in this same response; or remove that "
        "import and instead keep the implementation inline in the "
        "importing file, or reuse an already-existing local file that "
        "already resolves. Never leave the import in place while assuming "
        "a later stage or a future attempt will create the missing file -- "
        "no later stage re-emits this stage's own frontend files. After "
        "making this change, every other real local relative import in "
        "every emitted frontend file must still resolve"
    ),
    "frontend_import_binding_redeclared": (
        "a generated file imports a binding and also declares that same name in its module scope. "
        "Keep exactly one implementation: retain the real import and remove the duplicate inline "
        "declaration, or retain the inline implementation and remove its conflicting import. "
        "Do not leave duplicate imports of the same local name. Preserve working references and "
        "all other required imports; a nested scope may legally shadow an imported name"
    ),
    #: FRONTEND_SUCCESS_FEEDBACK_RETRY_HINT_GAP (real evidence: `factory-
    #: goal-mu2h4fda-yyz4hh`, ARK-ERR-0116 exhausted, session evidence,
    #: frozen). The real checker fires correctly -- a real create/update/
    #: delete call genuinely resolves and nothing in the rendered frontend
    #: ever changes afterward, for either real mutating module, on all 4
    #: real attempts -- but had no entry here, so a retry received only
    #: the raw finding text and the generic mutation-contracts callback-
    #: arity hint (a real, unrelated concern this candidate's own routes
    #: already satisfied). `STAGED_GENERATION_STAGES.md#9`'s own rule
    #: already states this same invariant ("add a visible success/
    #: feedback marker after a mutation completes") at generation time;
    #: this hint restates it only for a retry that already violated it.
    "frontend_ui_missing_success_feedback": (
        "product_ux_spec declares a mutating action, but the frontend "
        "shows no visible marker confirming a mutation actually "
        "succeeded. After a real create/update/delete call genuinely "
        "resolves, render a real, visible confirmation to the user -- in "
        "the form itself or in the parent component that owns the "
        "mutation, whichever already renders once that call resolves. "
        "Show it only once the mutation has genuinely succeeded, never "
        "before it resolves and never on a failed attempt -- existing "
        "error-state handling stays exactly as it is; a real error "
        "marker is never itself a success marker. No specific wording, "
        "library, modal, redirect, or component structure is required -- "
        "what matters is that a real user, after a real successful "
        "mutation, sees something that was not there before it succeeded"
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
    blocks = _prior_finding_hint_blocks(prior_findings)
    if not mutation_contracts:
        # F-0097. A stage with no real frontend mutation concern at all
        # (e.g. `backend_contract`, stage 1 -- `_mutation_contracts_for_
        # stage` returns `None` for any stage that does not declare both
        # `product_ux_spec` and `frontend_client` as real inputs) has no
        # real edit/delete route-identifier pattern to work an example
        # from; the worked-example preamble below names react-router/
        # useParams concepts that would misdirect a JSON-shape defect this
        # early in the pipeline. Only the real, code-specific structural-
        # finding blocks apply here -- never the mutation-specific example.
        return (
            "This is a retry. Do not simply reword the previous attempt -- "
            "resolve the exact structural invariant(s) below without "
            "reintroducing any defect already fixed:\n" + "\n".join(blocks)
        )
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
    previous_attempt_files: Mapping[str, str] | None = None,
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
