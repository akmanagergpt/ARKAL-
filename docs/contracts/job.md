# C-19 — Durable job record + checkpoint

**Owner:** `execution.durable` · **Producer:** job runtime · **Consumers:** scheduler, workflow, operations
**Kind:** DB+INT · **Versioning:** **semver** · **Compatibility:** **STRICT** · **Phase:** 7
**Verified by:** `execution.durable` — durable restart evidence

All fields above are the `CONTRACT_INVENTORY.md` row for C-19, not a restatement.
Where this document and the code or the canonical set disagree, they win and this
document is the defect.

## 0. Scope of this revision — Phase 7 Atomic Package 3

Package 1 defined the persistence foundation: the durable job record, its
idempotency identity and the checkpoint record. Package 2 added the durability
semantics: execution attempts with an ownership and heartbeat record, a
persisted retry bound with row-derived accounting, an absolute per-attempt
deadline, cancellation and dead-lettering. **Package 3 adds the job-type
contract registry, pause/resume, and the crash-recovery sweep.**

Still **not** implemented, not claimed, and not represented by an unused column:
**approvals/signals**, and everything the boundary in §5 disclaims. A column that
exists for a behaviour that does not is a claim, and STRICT compatibility
permits adding optional fields later with a defined absent-value meaning, so
nothing is lost by waiting.

**No Phase 7 requirement is discharged by this package.** `ARK-REQ-0060` is now
mechanically *evaluable*, which is not the same as discharged: no traceability
record, no phase report and no gate run exist, and `ARK-REQ-0059`/`ARK-REQ-0061`
carry a `chaos` evidence obligation whose formal tier begins at **Phase 31**.
The restart evidence below is real deterministic fault injection at the
available tier; it is not the T12 corpus and `ARK-REQ-0327` is not claimed.

## 0.1 `ARK-REQ-0060` applicability

The Appendix A rule is `job_type.supports_pause == true` **in the job-type
contract registry**. Before Package 3 that registry did not exist, so the rule
was **unevaluable**, and governing rule 7 of `REQUIREMENT_REGISTER.md` resolves
an unwaived unevaluable rule to **APPLICABLE**. Declining to build the registry
therefore never avoided the requirement — it only left the question
unanswerable. Package 3 makes it answerable from persisted data.

`durable_job_type` is the **only** authority for that answer. It is not read
from a request body, a caller identity, a UI affordance or the job's current
lifecycle state, and an unregistered type raises rather than defaulting: an
absent row is an unanswered question, and converting it to `false` would decide
something nobody declared.

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

**This context chooses between declared transitions; it never adds one.** On a
failed attempt the job moves `RUNNING → FAILED`, then to `RECOVERABLE` when the
recorded bound leaves another attempt and to `DEAD_LETTER` when it does not.
Both are edges the machine already declares, and it evaluates each one, so
retry exhaustion cannot bypass the machine.

Properties that follow from the canonical relation rather than from code here,
and are asserted as such:

- **`DEAD_LETTER` has no outgoing transition.** A dead-lettered job cannot be
  retried at all, silently or otherwise, until canonical authority declares an
  edge out of it.
- **`CANCELLED` is reachable only from `RUNNING`.** A queued job cannot be
  cancelled, and a terminal job cannot be cancelled again.
- **`RESUMING` has exactly two predecessors, `PAUSED` and `RECOVERABLE`.** Pause
  and crash recovery therefore share one lifecycle meaning because the canonical
  relation says so, not because this contract arranges it.
- **`RUNNING → RECOVERABLE` is not declared and `evaluate` refuses it.**

### 3.1 The two paths through `RESUMING`

Both are read off the canonical relation, not chosen here:

| Path | Route | Owner |
|---|---|---|
| Pause | `RUNNING → PAUSED → RESUMING → RUNNING` | `JobRecovery.pause` / `.resume` |
| Crash recovery | `RUNNING → FAILED → RECOVERABLE → RESUMING` | `JobRecovery.recover_lost_executions` |

`EXECUTION_AND_CAPABILITY.md` §3 says a `RUNNING` job without a live heartbeat
"transitions to `RECOVERABLE`, then `RESUMING`". It names the states a crashed
job resolves **to**; `STATE_MACHINES.md` §3 owns the **edges** it travels, and
`RUNNING → RECOVERABLE` is not one of them. The route through `FAILED` is the
only one the relation declares, and it is exactly the disposition Package 2
already owns — so recovery composes that path rather than repeating it, and the
canonical machine was not modified.

