# C-19 — Durable job record + checkpoint

**Owner:** `execution.durable` · **Producer:** job runtime · **Consumers:** scheduler, workflow, operations
**Kind:** DB+INT · **Versioning:** **semver** · **Compatibility:** **STRICT** · **Phase:** 7
**Verified by:** `execution.durable` — durable restart evidence

All fields above are the `CONTRACT_INVENTORY.md` row for C-19, not a restatement.
Where this document and the code or the canonical set disagree, they win and this
document is the defect.

## 0. Scope of this revision — Phase 7 Atomic Package 2

Package 1 defined the persistence foundation: the durable job record, its
idempotency identity and the checkpoint record. **Package 2 adds the durability
semantics**: execution attempts with an ownership and heartbeat record, a
persisted retry bound with row-derived accounting, an absolute per-attempt
deadline, cancellation and dead-lettering.

Still **not** implemented, not claimed, and not represented by an unused column:
**pause/resume**, the `supports_pause` job-type registry, the crash-recovery
sweep, and approvals/signals. Those are Package 3 and later. A column that
exists for a behaviour that does not is a claim, and STRICT compatibility
permits adding optional fields later with a defined absent-value meaning, so
nothing is lost by waiting.

Package 2 records what Package 3 will need — `heartbeat_at`, `deadline_at` and a
`RECOVERABLE` disposition — and stops there. It never enters `RESUMING`.

No Phase 7 requirement is discharged by this package.

## 1. Compatibility semantics

**STRICT** means a consumer compiled against version *N* must not be silently
handed a shape it cannot validate. For this contract that resolves to:

- a field may be **added** only as optional with a defined absent-value meaning;
- a field may not be removed, renamed, or have its type or nullability narrowed
  without a **major** version increment;
- `job_id` is identity and never changes meaning;
- a schema change reaches the database only through an Alembic revision, so the
  contract version and the migration chain move together (C-03).

## 2. Identity

A durable job carries **two** identities and they answer different questions.

| Identity | Question it answers | Enforcement |
|---|---|---|
| `job_id` | *which row is this?* | primary key |
| (`job_type`, `idempotency_key`) | *has this work already been submitted?* | unique constraint |

**There is one store for both.** The idempotency identity is a named unique
constraint on the job row, not a second table: it is a fact *about* a job, and a
separate table holding the same fact would be a second place where "does this
work already exist?" is answered — the duplicate authority `MS §Constitution 1`
forbids. `uq_durable_job_idempotency` is the authority, and the pre-insert
lookup in `submit` exists only to return a typed result rather than a driver
error.

**Idempotency is scoped by job type.** The same key under two job types is two
different pieces of work. Scoping keys globally would make an unrelated producer
able to suppress another's job by reusing a string.

**Re-submitting a known key returns the existing job.** It does not create a
second row, does not raise, and does not update the existing row — the recorded
job is whatever the first submission recorded, including its lifecycle state. A
caller that wants a *new* job supplies a new key.

## 3. Lifecycle

`lifecycle_state` is a **recorded value**, never a second transition table. The
`Job` state machine (`STATE_MACHINES.md` §3, implemented at Phase 3 in
`execution/durable/job_state_machine.py`) is the sole authority on whether a move
is legal, and `JobStore.transition` delegates every move to `evaluate`. This
context declares no states, no transition table and no allowed-target set, and a
structural control asserts that.

The initial state is **derived**, not named: it is the single declared state with
no incoming transition, read off the machine's own relation. The store cannot
nominate an initial state the machine does not recognise.

A rejected transition raises the machine's own typed error
(`IllegalTransition`, `ForbiddenTransition`, `TerminalStateEscape`,
`UnknownState`) unchanged, and the row is not touched.

**Package 2 chooses between declared transitions; it never adds one.** On a
failed attempt the job moves `RUNNING → FAILED`, then to `RECOVERABLE` when the
recorded bound leaves another attempt and to `DEAD_LETTER` when it does not.
Both are edges the machine already declares, and it evaluates each one, so
retry exhaustion cannot bypass the machine.

Three properties follow from the canonical relation rather than from code here,
and are asserted as such:

- **`DEAD_LETTER` has no outgoing transition.** A dead-lettered job cannot be
  retried at all, silently or otherwise, until canonical authority declares an
  edge out of it.
- **`CANCELLED` is reachable only from `RUNNING`.** A queued job cannot be
  cancelled, and a terminal job cannot be cancelled again.
- **`RESUMING` is never entered by this package.** Retry disposition stops at
  `RECOVERABLE`, which is exactly what Package 3's recovery needs and no more.

## 4. Records this contract owns

