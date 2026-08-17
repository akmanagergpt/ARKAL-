"""Migration safety sequence orchestrator (ARK-REQ-0151, ARK-REQ-0336, ARK-REQ-0152).

Owner: `lifecycle.recovery` (Protected Core).

THE NINE STEPS ARE ORCHESTRATED, NOT DECLARED AS A NEW MACHINE.
`docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md` section
"Migration safety" fixes the sequence: Impact -> Backup -> Dry Run ->
Integrity -> Candidate Migration -> Application Tests -> Apply -> Verify ->
Rollback Point. This is a plain ordered composition of already-accepted
authorities, not a thirteenth canonical state machine - `STATE_MACHINES.md`
declares exactly twelve and this module adds none. `BackupRestore` (its
section 9) is reused unmodified through `RecoveryService`. The nine step
implementations live in `migration_safety_steps.py`; this module only decides
what runs next and when to stop (split under the module logical-line budget,
ADR-0008 decomposition).

WHY A `Protocol` INSTEAD OF IMPORTING `acceptance.engine`. The Apply step needs
one fact only `acceptance.engine.GovernanceState` currently derives: which
human gates carry a recorded acceptance. A direct import would add the edge
`lifecycle.recovery -> acceptance.engine`, and `acceptance.engine`'s own
existing chain (`acceptance.engine -> control.specification ->
control.architecture -> kernel.contracts`) already measures 4 of 4 - the
canonical ceiling. Attaching `lifecycle.recovery` in front of it would measure
5. `HumanGateSource` (`migration_safety_types.py`) is therefore a structural
`Protocol`: the composition root (a test, or a future surface) constructs a
real `GovernanceState` and passes it in, and this module never imports
`arkali.acceptance` at all - the same shape Phase 16's `product_generation.py`
and Phase 19's `pipeline.py` used against `engineering.candidate` for the
identical reason.

KNOWN DATA-LOSS RISK STOPS THE WHOLE SEQUENCE, NOT ONLY APPLY. VDC section
"Migration safety": "Known data-loss risk blocks release." A risk detected at
Impact therefore refuses at Impact - every later step is reported `BLOCKED`
rather than silently skipped, so the record stays complete, but nothing after
Impact ever runs. `acceptance.engine` enforces the same property independently
over the whole shipped migration chain (ARK-REQ-0337); this is the sequence's
own, narrower refusal for one candidate run.

APPLY IS NEVER `require_auto`. `SECURITY_ARCHITECTURE.md` section 2 fixes
`APPLY_MIGRATION` to ASK_USER at TRUST-0/1 unconditionally - there is no tier
at which it is AUTO. A caller therefore cannot ask this module to apply a
migration unattended; it must already hold a genuine human decision, passed to
the already-accepted `WorkflowApprovalGate` (`control.policy`, composed
unmodified - the same reuse Phase 19's `execution_gate.py` made for its own
`control.policy`-owned requirement, with the "revision" it binds to being the
resolved target migration revision instead of a workflow-graph revision).
Targeting real or stable data additionally requires `HUMAN_GATE_6` to already
carry a recorded acceptance (read through `HumanGateSource`, never inferred):
an ordinary local human decision authorises a dev/test apply, but never a
real-or-stable-data one on its own.
"""

from __future__ import annotations

import pathlib

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.kernel.persistence.migrations import applied_revision
from arkali.lifecycle.recovery.backup_service import RecoveryService
from arkali.lifecycle.recovery.migration_safety_steps import (
    resolve_target_revision,
    step_application_tests,
    step_apply,
    step_backup,
    step_candidate_migration,
    step_dry_run,
    step_impact,
    step_integrity,
    step_rollback_point,
    step_verify,
)
from arkali.lifecycle.recovery.migration_safety_types import (
    MigrationSafetyRequest,
    MigrationSafetyResult,
    MigrationStepResult,
    MigrationStepState,
    remaining_blocked,
)

__all__ = [
    "MigrationSafetyRequest",
    "MigrationSafetyResult",
    "MigrationSafetySequence",
]


class MigrationSafetySequence:
    """Runs the nine-step VDC "Migration safety" sequence for one target.

    Construct with real, already-loaded authorities. Nothing here loads its
    own copy of the authority map or the PDP - the composition root does that
    once, the same discipline `test_recovery_lifecycle.py` already uses for
    `RecoveryService`.
    """

    def __init__(
        self,
        pep: PolicyEnforcementPoint,
        approval_gate: WorkflowApprovalGate,
        recovery: RecoveryService,
        backend_root: pathlib.Path,
    ) -> None:
        self._pep = pep
        self._approval = approval_gate
        self._recovery = recovery
        self._backend_root = backend_root

    def run(self, request: MigrationSafetyRequest) -> MigrationSafetyResult:
        target = resolve_target_revision(self._backend_root, request.target_revision)
        current = applied_revision(request.engine)
        steps = [step_impact(self._backend_root, current, target)]
        if steps[-1].state is not MigrationStepState.PASS:
            return self._stopped(target, steps)

        backup_step, backup = step_backup(
            self._recovery, request.engine, request.workspace, request.backup_id
        )
        steps.append(backup_step)
        if backup_step.state is not MigrationStepState.PASS or backup is None:
            return self._stopped(target, steps)

        dry_run_step, scratch_engine = step_dry_run(
            self._backend_root, request.workspace, backup, target
        )
        steps.append(dry_run_step)
        if dry_run_step.state is not MigrationStepState.PASS or scratch_engine is None:
            return self._stopped(target, steps)

        try:
            steps.append(step_integrity(backup, scratch_engine))
            if steps[-1].state is not MigrationStepState.PASS:
                return self._stopped(target, steps)

            steps.append(step_candidate_migration(self._backend_root, backup, target))
            if steps[-1].state is not MigrationStepState.PASS:
                return self._stopped(target, steps)

            steps.append(step_application_tests(scratch_engine, request))
            if steps[-1].state is not MigrationStepState.PASS:
                return self._stopped(target, steps)
        finally:
            scratch_engine.dispose()

        steps.append(step_apply(self._pep, self._approval, self._backend_root, target, request))
        if steps[-1].state is not MigrationStepState.PASS:
            return self._stopped(target, steps)

        steps.append(step_verify(request.engine, target, request.post_migration_verifier))
        if steps[-1].state is not MigrationStepState.PASS:
            return self._stopped(target, steps)

        rollback_step, rollback_id = step_rollback_point(
            self._recovery, request.workspace, backup
        )
        steps.append(rollback_step)
        return MigrationSafetyResult(
            target_revision=target, steps=tuple(steps),
            rollback_point_backup_id=rollback_id,
        )

    @staticmethod
    def _stopped(
        target: str, steps: list[MigrationStepResult]
    ) -> MigrationSafetyResult:
        complete = list(steps) + remaining_blocked(steps)
        return MigrationSafetyResult(target_revision=target, steps=tuple(complete))
