"""The nine step implementations (ARK-REQ-0151, ARK-REQ-0336, ARK-REQ-0152).

Owner: `lifecycle.recovery` (Protected Core).

Split from `migration_safety.py` under the module logical-line budget
(`ARCHITECTURE.md` section 8) - ADR-0008 decomposition, not an exception.
Every function here is a pure step: explicit inputs, one `MigrationStepResult`
out, no orchestration decision about what runs next - that stays in
`MigrationSafetySequence.run`.

MECHANICS STAY IN THE KERNEL. Every byte-level operation - copying a database,
running Alembic, computing an impact report, checking integrity - belongs to
`kernel.persistence`, exactly as `backup_service.py` already established for
backup/restore. Nothing here parses a migration file or issues raw SQL itself.
"""

from __future__ import annotations

import pathlib

from sqlalchemy import Engine

from arkali.control.policy.operation_class import Decision
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.kernel.persistence.backup import integrity_check, restore_database
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migration_impact import analyze_file
from arkali.kernel.persistence.migrations import (
    VERSIONS_DIR,
    applied_revision,
    declared_migrations,
    head_revision,
    is_forward_only,
    run_upgrade,
)
from arkali.kernel.persistence.schema_contract import MigrationContract
from arkali.lifecycle.recovery.backup_service import BackupSet, RecoveryService, Verifier
from arkali.lifecycle.recovery.migration_safety_types import (
    ACTOR,
    APPLY_OPERATION,
    STEP_APPLICATION_TESTS,
    STEP_APPLY,
    STEP_BACKUP,
    STEP_CANDIDATE_MIGRATION,
    STEP_DRY_RUN,
    STEP_IMPACT,
    STEP_INTEGRITY,
    STEP_ROLLBACK_POINT,
    STEP_VERIFY,
    TRUST_TIER,
    MigrationSafetyRequest,
    MigrationStepResult,
    MigrationStepState,
)


def _pending_chain(
    chain: tuple[MigrationContract, ...], current: str | None, target: str
) -> tuple[MigrationContract, ...]:
    """The revisions between `current` (exclusive) and `target` (inclusive).

    A revision already applied already ran under its own, earlier Impact
    analysis; re-flagging it here would block a target it cannot affect. An
    unknown `current` (never migrated, or from a foreign chain) is treated as
    "nothing applied yet", so the whole prefix up to `target` is pending.
    """
    revisions = [c.revision for c in chain]
    if target not in revisions:
        return ()
    target_index = revisions.index(target)
    start_index = revisions.index(current) + 1 if current in revisions else 0
    if start_index > target_index:
        return ()
    return chain[start_index:target_index + 1]


def step_impact(
    backend_root: pathlib.Path, current_revision: str | None, target_revision: str
) -> MigrationStepResult:
    chain = declared_migrations(backend_root)
    pending = _pending_chain(chain, current_revision, target_revision)
    versions = backend_root / VERSIONS_DIR
    reports = [analyze_file(versions / f"{c.revision}.py") for c in pending]
    flagged = [r for r in reports if r.data_loss_risk]
    if flagged:
        return MigrationStepResult(
            step=STEP_IMPACT, state=MigrationStepState.FAIL,
            summary="known data-loss risk detected; the sequence refuses to proceed",
            detail="; ".join(r.render() for r in flagged),
        )
    return MigrationStepResult(
        step=STEP_IMPACT, state=MigrationStepState.PASS,
        summary=f"{len(pending)} pending revision(s) carry no known data-loss risk",
    )


def step_backup(
    recovery: RecoveryService, engine: Engine, workspace: pathlib.Path, backup_id: str
) -> tuple[MigrationStepResult, BackupSet | None]:
    try:
        backup = recovery.create_backup(engine, workspace, backup_id)
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        return MigrationStepResult(
            step=STEP_BACKUP, state=MigrationStepState.FAIL,
            summary="pre-migration backup could not be taken", detail=str(exc),
        ), None
    return MigrationStepResult(
        step=STEP_BACKUP, state=MigrationStepState.PASS,
        summary=f"backup {backup.manifest.backup_id} taken at schema "
                f"{backup.manifest.schema_revision!r}",
    ), backup


