"""C-34 AI Review Bundle (ARK-REQ-0169, ARK-REQ-0357): architecture / tree /
contracts / issues / evidence / source, composed into one real bundle.

Owner: `surfaces.operations`.

EACH DIMENSION IS READ FROM ITS OWNING AUTHORITY, NEVER RE-DERIVED.
`architecture` reuses the real, unmodified `control.architecture.GateRunner`
(the identical mechanism `check_repository_structure.py` and every prior
phase's own acceptance evidence already runs) - no second architecture
summary is computed. `contracts`/`issues`/`evidence` reference the
canonical documents/roots that already own those facts
(`CONTRACT_INVENTORY.md`, `OPEN_BLOCKERS.md`, the evidence store root) by
path and a real, cheap count, rather than re-implementing
`acceptance.engine`'s own findings parser or evidence graph a second time -
`acceptance.engine`'s own chain into `kernel.contracts` is already at
`max_orchestration_depth`, and re-deriving its parsing here would either
duplicate it (the F-0013 shadow-model defect) or extend that chain (the
identical violation Package 1 already answered once for
`execution.workflow` by not adding the edge). `source`/`tree` are
`source_export.py`'s own real, redacted read.

READING THESE CANONICAL DOCUMENTS IS NOT A GOVERNED COMPUTER-USE OPERATION.
Every phase's own acceptance tooling already reads `AUTHORITY_MAP.yaml`,
`CONTRACT_INVENTORY.md` and `OPEN_BLOCKERS.md` directly, ungated, throughout
this repository (`RequirementRegister.load`, `AuthorityMap.load`, `checker.
py`'s own findings reconciliation) - these are the tool's own canonical
specification, not workspace or candidate content. Only `source_export`'s
own read of the *target* source tree goes through the real PDP.
"""

from __future__ import annotations

import pathlib

from pydantic import BaseModel, ConfigDict

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.runner import GateRunner
from arkali.surfaces.operations.computer_use import DEFAULT_TRUST_TIER, PolicyDecisionSource
from arkali.surfaces.operations.source_export import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_FILES,
    SourceExport,
    export_source,
)


class ArchitectureSummary(BaseModel):
    """The real, live architecture gate results - never a cached figure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gates_passed: int
    gates_total: int
    violations: tuple[str, ...] = ()


class DocumentReference(BaseModel):
    """A pointer to a canonical document or evidence directory this bundle
    does not re-parse. `size_bytes` is populated for a real file;
    `file_count` (a real recursive count) for a real directory - never both,
    so a caller cannot mistake one meaning for the other."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    exists: bool
    is_directory: bool = False
    size_bytes: int | None = None
    file_count: int | None = None


class AiReviewBundle(BaseModel):
    """architecture / tree / contracts / issues / evidence / source, in one
    real, composed bundle (ARK-REQ-0169/0357)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    architecture: ArchitectureSummary
    contracts: DocumentReference
    issues: DocumentReference
    evidence: DocumentReference
    source: SourceExport


def _observe_architecture(repo_root: pathlib.Path) -> ArchitectureSummary:
    authority_map = AuthorityMap.load(repo_root)
    results = GateRunner(repo_root, authority_map).run_all()
    passed = [r for r in results if r.state.value == "PASS"]
    violations = tuple(
        f"{r.check_id}: {r.summary}" for r in results if r.state.value != "PASS"
    )
    return ArchitectureSummary(
        gates_passed=len(passed), gates_total=len(results), violations=violations,
    )


def _reference(repo_root: pathlib.Path, relative: str) -> DocumentReference:
    target = repo_root / relative
    if target.is_file():
        return DocumentReference(
            path=relative, exists=True, size_bytes=target.stat().st_size,
        )
    if target.is_dir():
        count = sum(1 for p in target.rglob("*") if p.is_file())
        return DocumentReference(
            path=relative, exists=True, is_directory=True, file_count=count,
        )
    return DocumentReference(path=relative, exists=False)


def build_ai_review_bundle(
    pdp: PolicyDecisionSource,
    *,
    repo_root: pathlib.Path,
    source_root: pathlib.Path,
    trust_tier: str = DEFAULT_TRUST_TIER,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> AiReviewBundle:
    """The real, composed AI Review Bundle. `repo_root` locates the
    canonical documents this tool already owns; `source_root` is the
    (PDP-gated) tree actually exported as `source`/`tree` - the two may
    differ, since a caller might export only a subdirectory."""
    return AiReviewBundle(
        architecture=_observe_architecture(repo_root),
        contracts=_reference(repo_root, "docs/canonical/CONTRACT_INVENTORY.md"),
        issues=_reference(repo_root, "docs/build/OPEN_BLOCKERS.md"),
        evidence=_reference(repo_root, "docs/acceptance"),
        source=export_source(
            pdp, root=source_root, trust_tier=trust_tier,
            max_files=max_files, max_file_bytes=max_file_bytes,
        ),
    )


__all__ = [
    "ArchitectureSummary", "DocumentReference", "AiReviewBundle",
    "build_ai_review_bundle",
]
