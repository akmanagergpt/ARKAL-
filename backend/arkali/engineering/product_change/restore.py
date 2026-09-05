"""Restore-as-new-revision: "Bu sürüme geri dön" (Managed Product Revision
History + Restore-as-New Convergence).

RESTORE IS A PROPOSAL, NOT POINTER MOVEMENT. Restoring an older revision
never mutates or "reactivates" it -- `ProjectRevisionRecord` is immutable
and `sequence` only ever increases (`records.py`'s own `before_update`
refusal, `registry.next_sequence`). This module produces a real
`PreparedModification` -- BYTE-IDENTICAL to the type `modification.
prepare_modification` returns -- whose content is the SOURCE-BASIS
revision's own real, immutable bytes rather than a model's invention, so
`promotion.promote_modification` (unmodified) appends it as a genuinely
new revision through the exact same append-only path, gated by the exact
same `MANAGED_PRODUCT_REVISION_PROMOTION` grant, subject to the exact
same stale-base check. There is no second promotion path, no second
`ProjectRevisionRecord` authority and no pointer anywhere that moves
backward.

BASE REVISION VS SOURCE-BASIS REVISION. `base_revision_id` (on the
returned `PreparedModification`, exactly like a normal change) is the
project's real CURRENT revision at proposal time -- concurrency safety
stays anchored there, so `promote_modification`'s own existing
stale-base check (comparing `base_revision_id` against the real current
revision at promote time) needs no change to protect a restore too.
`source_basis_revision_id` is the explicit historical revision whose
content is being restored -- resolved by real, explicit identity
(`ProjectRegistry.revision`), never inferred, never required to be the
project's current revision, and may be any real revision the project
already has, including the current one itself (a harmless no-op restore).

ZERO PROVIDER INVOCATION. The desired content already exists, in full,
as the source-basis revision's own real immutable bytes -- asking a
model to reconstruct what is already known would be real, needless
non-determinism (the permanent Engineering Reliability mission's own
`ARK-REQ-0398`: mechanical evidence over model output wherever the
evidence already exists). This module never references `ModificationWiring.
model`/`.model_id` at all; the diff between the two REAL materialized
trees is computed here, directly, in Python.

REUSES `modification.py`'s OWN PRIVATE APPLY/VERIFY/REGISTER HELPERS,
UNCHANGED -- same package, same bounded context, no new architecture
edge and no second changeset-application or verification mechanism. The
resulting `PreparedModification` is handed to the UNMODIFIED `promotion.
promote_modification` by the caller, exactly as a normal change is.
"""

from __future__ import annotations

import pathlib
import shutil
import time
from typing import Callable

from arkali.engineering.product_change.change_plan import ChangeOperation, ChangePlan
from arkali.engineering.product_change.errors import (
    RevisionSourceUnavailableError,
    UnknownSourceBasisRevisionError,
)
from arkali.engineering.product_change.modification import (
    ModificationWiring,
    PreparedModification,
    _apply_changeset,
    _register_changeset_evidence,
    _register_plan,
)
from arkali.engineering.product_change.revision_resolution import (
    materialized_source,
    resolve_current_revision,
)
from arkali.engineering.product_change.verification import verify_changeset

_OnPhase = Callable[[str, dict[str, object]], None]


def _report(on_phase: _OnPhase | None, phase: str, detail: dict[str, object]) -> None:
    if on_phase is not None:
        on_phase(phase, detail)


#: Real, derived build/tooling artifacts a candidate directory or a
#: previously-promoted archive may genuinely carry (a real `pytest` run
#: leaves `__pycache__`, a real `npm install` leaves `node_modules`) --
#: never authored product source, and never restorable/diffable as text.
#: Found for real: `golden-work-129`'s own real candidate directory
#: carries `tests/__pycache__/test_app.cpython-313-pytest-9.1.1.pyc` from
#: its own real acceptance run, which is not valid UTF-8 -- a real
#: restore must not crash on a real, honest side effect of a real prior
#: test run. Excluding these directories is also correct on its own
#: terms: they are ephemeral and machine-regenerated, never part of what
#: a human means by "this version's content".
_NON_SOURCE_DIR_NAMES = frozenset({"__pycache__", "node_modules", ".git"})


def _relative_files(root: pathlib.Path) -> dict[str, pathlib.Path]:
    """Every real, textual source file under `root`, keyed by its POSIX-
    relative path -- the same sorted, symlink-safe walk `revision_
    resolution.archive_source` already establishes for deterministic
    archiving, reused here for a deterministic diff instead, with real
    derived build artifacts excluded (see `_NON_SOURCE_DIR_NAMES`) and any
    remaining file that is not valid UTF-8 text skipped rather than
    crashing this whole restore -- fail closed on the RESTORE as a whole
    only if that ever leaves zero real source files, never on one real,
    honest binary artifact found along the way."""
    files: dict[str, pathlib.Path] = {}
    for path in sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()):
        relative = path.relative_to(root)
        if _NON_SOURCE_DIR_NAMES & set(relative.parts[:-1]):
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files[relative.as_posix()] = path
    return files