def step_dry_run(
    backend_root: pathlib.Path, workspace: pathlib.Path,
    backup: BackupSet, target_revision: str,
) -> tuple[MigrationStepResult, Engine | None]:
    scratch_path = workspace / f"{backup.manifest.backup_id}.dry_run.db"
    scratch_engine: Engine | None = None
    try:
        scratch_engine = create_persistence_engine(sqlite_url(scratch_path))
        # Restore the pre-migration image into the scratch target, then apply
        # the candidate migration there - the real target is never touched.
        restore_database(backup.image, scratch_engine)
        run_upgrade(sqlite_url(scratch_path), backend_root, target_revision)
    except Exception as exc:  # noqa: BLE001
        if scratch_engine is not None:
            scratch_engine.dispose()
        return MigrationStepResult(
            step=STEP_DRY_RUN, state=MigrationStepState.FAIL,
            summary="the candidate migration failed against a scratch copy",
            detail=str(exc),
        ), None
    reached = applied_revision(scratch_engine)
    if reached != target_revision:
        scratch_engine.dispose()
        return MigrationStepResult(
            step=STEP_DRY_RUN, state=MigrationStepState.FAIL,
            summary=f"dry run reached {reached!r}, expected {target_revision!r}",
        ), None
    return MigrationStepResult(
        step=STEP_DRY_RUN, state=MigrationStepState.PASS,
        summary=f"candidate migration reaches {target_revision!r} on a scratch copy",
    ), scratch_engine


def step_integrity(backup: BackupSet, scratch_engine: Engine) -> MigrationStepResult:
    image_engine = create_persistence_engine(sqlite_url(backup.image))
    try:
        backup_sound = integrity_check(image_engine)
    finally:
        image_engine.dispose()
    scratch_sound = integrity_check(scratch_engine)
    if backup_sound != "ok" or scratch_sound != "ok":
        return MigrationStepResult(
            step=STEP_INTEGRITY, state=MigrationStepState.FAIL,
            summary="integrity check failed",
            detail=f"backup={backup_sound!r} scratch_post_migration={scratch_sound!r}",
        )
    return MigrationStepResult(
        step=STEP_INTEGRITY, state=MigrationStepState.PASS,
        summary="backup and post-migration scratch copy both report ok",
    )


def step_candidate_migration(
    backend_root: pathlib.Path, backup: BackupSet, target_revision: str
) -> MigrationStepResult:
    chain = declared_migrations(backend_root)
    if not is_forward_only(chain):
        return MigrationStepResult(
            step=STEP_CANDIDATE_MIGRATION, state=MigrationStepState.FAIL,
            summary="declared chain is not forward-only",
        )
    revisions = [c.revision for c in chain]
    if target_revision not in revisions:
        return MigrationStepResult(
            step=STEP_CANDIDATE_MIGRATION, state=MigrationStepState.FAIL,
            summary=f"target revision {target_revision!r} is not in the declared chain",
        )
    known = backup.manifest.schema_revision
    if known is not None and known in revisions:
        if revisions.index(known) > revisions.index(target_revision):
            return MigrationStepResult(
                step=STEP_CANDIDATE_MIGRATION, state=MigrationStepState.FAIL,
                summary="target revision precedes the backed-up revision; "
                        "this sequence only ever moves forward",
            )
    return MigrationStepResult(
        step=STEP_CANDIDATE_MIGRATION, state=MigrationStepState.PASS,
        summary=f"declared chain of {len(chain)} revision(s) is linear and forward-only",
    )


def step_application_tests(
    scratch_engine: Engine, request: MigrationSafetyRequest
) -> MigrationStepResult:
    try:
        passed = request.application_tests(scratch_engine)
    except Exception as exc:  # noqa: BLE001
        return MigrationStepResult(
            step=STEP_APPLICATION_TESTS, state=MigrationStepState.FAIL,
            summary="application tests raised", detail=str(exc),
        )
    if not passed:
        return MigrationStepResult(
            step=STEP_APPLICATION_TESTS, state=MigrationStepState.FAIL,
            summary="application tests reported failure against the migrated scratch copy",
        )
    return MigrationStepResult(
        step=STEP_APPLICATION_TESTS, state=MigrationStepState.PASS,
        summary="application tests pass against the migrated scratch copy",
    )


