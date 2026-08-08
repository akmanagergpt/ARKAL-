# ARKALI GENESIS v2 — FORMAL STATE-MACHINE INVENTORY (PHASE 0A)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1

Every entity below has exactly one state-machine authority. Transitions not listed are structurally impossible — rejected by the transition validator, not by convention. `DRAFT → STABLE` and equivalents cannot be expressed.

---

### 1. Project — authority `control.registry.project`
States: `DRAFT`, `SPECIFIED`, `ACTIVE`, `SUSPENDED`, `ARCHIVED`
Transitions: DRAFT→SPECIFIED→ACTIVE; ACTIVE↔SUSPENDED; {ACTIVE,SUSPENDED}→ARCHIVED
Forbidden: DRAFT→ACTIVE, ARCHIVED→any

### 2. Candidate — authority `engineering.candidate`, promotion by `lifecycle.release`
States: `CREATED`, `ASSEMBLING`, `ASSEMBLED`, `VERIFYING`, `ACCEPTED`, `REJECTED`, `PROMOTED`, `EXPIRED`
Transitions: CREATED→ASSEMBLING→ASSEMBLED→VERIFYING→{ACCEPTED,REJECTED}; ACCEPTED→PROMOTED; {ASSEMBLED,ACCEPTED}→EXPIRED
Forbidden: **CREATED→PROMOTED**, **VERIFYING→PROMOTED**, REJECTED→any, PROMOTED→any
Invariant: `PROMOTED` requires an `ACCEPTED` predecessor with an evidence set; core candidates additionally require HUMAN GATE 2.

### 3. Job — authority `execution.durable`
States: `QUEUED`, `RUNNING`, `CHECKPOINTED`, `PAUSED`, `RESUMING`, `SUCCEEDED`, `FAILED`, `CANCELLED`, `DEAD_LETTER`, `RECOVERABLE`
Transitions: QUEUED→RUNNING↔CHECKPOINTED; RUNNING→{PAUSED,SUCCEEDED,FAILED,CANCELLED}; PAUSED→RESUMING→RUNNING; FAILED→{DEAD_LETTER,RECOVERABLE}; RECOVERABLE→RESUMING
Invariant: an interrupted job resolves to `RESUMING` or `RECOVERABLE`. Silent disappearance is a verification FAIL.

### 4. Workflow Execution — authority `execution.workflow`
States: `PENDING`, `RUNNING`, `WAITING_SIGNAL`, `WAITING_APPROVAL`, `COMPENSATING`, `SUCCEEDED`, `FAILED`, `CANCELLED`
Transitions: PENDING→RUNNING→{WAITING_SIGNAL,WAITING_APPROVAL,COMPENSATING,SUCCEEDED,FAILED,CANCELLED}; WAITING_*→RUNNING; COMPENSATING→{FAILED,CANCELLED}
Invariant: `WAITING_APPROVAL` advances only on a recorded human approval. No agent, API or workflow path may advance it.

### 5. Provider Health — authority `control.registry.provider`
States: `UNCONFIGURED`, `CONFIGURED`, `HEALTHY`, `DEGRADED`, `UNHEALTHY`, `DISABLED`
Transitions: UNCONFIGURED→CONFIGURED→{HEALTHY,UNHEALTHY}; HEALTHY↔DEGRADED↔UNHEALTHY; any→DISABLED→CONFIGURED
Invariant: this is the **only** store of provider health. `control.capability` holds a reference, never a copy.

### 6. Plugin Lifecycle — authority `engineering.plugin`
States: `DISCOVERED`, `MANIFEST_VALIDATED`, `PERMISSIONS_DECLARED`, `APPROVED`, `ENABLED`, `DISABLED`, `QUARANTINED`, `REMOVED`
Transitions: DISCOVERED→MANIFEST_VALIDATED→PERMISSIONS_DECLARED→APPROVED→ENABLED↔DISABLED; any→QUARANTINED→{DISABLED,REMOVED}
Invariant: permissions are declared using the 14 canonical operation classes; an unmappable permission blocks at `PERMISSIONS_DECLARED`.

