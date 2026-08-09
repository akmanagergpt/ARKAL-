# C-03 — Persistence base schema + migration contract

**Owner:** `kernel.persistence` · **Definition phase:** 2 · **Implementation phase:** 5
**Compatibility:** STRICT · **Versioning:** migration-numbered
**Verified by:** `lifecycle.recovery` — migration + restore evidence (restore evidence is Phase 5 Package 2; not claimed here)

This document is the prose half of C-03. The executable half is
`backend/arkali/kernel/persistence/` and `backend/alembic/`. Where the two
disagree, the code and the canonical set win and this document is the defect.

`CONTRACT_INVENTORY.md` names this file and `backend/alembic/` as C-03's
location. It closes the C-03 portion of **DEF-008**; the remaining contract
schema files stay deferred.

## 1. What the contract fixes

Defined at Phase 2 in `schema_contract.py` and **not redefined** by the
implementation:

| Type | Fixes |
|---|---|
| `PersistedEntityContract` | the fields every persisted entity must expose — `entity`, `owning_context`, `primary_key`, `immutable_fields`, `content_hashed` |
| `MigrationContract` | the shape of a migration — `revision`, `down_revision`, `direction`, `requires_backup`, `requires_human_gate_6_on_real_data` |
| `MigrationDirection` | `FORWARD` · `ROLLBACK_POINT` |
| `SupportsRepository` | the engine-neutral repository surface — `get`, `put` |

## 2. Engine (ARK-REQ-0011)

SQLite + WAL, local-first. `create_persistence_engine` is the **only** place an
engine is constructed. On a SQLite dialect it attaches a connect listener
applying, in order:

| Pragma | Value | Why |
|---|---|---|
| `journal_mode` | `WAL` | ARK-REQ-0011 |
| `foreign_keys` | `ON` | SQLite disables constraint enforcement by default; without this a referential test passes for the wrong reason |
| `synchronous` | `FULL` | makes close/reopen durability evidence meaningful rather than incidental |

**WAL is verified, not asserted.** `journal_mode(connection)` re-reads the
pragma from a live connection, so the evidence is the database's own answer. An
in-memory database truthfully answers `memory`; a negative control depends on
that, because a probe that could only ever answer `wal` would prove nothing.

A non-SQLite URL gets no listener and no pragma. There is one dialect branch in
the entire context, and it is that one.

## 3. Base schema

One table, `persisted_entity_contract`, holding the stored form of
`PersistedEntityContract`. Its columns are reconciled against the Pydantic
model's fields by a control, so the two cannot become separate descriptions of
the same thing.

Types are `String`, `Boolean` and `JSON` — rendered by SQLite and PostgreSQL
alike. Constraint names come from an explicit naming convention so they are
deterministic across engines; Alembic cannot generate a stable downgrade
without one.

**Applied-revision state has one store.** That is Alembic's `alembic_version`
table. Nothing in `kernel.persistence` keeps a second copy.

## 4. Repository abstraction (ARK-REQ-0012)

`SqlRepository` implements `SupportsRepository` using the SQLAlchemy expression
language against mapped columns. It contains no `text()`, no string
concatenation into SQL and no dialect branch.

`put` refuses a key that disagrees with the entity's own key attribute rather
than silently preferring one of them, because either choice would store
something the caller did not ask for.

**The confinement is enforced.** `tests/structural/test_engine_confinement.py`
parses real imports with `ast` and fails if any module outside
`kernel.persistence` imports a database package or emits raw SQL. It also
asserts the owning context *does* use the engine, so the rule cannot pass
vacuously. It is a test rather than a ninth architecture gate because the eight
gates are declared in `AUTHORITY_MAP.yaml`, and adding one would mean an
implementing actor editing canonical authority to admit its own work.

**PostgreSQL operation is not claimed.** ADR-0006 registers the abstraction as
MANDATORY and verified PostgreSQL operation as *not* a canonical requirement. No
PostgreSQL driver is installed on this host; the driver-dependent control is
reported **NOT_CONFIGURED** and skipped, while the driver-independent control —
that the URL resolves to a non-SQLite dialect — runs.

## 5. Migrations

Forward-only with a recorded rollback point (`ARCHITECTURE.md` §10). Runtime
database files are never committed; `.gitignore` already excludes `*.db`,
`*.db-wal` and `*.db-shm`. Migrations are always committed.

`migrations.py` builds one `MigrationContract` per revision file, read from the
file itself. It **fails closed**: a revision whose declared identity disagrees
with its filename, a chain with two roots, a branched chain, an orphaned
revision, or a file declaring no direction is refused rather than run.

The database URL is never written into `alembic.ini`. `env.py` takes it from the
Alembic config or `ARKALI_DATABASE_URL` and refuses to migrate an unspecified
target. `env.py` constructs no engine of its own — it calls
`create_persistence_engine`, so the migration tooling cannot bypass the single
construction point.

### Out of scope here

- **HUMAN GATE 6.** `APPLY_MIGRATION` is fixed to
  `HUMAN_GATE_6_ON_REAL_OR_STABLE_DATA` in the authority map, and
  `MigrationContract` carries `requires_human_gate_6_on_real_data`. Both are
  `control.policy` decisions at layer rank 1, unreachable from rank 0. The flag
  is carried and surfaced; the decision belongs to the call site.
- **The nine-step migration safety sequence** is ARK-REQ-0151 / ARK-REQ-0336 at
  Phase 20.
- **Backup and restore** are ARK-REQ-0153 / ARK-REQ-0335, owned by
  `lifecycle.recovery`, and are not implemented by this package.

## 6. Layering

`kernel.persistence` is layer rank 0. `kernel.contracts` is also rank 0,
`allow_same_layer` is false and no sibling edge between them is declared, so the
canonical error taxonomy is **not reachable** from this context. Configuration
faults therefore raise built-in exceptions rather than `ArkaliError` subclasses.
Declaring a sibling edge would widen the accepted architecture to fit an
implementation, which is what ERR-003 and the F-0028 repair both refused.

For the same reason there is **no PDP import**. Whether a write is permitted is
a `control.policy` decision at rank 1; enforcement belongs at a call site in a
higher layer. This module governs transaction boundaries only.