| Record | Fields |
|---|---|
| `durable_job` | `job_id` (PK) · `job_type` · `idempotency_key` · `lifecycle_state` · `payload` (JSON) · `max_attempts` · `attempt_timeout_seconds` · `created_at` · `updated_at` — unique (`job_type`, `idempotency_key`) |
| `job_checkpoint` | `job_id` (PK, FK → `durable_job`) · `sequence` (PK) · `payload` (JSON) · `recorded_at` |
| `job_execution_attempt` | `job_id` (PK, FK → `durable_job`) · `attempt` (PK) · `owner` · `started_at` · `heartbeat_at` · `deadline_at` · `ended_at` · `outcome` · `detail` |

A control reads this table against the mapped columns, so the mapping cannot
drift into two descriptions of the same thing.

**Retry accounting is rows, not a counter.** The attempt count is
`count(job_execution_attempt)`. It therefore cannot be reset by restarting a
process, cannot be set by a caller, and cannot drift from what happened. The
primary key (`job_id`, `attempt`) is also the concurrency backstop: two writers
opening the same next attempt cannot both succeed, whatever the service does.

**The bound and the timeout are recorded on the job.** `max_attempts` and
`attempt_timeout_seconds` are the terms a job was admitted under, so they
survive a restart and cannot be widened by changing a default later.

**The deadline is absolute.** `deadline_at` is computed once, when the attempt
opens, from the injected clock. A remaining-duration counter would silently
restart with the process; an instant does not.

**An attempt is open while `ended_at` is NULL.** At most one may be open at a
time. Closing sets `ended_at` and `outcome` together, and the service refuses to
write to a closed attempt — which is what makes a superseded owner unable to
keep a dead execution looking alive.

**`owner` records who is executing; it does not decide who should.** Refusing a
stale owner is a durability property. Choosing, allocating or balancing owners is
C-21 at Phase 8 and appears nowhere in this contract.

**Checkpoint ordering is identity.** The primary key is (`job_id`, `sequence`),
so two checkpoints cannot claim one position in a job's history and an ordinal
cannot be silently reused. `sequence` is derived from the stored rows, never
supplied by a caller.

**Checkpoints are immutable.** Both `before_update` and `before_delete` are
refused at the ORM. A checkpoint is what a restart reads to decide where work
resumed from; a checkpoint that can be edited or removed is not a durability
record. The job row itself is mutable by design, because the machine declares
non-terminal states and the row follows it.

## 5. What this contract does NOT own

- **Scheduling, admission, worker allocation, ownership and resource budget.**
  That is **C-21** / `execution.scheduler` at **Phase 8**. Nothing here queues,
  claims, leases or admits; `submit` records a job and returns.
- **Workflow graphs and workflow execution.** That is **C-20** /
  `execution.workflow` at **Phase 17**. `execution.workflow → execution.durable`
  is a declared sibling edge; the reverse is forbidden and absent.
- **Artifact identity and the evidence chain.** C-14 and C-15, owned by
  `evidence.artifact` and `evidence.audit`. This package writes neither. When
  checkpoint/progress evidence is actually required, it will call those
  authorities rather than restating them.
- **The durable-restart chaos proof.** `ARK-REQ-0327` is **Phase 31**.
- **The persistence engine.** Built only by `kernel.persistence` (C-03).

## 6. Security

The store performs governed operations and enforces them through the Phase 4
PEP, which is **injected with no default** so a caller cannot obtain a store that
writes without a policy decision. Reads request `READ_FILE`; writes request
`WRITE_WORKSPACE_FILE`. These are the classes `evidence.audit` already uses for
persisted governed operations; no new operation class is invented, and
`unmapped_action_resolution: DENY` means none could be.

`WRITE_STABLE_FILE` and `ROLLBACK_STABLE` are **never** requested by this
context, and a control asserts neither string appears in its source.

A denied decision prevents the operation: the PEP raises and nothing is written.

## 7. Transactions and time

**Transaction boundaries belong to the caller.** Like `ProjectRegistry`,
`ArtifactStore` and `AuditChain`, this service never commits, so a caller cannot
obtain a partially committed store and a failed unit of work leaves no row.

**The clock is injected.** Timestamps come from a supplied callable defaulting to
UTC now, so time-dependent behaviour in later packages is testable without
sleeping. Package 1 records timestamps but decides nothing from them.

## 8. Engine neutrality (ARK-REQ-0012, ADR-0006)

Declarative mapping only: `String`, `Integer`, `DateTime`, `JSON` and standard
constraints, all of which SQLAlchemy renders for SQLite and PostgreSQL alike. No
PRAGMA, no raw SQL, no dialect branch, no engine construction. PostgreSQL remains
**unexercised** and this document does not claim otherwise.