### 7. Release — authority `lifecycle.release`
States: `DRAFT`, `BUILT`, `VERIFIED`, `SIGNED_READY`, `RELEASED`, `WITHDRAWN`
Transitions: DRAFT→BUILT→VERIFIED→SIGNED_READY→RELEASED; any pre-RELEASED→WITHDRAWN
Invariant: `RELEASED` requires HUMAN GATE 7 and a complete evidence set.

### 8. Core Upgrade — authority `lifecycle.evolution`, promotion by `lifecycle.release`
States: `SNAPSHOT_TAKEN`, `CANDIDATE_BUILT`, `VERIFYING`, `AWAITING_GATE_2`, `PROMOTED`, `REJECTED`, `ROLLED_BACK`
Transitions: SNAPSHOT_TAKEN→CANDIDATE_BUILT→VERIFYING→{AWAITING_GATE_2,REJECTED}; AWAITING_GATE_2→{PROMOTED,REJECTED}; PROMOTED→ROLLED_BACK
Invariants: entry requires verified Recovery Supervisor (Phase 22B) or the PDP returns DENY; `SNAPSHOT_TAKEN` must produce a restorable snapshot; `ROLLED_BACK` is reachable only via `lifecycle.recovery`.

### 9. Backup/Restore — authority `lifecycle.recovery`
States: `PLANNED`, `BACKUP_RUNNING`, `BACKUP_VERIFIED`, `RESTORE_RUNNING`, `RESTORE_VERIFIED`, `FAILED`
Transitions: PLANNED→BACKUP_RUNNING→{BACKUP_VERIFIED,FAILED}; BACKUP_VERIFIED→RESTORE_RUNNING→{RESTORE_VERIFIED,FAILED}
Invariant: a backup is not `BACKUP_VERIFIED` until proven by an actual restore. File copy alone is FAIL.

### 10. Evolution Campaign — authority `lifecycle.evolution`
States: `DECLARED`, `RUNNING`, `PROMOTED`, `COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN`, `ESCALATED`, `BLOCKED`
Transitions: DECLARED→RUNNING→{PROMOTED, COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN, ESCALATED, BLOCKED}
Invariants: `DECLARED` requires objective, baseline metrics and all six budgets recorded **before** execution; a rejected candidate does not auto-generate a successor; all four exits are terminal — no restart to obtain a different terminal state.

### 11. Hardening Round — authority `acceptance.engine`
States: `DECLARED`, `RUNNING`, `PASS`, `COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN`, `ESCALATED`, `BLOCKED`
Transitions: DECLARED→RUNNING→{PASS, COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN, ESCALATED, BLOCKED}
Invariants: budgets declared before the first candidate; budget exhaustion with intact baseline ⇒ `COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN`, otherwise `ESCALATED`; post-Round-4 regression failure ⇒ `ESCALATED`, never a new round.

### 12. Import Project — authority `engineering.import`
States: `REGISTERED`, `STATICALLY_INSPECTED`, `TIER_ASSIGNED`, `APPROVED_FOR_EXECUTION`, `WORKING_COPY_CREATED`, `REJECTED`
Transitions: REGISTERED→STATICALLY_INSPECTED→TIER_ASSIGNED→APPROVED_FOR_EXECUTION→WORKING_COPY_CREATED; any→REJECTED
Invariants: **no execution before `STATICALLY_INSPECTED`**; tier cannot be reassigned by an implementing actor; the original source is preserved unmodified and independently restorable.

---

## Cross-cutting invariants (property-tested)

1. A stable revision always originates from an `ACCEPTED` candidate.
2. No actor directly mutates stable except `lifecycle.recovery` via `ROLLBACK_STABLE` to a previously verified immutable revision.
3. A DENY decision cannot be bypassed through API, UI, agent, workflow, plugin/connector or computer-use paths.
4. Every mandatory accepted candidate has an evidence set.
5. Restore preserves integrity.
6. Every invalid transition is rejected structurally.
7. Every terminal state is genuinely terminal.
