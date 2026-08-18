"""Whether an evolution campaign's own evidence record is bounded enough to
trust its outcome (VDC "ARKALI Self-Evolution": "An evolution run without a
bounded campaign record is FAIL") - ARK-REQ-0360.

Owner: `acceptance.engine` (Protected Core).

OPERATES ON PRIMITIVE FACTS ONLY, NEVER A `lifecycle.evolution` IMPORT.
`acceptance.engine` is `evidence` layer; `lifecycle.evolution` is `lifecycle`
layer, a later rank. Importing it here would be an upward edge
`AUTHORITY_MAP.yaml` forbids. This checks the same shape
`CampaignDeclaration`/`CampaignLedger` render into their own C-14 evidence
artifacts (`.rendering()` -> JSON), read back as plain mappings - the
identical "primitive facts only" discipline `RollbackAuthorization`/
`EvidenceSink` already use for the same layer-direction problem.

WHAT THIS DECIDES, AND WHAT IT DOES NOT. It decides only whether a campaign
record's *shape* is complete enough to be trusted - VDC's own enumerated
fields (objective, baseline metrics, all six declared budgets, a genuine
terminal state). Whether the campaign's outcome was itself correct is not
this module's question, the same boundary `discharge_shape.check_claim_shape`
draws for traceability records.

WHY THE CHECK IS PRIVATE. `acceptance.engine`'s `max_public_surface_per_
context` budget (40) was already at its ceiling; a public function here has
no real caller yet either way - no phase before the mechanism this checks
(Phase 23 itself, building it) has a live campaign-acceptance path to
consult it from, and Phase 23's own phase-gate report claims no live
campaign run. `checker.py` gains a public caller for this the same day a
real campaign-outcome acceptance path is built, not before - matching this
codebase's own "no premature surface" discipline.
"""

from __future__ import annotations

from collections.abc import Mapping

#: The six MS "ARKALI Self-Evolution" budgets, restated here as plain
#: strings - never imported from `lifecycle.evolution.campaign_declaration.
#: CampaignBudgets`, which this layer cannot reach.
#: `test_campaign_record_shape.py` asserts this set is identical to that
#: context's own `model_fields`, so the two cannot silently diverge.
REQUIRED_BUDGET_NAMES = frozenset({
    "candidate_budget", "ai_call_budget", "time_budget_seconds",
    "cost_budget", "regression_ceiling", "no_progress_threshold",
})

#: The four terminal states `STATE_MACHINES.md` §10 declares for
#: `EvolutionCampaign`. Restated for the same reason as the budget names.
TERMINAL_STATES = frozenset({
    "PROMOTED", "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN", "ESCALATED", "BLOCKED",
})

#: Returned as (summary, detail) when the shape is refused; None when permitted.
ShapeRefusal = tuple[str, str]


def _check_campaign_record_shape(
    declaration: Mapping[str, object], outcome: Mapping[str, object],
) -> ShapeRefusal | None:
    """Refuse an evolution run's outcome unless its campaign record proves
    bounded. `declaration` and `outcome` are plain mappings - the JSON shape
    a real `CampaignDeclaration`/campaign-ledger evidence artifact renders,
    never a caller-fabricated claim this module could not detect."""
    if not declaration.get("objective"):
        return (
            "campaign record declares no objective",
            "objective missing or empty",
        )
    if not declaration.get("baseline_metrics"):
        return (
            "campaign record declares no baseline metrics",
            "baseline_metrics missing or empty",
        )
    budgets = declaration.get("budgets")
    names = frozenset(budgets) if isinstance(budgets, Mapping) else frozenset()
    if names != REQUIRED_BUDGET_NAMES:
        return (
            "campaign record does not declare exactly the six canonical budgets",
            f"expected={sorted(REQUIRED_BUDGET_NAMES)} found={sorted(names)}",
        )
    terminal_state = outcome.get("terminal_state")
    if terminal_state not in TERMINAL_STATES:
        return (
            "campaign record carries no genuine terminal state",
            f"terminal_state={terminal_state!r} expected one of "
            f"{sorted(TERMINAL_STATES)}",
        )
    return None
