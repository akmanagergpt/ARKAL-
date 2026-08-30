"""Read-only Phase 30 production-history surface.

READ-ONLY BY DESIGN, mirroring `operations.py`'s own posture exactly: this
router exposes what `engineering.candidate.ledger.CandidateLedger` and
`engineering.candidate.campaign_budget.GenerationCampaignLedger` have
already, durably recorded about real `golden-work-*` generation attempts
(`scripts/run_staged_generation.py`) -- never a live trigger, never a
mutation. Submitting a new goal remains `factory.py`'s own
`POST /api/factory/goals`, untouched here.

NOT A CLOSURE OF DEF-009. `docs/build/OPEN_BLOCKERS.md` records DEF-009 as a
permanently open gap: no live orchestrator or worker/scheduler loop wires
this repository's real staged-generation pipeline to the Command Center's
own job/registry system (sub-gaps (a)/(b), owner still unassigned). This
module does not build that -- it only lets an operator see, read-only, what
the pipeline's own CLI-driven runs have already recorded on disk. Closing
DEF-009 is out of this module's scope, and its own response never claims
otherwise.

SUPPLIED, NOT BUILT HERE -- the identical shape `operations.py`'s own module
docstring already established for `probe_host`: a direct `engineering.
candidate` import here would be a real, undeclared `surfaces.command ->
engineering.candidate` dependency edge (`AUTHORITY_MAP.yaml` declares no
such edge today). The two data sources are opaque `Callable`s instead,
constructed from the real `CandidateLedger`/`GenerationCampaignLedger`
classes in `scripts/run_command_center.py` (the composition root, outside
the measured architecture graph) -- the same wiring shape `factory.py`'s
own `_FactorySubmitter` already established for the sibling POST route.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from arkali.surfaces.command.contracts import BROWSER_SLICE


class FactoryCandidateSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    state: str
    recorded_at: str


class FactoryCampaignAttempt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    outcome: str
    failure_class: str | None
    fingerprint: str | None
    elapsed_seconds: float
    recorded_at: str


class FactoryCampaignSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    campaign_id: str
    max_new_candidates: int
    max_total_seconds: float
    max_same_fingerprint_repeats: int
    consumed_candidates: int
    consumed_seconds: float
    status: str
    attempts: tuple[FactoryCampaignAttempt, ...]


class FactoryHistorySnapshot(BaseModel):
    """Every real `golden-work-*` candidate and campaign this host's own
    ledgers have recorded -- re-derived from disk on every call, the same
    "nothing is cached" discipline `OperationsSnapshot` already applies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[FactoryCandidateSummary, ...]
    campaigns: tuple[FactoryCampaignSummary, ...]


Guard = Callable[[str], None]
_CandidateHistorySource = Callable[[], tuple[FactoryCandidateSummary, ...]]
_CampaignHistorySource = Callable[[], tuple[FactoryCampaignSummary, ...]]


def _build_factory_history_router(
    guard: Guard, candidates: _CandidateHistorySource, campaigns: _CampaignHistorySource,
) -> APIRouter:
    router = APIRouter(prefix="/api/factory", tags=[BROWSER_SLICE])

    @router.get("/history", response_model=FactoryHistorySnapshot)
    def history() -> FactoryHistorySnapshot:
        guard("READ_FILE")
        return FactoryHistorySnapshot(candidates=candidates(), campaigns=campaigns())

    return router


__all__ = [
    "_CampaignHistorySource", "_CandidateHistorySource", "FactoryHistorySnapshot",
    "FactoryCampaignAttempt", "FactoryCampaignSummary", "FactoryCandidateSummary", "_build_factory_history_router",
]
