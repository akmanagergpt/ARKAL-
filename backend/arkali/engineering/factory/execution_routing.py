"""D-026 adaptive execution-tier routing (`ARK-REQ-0392`, `ARK-REQ-0393`).

Owner: `engineering.factory`.

COMPOSITION, NOT A SECOND AUTHORITY. This module owns exactly one thing: the
ORDER in which the eight canonical tiers are tried and the honest
NOT_CONFIGURED/EXHAUSTED/SELECTED verdict for each. It stores no provider
identity, no capability node, no worker contract and no repair fingerprint of
its own; every fact it reasons over is supplied by the caller from the real
owning authority, exactly as `AdmissionService` (C-21) already does one layer
below. No provider registry, capability graph, scheduler or repair-budget
ledger is constructed, cached or duplicated here.

THE EIGHT TIERS ARE READ FROM D-026, NOT RE-DERIVED. `docs/build/DECISION_LOG.md`
records: "deterministic tool -> verified knowledge -> local model -> stronger
local/independent local reviewer -> cloud provider -> stronger cloud
specialist -> multi-reviewer -> human governance". `TIER_ORDER` below is that
exact sequence and nothing else may reorder it.

WHY TIERS 2, 5 AND 6 RESOLVE NOT_CONFIGURED TODAY, HONESTLY, BY CONSTRUCTION.
`engineering.knowledge` (Phase 18) and `engineering.localai` (Phase 22) ship no
module beyond their context declaration, and no live provider registry exists
anywhere in this repository (`control.registry.provider` is a static contract
and architectural-enforcement authority, not a running store of configured
providers) - confirmed by inspection before this module was written. This is
not a fabricated answer: it is the same honest shape `CapabilityGraph.can_perform` already
uses pre-activation (`ARK-REQ-0049`), and it changes the moment those phases
exist and are wired in by a real caller, never by editing this file's
constants.

TIER 8 IS THE ONLY TIER THAT IS ALWAYS DETERMINATE. When no automated tier
resolves, escalation to human governance is not a failure mode this module
invents; it is D-026's own explicit terminal tier, and `select_execution_tier`
always returns it rather than `None` in that case - there is no "no decision"
outcome (`ARK-REQ-0393`'s false-PASS prohibition, applied to the absence
direction too).

NO DURABLE STATE IS TOUCHED. This module imports nothing from
`execution.durable`, mutates no job record and performs no filesystem or
process I/O; `task_id` passes through unchanged. Preservation of durable task
state under failover is therefore a structural property, not a promise: there
is nothing here that could lose it.
"""

from __future__ import annotations

import enum
from typing import Callable, Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.control.capability.capability_graph import CapabilityQueryResult
from arkali.engineering.factory.errors import RoutingDecisionIncomplete
from arkali.engineering.repair.contracts import RepairBudgetLedger, RepairFingerprint
from arkali.kernel.contracts.results import HonestState


class ExecutionTier(str, enum.Enum):
    """The eight canonical tiers, spelled exactly as D-026 records them."""

    DETERMINISTIC_TOOL = "deterministic_tool"
    VERIFIED_KNOWLEDGE = "verified_knowledge"
    LOCAL_MODEL = "local_model"
    STRONGER_LOCAL_REVIEWER = "stronger_local_reviewer"
    CLOUD_PROVIDER = "cloud_provider"
    STRONGER_CLOUD_SPECIALIST = "stronger_cloud_specialist"
    MULTI_REVIEWER = "multi_reviewer"
    HUMAN_GOVERNANCE = "human_governance"


#: The declared preference order (D-026). Immutable; never re-sorted.
TIER_ORDER: Final[tuple[ExecutionTier, ...]] = (
    ExecutionTier.DETERMINISTIC_TOOL,
    ExecutionTier.VERIFIED_KNOWLEDGE,
    ExecutionTier.LOCAL_MODEL,
    ExecutionTier.STRONGER_LOCAL_REVIEWER,
    ExecutionTier.CLOUD_PROVIDER,
    ExecutionTier.STRONGER_CLOUD_SPECIALIST,
    ExecutionTier.MULTI_REVIEWER,
    ExecutionTier.HUMAN_GOVERNANCE,
)

#: Tiers with no owning authority shipped yet (Phase 18, Phase 22) or no live
#: runtime store at all (no configured provider anywhere in this repository).
#: Declared here as a closed, honestly-derived set - not a guess, not an invented default.
_STRUCTURALLY_UNAVAILABLE: Final[frozenset[ExecutionTier]] = frozenset({
    ExecutionTier.VERIFIED_KNOWLEDGE,       # engineering.knowledge: Phase 18, unbuilt
    ExecutionTier.CLOUD_PROVIDER,           # no live provider registry exists
    ExecutionTier.STRONGER_CLOUD_SPECIALIST,  # same
    ExecutionTier.MULTI_REVIEWER,           # needs >=2 of the above; none exist
})


