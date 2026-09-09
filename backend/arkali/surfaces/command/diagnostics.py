"""Tanılama — the browser-safe diagnostics surface (Command Center Wave 2C,
Surface C).

Owner: `surfaces.command`. A REPRESENTATION SURFACE ONLY. This module holds
no finding, no job, no architecture verdict and no operational fact of its
own, and — unlike `providers.py`/`code_intelligence.py` — it composes
NOTHING itself: `acceptance.engine` (`GovernanceState`/`findings`) already
has its own pre-existing chain into `kernel.contracts` measured at the
`max_orchestration_depth` ceiling (4 of 4), so a direct import here would
extend it to 5 (found by running the gate, not assumed); `control.policy.
pep` was already at its own fan-in ceiling (15 of 15) before this surface
existed. Both are the identical shape `operations.py`'s own module
docstring already documents for `PolicyEnforcementPoint`/`host_probe`, so
the answer is the same one this repository has used since Phase 25:
`scripts/run_command_center.py` (outside the measured architecture graph)
composes the real snapshot — `GovernanceState`, `findings.parse_findings`,
`JobStore` behind a real `PolicyEnforcementPoint`, and `surfaces.operations.
ai_review_bundle.observe_architecture` — and hands this router an
already-built, session-parameterised snapshot source. This file never
imports `acceptance.engine`, `control.policy.pep` or `execution.durable`
directly.

STRUCTURED, NEVER FREE TEXT — THE STALE-ACTION-SAFETY ANSWER. `operational_
hint` is one of the same five values `scripts/task_packet.py::_live_next_
action_hint` already established (`resolve_open_finding`, `review_pending_
product_change`, `pending_operational_job`, `no_pending_operational_work`,
`live_state_unavailable`), derived fresh from live `JobStore`/
`GovernanceState` facts by the composition root — never `ARKALI_HANDOFF.md`'s
own free-text "NEXT EXACT ACTION" narrative, and never a second staleness
heuristic re-checking it: a value re-derived from live state on every call
cannot go stale the way cached prose can, so none was written here.

BOUNDED BY CONSTRUCTION. `top_findings` is capped by the composition root at
a small fixed maximum; each finding's `detail` is truncated; `architecture.
violations` is whatever the real gate run already bounds itself to (one
line per real failing check). No absolute filesystem path, secret or raw
job/checkpoint payload is representable in either DTO below.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
import datetime as dt

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from arkali.surfaces.command.contracts import BROWSER_SLICE
from arkali.surfaces.operations.ai_review_bundle import ArchitectureSummary

Guard = Callable[[str], None]
SessionScope = Callable[[], Iterator[Session]]


class _DiagnosticsFinding(BaseModel):
    """One open finding, bounded and truncated by the composition root -
    never the full ledger row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    severity: str
    status: str
    detail: str


class _DiagnosticsSnapshotResponse(BaseModel):
    """Beginner-safe system-diagnostics summary. Every field is re-derived
    on each call by the composition root from real owners; nothing here is
    this surface's own truth."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    overall_status: str
    open_stopping_count: int
    top_findings: tuple[_DiagnosticsFinding, ...]
    architecture: ArchitectureSummary
    operational_hint: str
    generated_at: dt.datetime


DiagnosticsSnapshotSource = Callable[[Session], _DiagnosticsSnapshotResponse]


def _build_diagnostics_router(
    guard: Guard, session_scope: SessionScope, snapshot_source: DiagnosticsSnapshotSource,
) -> APIRouter:
    """The one route this surface offers - the identical additive,
    read-only shape `providers.py`/`code_intelligence.py` already
    established, extended with the real per-request `Session` this
    surface's own `JobStore` read needs (`operations.py`'s own `/snapshot`
    precedent)."""
    router = APIRouter(prefix="/api/diagnostics", tags=[BROWSER_SLICE])

    @router.get("/snapshot", response_model=_DiagnosticsSnapshotResponse)
    def snapshot(session: Session = Depends(session_scope)) -> _DiagnosticsSnapshotResponse:
        guard("READ_FILE")
        return snapshot_source(session)

    return router


__all__: list[str] = []