def _diff_operations(
    base_dir: pathlib.Path, source_basis_dir: pathlib.Path, source_basis_revision_id: str,
) -> tuple[ChangeOperation, ...]:
    """A real, mechanical, file-level diff between two real materialized
    trees -- never a model's invention. Every `create`/`update` operation's
    `content` is copied byte-for-byte (decoded as UTF-8, the same
    assumption `modification._apply_changeset` already makes for every
    real Managed Product source file) from the source-basis revision's own
    real bytes. `ChangePlan.operations` requires at least one entry; if the
    two trees are byte-identical (restoring the current revision to
    itself, or restoring to a revision whose content a later change never
    actually altered), one real, unchanged file is re-stated as an
    `update` -- true, not fabricated: after this restore, that file's
    content is exactly what is stated, it merely already was."""
    base_files = _relative_files(base_dir)
    source_files = _relative_files(source_basis_dir)
    if not source_files:
        raise RevisionSourceUnavailableError(
            f"revision {source_basis_revision_id!r} carries no real, textual "
            "source file to restore"
        )

    operations: list[ChangeOperation] = []
    for relative in sorted(source_files):
        content = source_files[relative].read_text(encoding="utf-8")
        if relative not in base_files:
            operations.append(ChangeOperation(
                operation="create", path=relative, content=content,
                rationale=f"restored from revision {source_basis_revision_id!r}: new file",
            ))
        elif base_files[relative].read_text(encoding="utf-8") != content:
            operations.append(ChangeOperation(
                operation="update", path=relative, content=content,
                rationale=f"restored from revision {source_basis_revision_id!r}: content differs",
            ))
    for relative in sorted(set(base_files) - set(source_files)):
        operations.append(ChangeOperation(
            operation="delete", path=relative,
            rationale=f"restored from revision {source_basis_revision_id!r}: absent there",
        ))

    if not operations:
        relative, path = next(iter(sorted(source_files.items())))
        operations.append(ChangeOperation(
            operation="update", path=relative, content=path.read_text(encoding="utf-8"),
            rationale=(
                f"restored from revision {source_basis_revision_id!r}: content already "
                "identical to the current revision"
            ),
        ))
    return tuple(operations)


def prepare_restore(
    project_id: str, source_basis_revision_id: str, *, registry: object, wiring: ModificationWiring,
    on_phase: _OnPhase | None = None,
) -> PreparedModification:
    """"Bu sürüme geri dön": resolve the real current (base) revision and
    the real, explicit source-basis revision, materialize BOTH real
    immutable sources, compute their real diff, apply it through the
    UNCHANGED `modification._apply_changeset`, verify it through the
    UNCHANGED `verification.verify_changeset`, and return a real
    `PreparedModification` ready for the UNCHANGED `promotion.
    promote_modification` -- no provider call anywhere in this function.
    """
    base = resolve_current_revision(project_id, registry=registry)  # type: ignore[arg-type]
    _report(on_phase, "base_revision_resolved", {"base_revision_id": base.revision_id})

    source_basis = registry.revision(source_basis_revision_id)  # type: ignore[attr-defined]
    if source_basis is None or source_basis.project_id != project_id:
        raise UnknownSourceBasisRevisionError(
            f"revision {source_basis_revision_id!r} is not a real revision of "
            f"project {project_id!r}"
        )
    _report(on_phase, "source_basis_resolved", {
        "source_basis_revision_id": source_basis.revision_id,
    })

    with materialized_source(
        base, artifacts=wiring.artifacts, candidate_source_resolver=wiring.candidate_source_resolver,
    ) as base_source:
        workspace_id = f"restore-{project_id}-{int(time.time())}"
        workspace = wiring.workspace_allocator.allocate(
            workspace_id=workspace_id, task_id="product-restore", agent_id="command-center",
            stable_snapshot=base_source,
        )
    product_root = workspace.snapshot
    _report(on_phase, "workspace_allocated", {"workspace_root": str(workspace.root)})

    # From here on the real, on-disk `workspace.root` exists: any real
    # failure below must remove it before propagating, the identical
    # discipline `modification.prepare_modification` already applies to
    # its own post-allocation provider-response failures -- an orphaned
    # `var/factory/changes/restore-*` directory is a real, found defect
    # class, not a hypothetical one (reproduced live: a real non-UTF8
    # build artifact crashing `_diff_operations` left exactly this behind
    # before this fix).
    try:
        with materialized_source(
            source_basis, artifacts=wiring.artifacts,
            candidate_source_resolver=wiring.candidate_source_resolver,
        ) as source_basis_dir:
            operations = _diff_operations(product_root, source_basis_dir, source_basis.revision_id)
            _apply_changeset(workspace, operations)
        _report(on_phase, "changes_applied", {"operations": len(operations)})

        plan = ChangePlan(
            request_text=f"Bu sürüme geri dön: {source_basis.revision_id}",
            target_summary=f"restore revision {project_id!r} to the content of {source_basis.revision_id!r}",
            operations=operations,
        )

        _report(on_phase, "verification_running", {})
        verification = verify_changeset(product_root, operations)
        _report(
            on_phase, "verification_passed" if verification.passed else "verification_failed",
            {"failures": verification.failures},
        )

        plan_ref = _register_plan(wiring.artifacts, project_id, plan)
        changeset_ref = _register_changeset_evidence(wiring.artifacts, project_id, plan_ref, verification)
    except Exception:
        shutil.rmtree(workspace.root, ignore_errors=True)
        raise

    return PreparedModification(
        workspace=workspace, product_root=product_root, base_revision_id=base.revision_id,
        plan=plan, plan_ref=plan_ref, changeset_ref=changeset_ref, verification=verification,
    )
