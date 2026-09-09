"""Kod Zekâsı — the browser-safe code-intelligence surface (Command Center
Wave 2B, Surface B).

Owner: `surfaces.command`, composing two already-real, already-canonical
owners. NOT A SECOND CODE INDEX and NOT A SECOND ARCHITECTURE ENGINE: this
module builds nothing of its own.

  - `engineering.codeintel.PythonGraphBuilder` (C-24) builds the real,
    deterministic, rebuildable "import" graph over `backend/arkali` — the
    identical builder `scripts/arkali_memory.py`'s own local index already
    uses, never a copy. This route only aggregates its already-real nodes/
    edges into a bounded summary; the raw graph never crosses the boundary.
  - `surfaces.operations.ai_review_bundle.observe_architecture` is the same
    real, live architecture-gate composition `operations.py`'s own
    `BACKEND_ONLY` `/architecture` route already calls (D-028 scoped that
    route's audience, not the underlying function) — reused verbatim, never
    retagged, never re-implemented.

BOUNDED BY CONSTRUCTION. `top_dependencies` is capped at
`MAX_TOP_DEPENDENCIES` internal areas; no raw node or edge list, no absolute
filesystem path (every path is relative to `backend/arkali`), no file
content — `PythonGraphBuilder` parses `.py` syntax only and never touches a
secret/env file.
"""

from __future__ import annotations

import pathlib
from collections import Counter
from collections.abc import Callable
from typing import Final

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.engineering.codeintel.python_builder import PythonGraphBuilder
from arkali.surfaces.command.contracts import BROWSER_SLICE
from arkali.surfaces.operations.ai_review_bundle import ArchitectureSummary, observe_architecture

Guard = Callable[[str], None]

#: A bounded top-N, never an unbounded ranking — the whole point of this
#: surface being a summary, not a graph dump.
MAX_TOP_DEPENDENCIES: Final[int] = 8

_INTERNAL_PACKAGE_PREFIX: Final[str] = "arkali."


class _CodeIntelligenceDependencyArea(BaseModel):
    """One internal bounded-context area, and how many real import edges
    across the whole scanned tree target it — never a file-level edge, so
    no path pair is representable here."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    area: str
    dependent_count: int


class _CodeIntelligenceSnapshotResponse(BaseModel):
    """Beginner-safe code-intelligence summary: how many files exist, which
    internal areas the rest of the codebase depends on most, and whether the
    architecture gate is currently clean — never a raw graph, symbol name or
    absolute path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    module_count: int
    top_dependencies: tuple[_CodeIntelligenceDependencyArea, ...]
    architecture: ArchitectureSummary


def _internal_area(target: str) -> str | None:
    """The bounded-context area an import target names, or `None` for an
    external (stdlib/third-party) import - those are not this surface's
    concern, `top_dependencies` names internal areas only."""
    if not target.startswith(_INTERNAL_PACKAGE_PREFIX):
        return None
    parts = target.split(".")
    return ".".join(parts[1:3]) if len(parts) > 2 else parts[1]


def _observe_code_intelligence(
    backend_arkali_root: pathlib.Path, repo_root: pathlib.Path,
) -> _CodeIntelligenceSnapshotResponse:
    """Compose the real, live snapshot. Read-only; builds nothing durable."""
    vocabulary = GraphVocabulary.load(repo_root)
    graph = PythonGraphBuilder(vocabulary, backend_arkali_root).build("import")

    areas = Counter(
        area
        for edge in graph.edges()
        if (area := _internal_area(edge.target)) is not None
    )
    top = tuple(
        _CodeIntelligenceDependencyArea(area=area, dependent_count=count)
        for area, count in areas.most_common(MAX_TOP_DEPENDENCIES)
    )
    return _CodeIntelligenceSnapshotResponse(
        module_count=len(graph.nodes()),
        top_dependencies=top,
        architecture=observe_architecture(repo_root),
    )


CodeIntelligenceSnapshotSource = Callable[[], _CodeIntelligenceSnapshotResponse]


def _build_code_intelligence_router(
    guard: Guard, snapshot_source: CodeIntelligenceSnapshotSource,
) -> APIRouter:
    """The one route this surface offers - the identical additive,
    read-only shape `providers.py`'s own `_build_providers_router` already
    established."""
    router = APIRouter(prefix="/api/code-intelligence", tags=[BROWSER_SLICE])

    @router.get("/snapshot", response_model=_CodeIntelligenceSnapshotResponse)
    def snapshot() -> _CodeIntelligenceSnapshotResponse:
        guard("READ_FILE")
        return snapshot_source()

    return router


__all__: list[str] = []