def step_apply(
    pep: PolicyEnforcementPoint, approval_gate: WorkflowApprovalGate,
    backend_root: pathlib.Path, target_revision: str, request: MigrationSafetyRequest,
) -> MigrationStepResult:
    policy_request = PolicyRequest(
        operation_class=APPLY_OPERATION,
        trust_tier=TRUST_TIER,
        actor=ACTOR,
        targets_real_or_stable_data=request.targets_real_or_stable_data,
        recorded_human_gates=tuple(sorted(request.human_gates.accepted_human_gates)),
    )
    decision = pep.evaluate(policy_request)
    if decision.decision is Decision.DENY:
        return MigrationStepResult(
            step=STEP_APPLY, state=MigrationStepState.BLOCKED,
            summary=f"policy DENY: {decision.reason}",
        )
    if (
        request.targets_real_or_stable_data
        and decision.required_human_gate is not None
        and decision.required_human_gate not in request.human_gates.accepted_human_gates
    ):
        return MigrationStepResult(
            step=STEP_APPLY, state=MigrationStepState.BLOCKED,
            summary=f"{decision.required_human_gate} required and not recorded; "
                    "APPLY to real or stable data is refused",
        )
    if not approval_gate.is_enforced_approval(
        decision=request.human_decision, actor=request.human_actor,
        approval_revision_hash=request.human_approval_revision_hash,
        current_revision_hash=target_revision,
    ):
        return MigrationStepResult(
            step=STEP_APPLY, state=MigrationStepState.BLOCKED,
            summary="no enforced human approval recorded for this exact target revision",
        )
    try:
        run_upgrade(request.database_url, backend_root, target_revision)
    except Exception as exc:  # noqa: BLE001
        return MigrationStepResult(
            step=STEP_APPLY, state=MigrationStepState.FAIL,
            summary="apply raised against the real target", detail=str(exc),
        )
    return MigrationStepResult(
        step=STEP_APPLY, state=MigrationStepState.PASS,
        summary=f"applied to {target_revision!r}, approved by {request.human_actor!r}",
    )


def step_verify(
    engine: Engine, target_revision: str, verifier: Verifier
) -> MigrationStepResult:
    reached = applied_revision(engine)
    if reached != target_revision:
        return MigrationStepResult(
            step=STEP_VERIFY, state=MigrationStepState.FAIL,
            summary=f"real target reports {reached!r}, expected {target_revision!r}",
        )
    sound = integrity_check(engine)
    if sound != "ok":
        return MigrationStepResult(
            step=STEP_VERIFY, state=MigrationStepState.FAIL,
            summary=f"real target integrity check reports {sound!r}",
        )
    if not verifier(engine):
        return MigrationStepResult(
            step=STEP_VERIFY, state=MigrationStepState.FAIL,
            summary="post-migration verifier reports the target does not hold "
                    "the expected state",
        )
    return MigrationStepResult(
        step=STEP_VERIFY, state=MigrationStepState.PASS,
        summary=f"real target verified at {target_revision!r}",
    )


def step_rollback_point(
    recovery: RecoveryService, workspace: pathlib.Path, backup: BackupSet
) -> tuple[MigrationStepResult, str | None]:
    scratch = workspace / f"{backup.manifest.backup_id}.rollback_proof.db"
    expected = backup.manifest.schema_revision

    def _pre_migration_state(engine: Engine) -> bool:
        return applied_revision(engine) == expected

    try:
        recovery.prove_by_restore(backup, scratch, _pre_migration_state)
    except Exception as exc:  # noqa: BLE001
        return MigrationStepResult(
            step=STEP_ROLLBACK_POINT, state=MigrationStepState.FAIL,
            summary="pre-migration backup could not be proven as a rollback point",
            detail=str(exc),
        ), None
    return MigrationStepResult(
        step=STEP_ROLLBACK_POINT, state=MigrationStepState.PASS,
        summary=f"backup {backup.manifest.backup_id} proven restorable to "
                f"{expected!r}; recorded as the rollback point",
    ), backup.manifest.backup_id


def resolve_target_revision(backend_root: pathlib.Path, requested: str) -> str:
    return head_revision(backend_root) if requested == "head" else requested
