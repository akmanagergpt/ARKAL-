"""C-34 Source Intelligence Export (ARK-REQ-0169, ARK-REQ-0357): a real file
tree and real, secret-redacted source content.

Owner: `surfaces.operations`.

MS §Operations / Computer Use / Source Export: "Full Source Intelligence
Export and AI Review Bundle include architecture/tree/contracts/issues/
evidence/source with secrets redacted." This module owns the `tree`/`source`
half; `ai_review_bundle.py` composes it with the other four.

SECRETS ARE REDACTED WITH THE REAL, UNMODIFIED C-09 PATTERN, NEVER A SECOND
ONE. `control.policy.secret_reference.redact_raw_secrets` is the same
pattern `assert_no_raw_secret` already enforces on every evidence/log/prompt
path in this repository - this module never defines its own secret-shape
regex.

CONFINEMENT IS STRUCTURAL, mirroring `file_boundary.py`'s own two-step
relative-path + post-`resolve()` check exactly, so a symlink planted inside
`root` cannot walk an export outside it.

GATED BY THE REAL PDP, THE SAME `READ_FILE` DECISION EVERY OTHER READ IN
THIS CONTEXT ALREADY REQUIRES - an export is a read, never a separate
capability with a separate policy question.
"""

from __future__ import annotations

import pathlib

from pydantic import BaseModel, ConfigDict

from arkali.control.policy.secret_reference import redact_raw_secrets
from arkali.surfaces.operations.computer_use import (
    DEFAULT_TRUST_TIER,
    PolicyDecisionSource,
    authorize_computer_use_action,
)
from arkali.surfaces.operations.computer_use_contracts import ComputerUseDecision

#: Directories never walked - build artefacts and version control internals,
#: never source a human or an AI reviewer needs to see.
_EXCLUDED_DIR_NAMES = frozenset({
    "__pycache__", ".git", "node_modules", ".pytest_cache", ".venv", "venv",
})
#: A generous but real ceiling, so a caller cannot accidentally export a
#: multi-gigabyte tree into memory. Explicit, not implied.
DEFAULT_MAX_FILES = 2000
DEFAULT_MAX_FILE_BYTES = 1_000_000


class SourceFile(BaseModel):
    """One exported file: its path and its real, redacted text content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    relative_path: str
    size_bytes: int
    content: str
    redacted: bool


class SourceExport(BaseModel):
    """The real file tree and real, redacted source content under `root`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: ComputerUseDecision
    executed: bool
    root: str
    tree: tuple[str, ...] = ()
    files: tuple[SourceFile, ...] = ()
    truncated: bool = False


def _walk_tree(root: pathlib.Path, *, max_files: int) -> tuple[list[pathlib.Path], bool]:
    found: list[pathlib.Path] = []
    truncated = False
    for path in sorted(root.rglob("*")):
        if any(part in _EXCLUDED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        if path.is_dir():
            continue
        if len(found) >= max_files:
            truncated = True
            break
        found.append(path)
    return found, truncated


def _read_redacted(path: pathlib.Path, *, max_bytes: int) -> SourceFile:
    relative = str(path.relative_to(path.anchor)) if path.is_absolute() else str(path)
    size = path.stat().st_size
    try:
        raw = path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, ValueError):
        return SourceFile(
            relative_path=relative, size_bytes=size,
            content="<binary or non-UTF-8 file, not exported as text>", redacted=False,
        )
    if size > max_bytes:
        raw = raw[:max_bytes] + "\n<truncated at max_file_bytes>"
    redacted = redact_raw_secrets(raw)
    return SourceFile(
        relative_path=relative, size_bytes=size, content=redacted, redacted=redacted != raw,
    )


def export_source(
    pdp: PolicyDecisionSource,
    *,
    root: pathlib.Path,
    trust_tier: str = DEFAULT_TRUST_TIER,
    max_files: int = DEFAULT_MAX_FILES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> SourceExport:
    """The real file tree and real, redacted source content under `root`."""
    decision = authorize_computer_use_action(
        pdp, operation_class="READ_FILE", trust_tier=trust_tier,
    )
    if not decision.permits_execution:
        return SourceExport(decision=decision, executed=False, root=str(root))

    resolved_root = root.resolve()
    paths, truncated = _walk_tree(resolved_root, max_files=max_files)
    tree = tuple(p.relative_to(resolved_root).as_posix() for p in paths)
    files = tuple(
        _read_redacted(p, max_bytes=max_file_bytes).model_copy(
            update={"relative_path": p.relative_to(resolved_root).as_posix()}
        )
        for p in paths
    )
    return SourceExport(
        decision=decision, executed=True, root=str(root), tree=tree, files=files,
        truncated=truncated,
    )


__all__ = ["SourceFile", "SourceExport", "export_source", "DEFAULT_MAX_FILES",
           "DEFAULT_MAX_FILE_BYTES"]