**There is one `RESUMING` and one meaning.** No pause-specific or
recovery-specific resuming state exists, no `is_resuming` flag exists, and
nothing records the *origin* of a resume in a way that decides transition
legality.

### 3.2 Pause leaves the attempt open; recovery closes it

A paused execution is **suspended**, not lost. Its attempt stays open under the
same owner, with the same absolute `deadline_at` and the same position in the
retry budget. Closing it would consume an attempt — and pausing is not failing —
while extending its deadline would reset the timeout basis the job was admitted
under. Resume therefore returns to exactly the attempt that was interrupted, and
a job paused for longer than its attempt timeout is timed out on resume by the
ordinary Package 2 rule.

A crashed execution **is** lost, so recovery closes its attempt through the
Package 2 failure path. That is what makes the departed owner unable to act: a
closed attempt refuses every write, so a zombie worker cannot heartbeat,
complete or fail the execution it lost. The consumed attempt is honest
accounting — the attempt really did happen and really did stop.

A **paused** job is deliberately silent and is never swept. Recovery selects
`RUNNING` jobs only, so pausing does not expose a job to being "recovered".

## 4. Records this contract owns

| Record | Fields |
|---|---|
| `durable_job` | `job_id` (PK) · `job_type` · `idempotency_key` · `lifecycle_state` · `payload` (JSON) · `max_attempts` · `attempt_timeout_seconds` · `heartbeat_timeout_seconds` · `created_at` · `updated_at` — unique (`job_type`, `idempotency_key`) |
| `job_checkpoint` | `job_id` (PK, FK → `durable_job`) · `sequence` (PK) · `payload` (JSON) · `recorded_at` |
| `job_execution_attempt` | `job_id` (PK, FK → `durable_job`) · `attempt` (PK) · `owner` · `started_at` · `heartbeat_at` · `deadline_at` · `ended_at` · `outcome` · `detail` |
| `durable_job_type` | `job_type` (PK) · `supports_pause` · `registered_at` |

A control reads this table against the mapped columns, so the mapping cannot
drift into two descriptions of the same thing. The control **derives** the
record set from the context's mapped classes rather than naming them, so a
record added later cannot escape it.

**The job-type registry is joined by the natural key, not by a foreign key.**
`durable_job_type.job_type` is the same value `durable_job.job_type` already
carries — the key idempotency is scoped by. A foreign key would make
registration a *precondition of submitting*, which is admission control, and
admission is C-21 at Phase 8. An unregistered type instead fails closed at the
point its capability is asked about.

**Declaration is write-once.** Re-declaring a registered type is refused rather
than overwritten, so a job admitted while its type supported pause cannot have
that capability changed underneath it. Canonical authority declares no
versioning or mutation semantics for this registry, so none is invented.

**Three timing terms, three different questions.** They are not
interchangeable, and Package 2 shipped one under a name that promised another
(F-0036):

| Term | Question | Basis |
|---|---|---|
| `attempt_timeout_seconds` → `deadline_at` | has this attempt run too **long**? | elapsed work, absolute instant |
| `heartbeat_timeout_seconds` → `heartbeat_at` | has this execution stopped **reporting**? | silence since last proof of life |
| `max_attempts` | may another attempt be opened? | `count(job_execution_attempt)` |

A worker can fall silent long before its deadline, and a worker that is very
much alive can pass one. Crash recovery keys on the **heartbeat** term, per
`EXECUTION_AND_CAPABILITY.md` §3; `JobExecution.timed_out` keys on the deadline.

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

## 4.1 What the recovery sweep decides, and what it must not

The sweep decides that an execution **is gone**. That is a durability judgement
made from persisted facts — recorded owner, recorded heartbeat, recorded bound —
against the injected clock.

It does **not** decide who should run the job next, in what order, with what
priority, on what resources, or whether there is capacity to run it at all. It
leaves a recovered job in `RESUMING` for someone to pick up, and picking up is
`execution.scheduler` / C-21 at **Phase 8**. A structural control fails on the
scheduling vocabulary appearing anywhere in this context.

**Idempotent by construction, not by a guard.** A recovered job is no longer
`RUNNING` and no longer has an open attempt, so it cannot match the selection
twice. The sweep returns the ids it resolved, so a second sweep returning empty
is observable rather than assumed.

## 5. What this contract does NOT own

- **Scheduling, admission, worker allocation, ownership and resource budget.**
  That is **C-21** / `execution.scheduler` at **Phase 8**. Nothing here queues,
  claims, leases or admits; `submit` records a job and returns. The job-type
  registry holds one durability capability per type and no worker class,
  concurrency limit, resource profile or TRUST tier.
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
