"""Sağlayıcılar ve Modeller — the browser-safe local-AI readiness surface.

Owner: `surfaces.command`, composing `engineering.localai`'s already-real
capability/host-probe authorities. NOT A SECOND PROVIDER SYSTEM: this module
holds no probe, no adapter and no capability state of its own. The capability
answer (whether a local model is genuinely usable right now) is composed
exactly once, at composition time, by `scripts/run_command_center.py` — the
identical `compose_real_capability_authority` call `_factory_submitter`
already makes for Factory routing — so this file never imports
`engineering.localai` directly and adds no edge the architecture budget would
measure a second time; it only receives an already-built snapshot source.

NOTHING SENSITIVE CROSSES THIS BOUNDARY. No environment variable, API key,
host command output or filesystem path is representable here — every field is
a `DimensionReading`, the exact browser-safe shape `surfaces.operations`
already established for the Operations page, reused unchanged rather than a
second telemetry contract.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from arkali.surfaces.command.contracts import BROWSER_SLICE
from arkali.surfaces.operations.contracts import DimensionReading

Guard = Callable[[str], None]


class _ProvidersSnapshotResponse(BaseModel):
    """Beginner-safe local-AI readiness: exactly the three facts a user
    needs — is a local runtime usable, which model is configured, is an
    accelerator present — never a raw provider/transport dump."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    local_runtime: DimensionReading
    configured_model: DimensionReading
    accelerator: DimensionReading


ProvidersSnapshotSource = Callable[[], _ProvidersSnapshotResponse]


def _build_providers_router(guard: Guard, snapshot_source: ProvidersSnapshotSource) -> APIRouter:
    """The one route this surface offers — read-only, additive and optional
    at the composition root, the identical shape `factory_history.py`'s own
    `_build_factory_history_router` already established."""
    router = APIRouter(prefix="/api/providers", tags=[BROWSER_SLICE])

    @router.get("/snapshot", response_model=_ProvidersSnapshotResponse)
    def snapshot() -> _ProvidersSnapshotResponse:
        guard("READ_FILE")
        return snapshot_source()

    return router


__all__: list[str] = []