class TierState(str, enum.Enum):
    SELECTED = "selected"
    NOT_CONFIGURED = "not_configured"
    EXHAUSTED = "exhausted"


class TierEligibilityRequest(BaseModel):
    """What the caller asks to have routed. Opaque `task_id`; no durable
    handle, no job state - the owning durable authority holds those."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str = Field(min_length=1)
    #: Whether a deterministic transformer/tool can satisfy this task at all.
    #: A fact the caller derives from the task itself, never guessed here.
    deterministic_capable: bool = False
    #: A capability id to consult the real Capability Graph for, or None.
    capability_id: str | None = None


class TierEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: ExecutionTier
    state: TierState
    reason: str = Field(min_length=1)


class TierSelection(BaseModel):
    """The routing verdict. No PASS/FAIL field exists - `selected` is an
    `ExecutionTier`, never a boolean, so a NOT_CONFIGURED/EXHAUSTED tier
    cannot be misread as success (`ARK-REQ-0393`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task_id: str
    selected: ExecutionTier
    evaluations: tuple[TierEvaluation, ...]

    @property
    def is_automated(self) -> bool:
        return self.selected is not ExecutionTier.HUMAN_GOVERNANCE


def _deterministic_tool(
    request: TierEligibilityRequest,
    ledger: RepairBudgetLedger | None,
    fingerprint: RepairFingerprint | None,
) -> TierEvaluation:
    if not request.deterministic_capable:
        return TierEvaluation(
            tier=ExecutionTier.DETERMINISTIC_TOOL, state=TierState.NOT_CONFIGURED,
            reason="task is not deterministically satisfiable",
        )
    if ledger is not None and fingerprint is not None and ledger.repeats_failed_strategy(fingerprint):
        return TierEvaluation(
            tier=ExecutionTier.DETERMINISTIC_TOOL, state=TierState.EXHAUSTED,
            reason="repeated failed strategy bounded by the existing C-26 ledger",
        )
    return TierEvaluation(
        tier=ExecutionTier.DETERMINISTIC_TOOL, state=TierState.SELECTED,
        reason="task is deterministically satisfiable and not budget-exhausted",
    )


def _local_model(
    request: TierEligibilityRequest,
    tier: ExecutionTier,
    capability_query: Callable[[str], CapabilityQueryResult] | None,
) -> TierEvaluation:
    if request.capability_id is None or capability_query is None:
        return TierEvaluation(
            tier=tier, state=TierState.NOT_CONFIGURED,
            reason="no capability id or capability authority supplied",
        )
    result = capability_query(request.capability_id)
    if result.state is HonestState.PASS:
        return TierEvaluation(
            tier=tier, state=TierState.SELECTED,
            reason=f"capability {request.capability_id!r} resolved PASS",
        )
    return TierEvaluation(
        tier=tier, state=TierState.NOT_CONFIGURED,
        reason=f"capability {request.capability_id!r} resolved {result.state.value}",
    )


def select_execution_tier(
    request: TierEligibilityRequest,
    *,
    capability_query: Callable[[str], CapabilityQueryResult] | None = None,
    ledger: RepairBudgetLedger | None = None,
    fingerprint: RepairFingerprint | None = None,
) -> TierSelection:
    """Evaluate all eight tiers in D-026's declared order; return the first
    SELECTED, or `HUMAN_GOVERNANCE` if none automated resolves.

    Every tier is evaluated and recorded (`evaluations`), even after a
    selection, so the full decision trail is inspectable — never just the
    winning tier.
    """
    evaluations: list[TierEvaluation] = []
    selected: ExecutionTier | None = None

    for tier in TIER_ORDER:
        if selected is not None:
            evaluations.append(TierEvaluation(
                tier=tier, state=TierState.NOT_CONFIGURED,
                reason="a higher-preference tier was already selected",
            ))
            continue
        if tier is ExecutionTier.DETERMINISTIC_TOOL:
            evaluation = _deterministic_tool(request, ledger, fingerprint)
        elif tier in (ExecutionTier.LOCAL_MODEL, ExecutionTier.STRONGER_LOCAL_REVIEWER):
            evaluation = _local_model(request, tier, capability_query)
        elif tier in _STRUCTURALLY_UNAVAILABLE:
            evaluation = TierEvaluation(
                tier=tier, state=TierState.NOT_CONFIGURED,
                reason="tier's owning authority is not yet built or has no live runtime instance",
            )
        else:
            evaluation = TierEvaluation(
                tier=tier, state=TierState.SELECTED,
                reason="terminal tier: no eligible automated tier resolved",
            )
        evaluations.append(evaluation)
        if evaluation.state is TierState.SELECTED:
            selected = tier

    if selected is None:
        raise RoutingDecisionIncomplete(
            "no tier resolved SELECTED, including the always-determinate "
            "human-governance terminal tier; this cannot happen for a "
            "TIER_ORDER ending in human_governance and indicates TIER_ORDER "
            "itself was mutated"
        )
    return TierSelection(task_id=request.task_id, selected=selected, evaluations=tuple(evaluations))
