# C-12 — Project / revision record

**Owner:** `control.registry.project` · **Producer:** registry · **Consumers:** `engineering.factory`, `engineering.candidate`, `lifecycle.release`
**Kind:** DB+INT · **Versioning:** semver · **Compatibility:** **STRICT** · **Phase:** 5
**Verified by:** `control.registry.project` — state-machine tests

All fields above are the `CONTRACT_INVENTORY.md` row for C-12, not a restatement.
Where this document and the code or the canonical set disagree, they win and
this document is the defect.

## 1. Compatibility semantics

**STRICT** means a consumer compiled against version *N* must not be silently
handed a shape it cannot validate. For this contract that resolves to:

- a field may be **added** only as optional with a defined absent-value meaning;
- a field may not be removed, renamed, or have its type or nullability narrowed
  without a **major** version increment;
- `project_id` and `revision_id` are identity and never change meaning;
- a schema change reaches the database only through an Alembic revision, so the
  contract version and the migration chain move together (C-03).

Versioning is semver over the record shape. The migration chain is numbered
separately — a shape change implies a migration, but a migration does not imply
a shape change.

## 2. What this contract owns

Identity, and only identity:

| Record | Fields |
|---|---|
| `project` | `project_id` (PK) · `name` (unique) · `lifecycle_state` · `created_at` · `updated_at` |
| `project_revision` | `revision_id` (PK) · `project_id` (FK → `project`) · `sequence` · `created_at` · `provenance_ref` (nullable) |

**Not owned, deliberately:**

- **The lifecycle relation.** `STATE_MACHINES.md` §1 and the executable Project
  machine are the authority. `lifecycle_state` is a recorded value; the registry
  calls `StateMachine.evaluate` and records the outcome. It declares no states,
  no transitions and no comparisons against either — a control reads the
  deployed source and fails if any state name appears as a literal.
- **Content-addressed revision identity and provenance.** The dependency matrix
  assigns those to `evidence.artifact` at **Phase 6**. `provenance_ref` is a
  nullable reference to a record that does not exist yet. No hash is computed
  here, so no second provenance authority is created.
- **Candidate assembly** (`engineering.candidate`, Phase 12) and **stable
  promotion / rollback** (`lifecycle.release`, `lifecycle.recovery`). A
  `CandidateRevision` and a `StableRevision` are not this record.

## 3. Identity is enforced by the database

Uniqueness and referential integrity are real constraints, not pre-insert
queries — a check-then-insert loses to a concurrent writer:

| Guarantee | Mechanism |
|---|---|
| project identity unique | `pk_project` |
| project name unique | `uq_project_name` |
| revision identity unique | `pk_project_revision` |
| revision belongs to a real project | `fk_project_revision_project_id_project` |
| one revision per ordinal per project | `uq_revision_project_sequence` |

The service also raises typed errors (`DuplicateIdentity`, `UnknownProject`) so
callers get a meaningful failure, but every one of those checks has a database
constraint behind it, each proven by a control that bypasses the service.

The foreign key is only enforced because C-03 turns `foreign_keys=ON` on every
SQLite connection; without it SQLite would accept an orphan silently.

## 4. Revision immutability

`ARCHITECTURE.md` §7: revisions are immutable and a change creates a new one.
A `before_update` listener on the revision mapper raises
`ImmutableRevisionViolation`, so immutability does not depend on callers
choosing not to write, and the registry exposes no revision-update method.

**Honest limit.** This confines the ORM path. A raw `UPDATE` would bypass it —
but raw SQL outside `kernel.persistence` is itself forbidden by ADR-0006 and
proven absent by `test_engine_confinement.py`, so the two controls compose. A
database-level trigger would be engine-specific and is therefore **not** claimed
at Phase 5.

The canonical mutable/immutable split is preserved: the **project** record is
mutable through its state machine, the **revision** record is not.

## 5. Layering

`control.registry.project` is layer rank 1. It depends on `kernel.persistence`
and `kernel.contracts` (both rank 0) and on nothing else.

**No `control.policy` import.** The F-0028 repair made that edge canonically
legal, but the higher-layer surface that would carry an authorisation decision
does not exist yet. Fabricating it here would place a future surface in the
wrong context, so the registry contract stays clean and the decision stays with
the caller.

**No secret material.** The records carry identity, lifecycle state, timestamps
and a provenance reference. A control asserts no column name matches a
secret-shaped term.

**Engine-neutral (ARK-REQ-0012).** Declarative mapping and the expression
language only — no PRAGMA, no raw SQL, no dialect branch, no engine
construction. Exactly one module in this context imports the kernel error
taxonomy, because a second importer pushed `kernel.contracts.errors` past its
fan-in budget; ADR-0008 makes decomposition the response to a budget.

## 6. Transactions

The caller owns the transaction via the C-03 `unit_of_work`. `ProjectRegistry`
never commits, so a caller cannot obtain a partially committed registry, and a
failure anywhere in the block rolls back every write in it.
