"""C-34 permission-aware file access (ARK-REQ-0170: `READ_FILE`,
`WRITE_WORKSPACE_FILE`).

Owner: `surfaces.operations`.

CONFINEMENT IS STRUCTURAL, NOT JUST POLICY. `relative` must be a relative
path with no `..` segment, resolved against a caller-supplied `root` and
then re-checked with `is_relative_to` *after* `resolve()` - the identical
two-step check `engineering.candidate.workspace.CandidateWorkspace.path_for`/
`.write` already established, so a symlink planted inside `root` cannot walk
a write outside it. This is a distinct, general-purpose confinement (any
Computer-Use file access, not only a candidate lease) - not a reuse of that
class, since `engineering.candidate`'s own chain into `kernel.contracts` is
already at `max_orchestration_depth` and a direct import would extend it
(the identical shape `product_generation.py`/`pipeline.py` already answered
by not adding the edge).

NEVER READS OR WRITES BEFORE THE REAL PDP DECIDES, mirroring
`process_boundary.py`'s own discipline exactly.
"""

from __future__ import annotations

import pathlib

from arkali.surfaces.operations.computer_use import (
    DEFAULT_TRUST_TIER,
    PolicyDecisionSource,
    authorize_computer_use_action,
)
from arkali.surfaces.operations.execution_contracts import FileOutcome


class FileConfinementError(ValueError):
    """A requested path escapes its assigned root."""


def _confined_path(root: pathlib.Path, relative: str) -> pathlib.Path:
    requested = pathlib.PurePath(relative)
    if requested.is_absolute() or ".." in requested.parts or not requested.parts:
        raise FileConfinementError("file paths must be relative and confined")
    target = root.joinpath(*requested.parts)
    if not target.is_relative_to(root):
        raise FileConfinementError("path escapes its assigned root")
    return target


def read_workspace_file(
    pdp: PolicyDecisionSource,
    *,
    root: pathlib.Path,
    relative: str,
    trust_tier: str = DEFAULT_TRUST_TIER,
) -> FileOutcome:
    """`READ_FILE`, confined to `root`."""
    target = _confined_path(root, relative)
    decision = authorize_computer_use_action(
        pdp, operation_class="READ_FILE", trust_tier=trust_tier,
    )
    if not decision.permits_execution:
        return FileOutcome(decision=decision, executed=False, path=str(target))
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise FileConfinementError("path resolves through a link outside its assigned root")
    if not target.is_file():
        return FileOutcome(decision=decision, executed=False, path=str(target))
    return FileOutcome(
        decision=decision, executed=True, path=str(target), content=target.read_bytes(),
    )


def write_workspace_file(
    pdp: PolicyDecisionSource,
    *,
    root: pathlib.Path,
    relative: str,
    payload: bytes,
    trust_tier: str = DEFAULT_TRUST_TIER,
) -> FileOutcome:
    """`WRITE_WORKSPACE_FILE`, confined to `root`. Never touches Stable -
    `WRITE_STABLE_FILE` is a distinct operation class this function never
    requests, and the PDP's own fixed rule refuses it for every actor
    regardless (`stable_mutation.prohibited_actors` already names
    `computer_use_worker`)."""
    target = _confined_path(root, relative)
    decision = authorize_computer_use_action(
        pdp, operation_class="WRITE_WORKSPACE_FILE", trust_tier=trust_tier,
    )
    if not decision.permits_execution:
        return FileOutcome(decision=decision, executed=False, path=str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved_root = root.resolve()
    resolved_target = target.resolve()
    if not resolved_target.is_relative_to(resolved_root):
        raise FileConfinementError("path resolves through a link outside its assigned root")
    target.write_bytes(payload)
    return FileOutcome(decision=decision, executed=True, path=str(target), content=payload)


__all__ = [
    "read_workspace_file", "write_workspace_file", "FileConfinementError",
]
