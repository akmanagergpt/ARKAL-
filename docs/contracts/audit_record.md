# C-15 — Audit record

**Owner:** `evidence.audit` (**Protected Core**) · **Producer:** every auditable action · **Consumers:** audit chain, security review
**Kind:** EVD · **Versioning:** **append-only, semver** · **Compatibility:** **STRICT** · **Phase:** 6
**Verified by:** `evidence.audit` — integrity tests

All fields above are the `CONTRACT_INVENTORY.md` row for C-15, not a restatement.
Where this document and the code or the canonical set disagree, they win and this
document is the defect.

## 1. What this contract owns

`ARCHITECTURE.md` §3 row 12 and its concern table give `evidence.audit` the
**audit chain and evidence integrity**. `VERIFICATION_ARCHITECTURE.md` §2.2 rule
7 states it without qualification: *`evidence.audit` owns the chain; no other
context may write or amend an evidence record.*

An **evidence record** is the `Evidence` node of §2.1 — *record + timestamp +
producer* — carrying the `Result` it yields. This contract owns the record, its
ordering, and the integrity linkage between records. It owns nothing else.

## 2. What it does NOT own

- **Artifact identity and provenance.** That is **C-14**, owned by
  `evidence.artifact`. An evidence record *references* an artifact by its
  content address and never mints, derives or restates one. `evidence.audit`
  computes no artifact hash and holds no artifact metadata beyond the reference.
- **Coverage, verdicts and the evidence graph.** §2.3 coverage computation and
  the Acceptance Engine are **Phase 13** (C-16). This contract stores and
  verifies; it decides nothing about whether a requirement is covered.
- **Policy decisions.** The Phase 4 PEP keeps its own decision trail. A PDP
  decision is not an evidence record, and §11 of this document explains why that
  separation is what stops the chain auditing itself forever.

## 3. Record shape

| Field | Meaning |
|---|---|
| `record_hash` | PK. The record's integrity digest — see §5. Derived, never supplied |
| `sequence` | Position in the chain. Contiguous from 1, unique |
| `previous_hash` | The predecessor's `record_hash`; `NULL` **only** for the genesis record |
| `requirement_id` | The `ARK-REQ` this evidence is reachable from (§2.2 rule 3) |
| `contract_id` | The `C-nn` exercised, where one applies |
| `artifact_id` | FK → `artifact.artifact_id`. The artifact this evidence was produced against (§2.2 rule 2) |
| `test_id` | The `Test` node — identifier plus tier — where one applies |
| `producer` | Who recorded it (§2.1: record + timestamp + **producer**) |
| `result` | The `Result` yielded. One of the canonical `HonestState` values |
| `recorded_at` | The timestamp (§2.1) |
| `supersedes` | FK → `audit_record.record_hash`. The record this one supersedes (§2.2 rule 1) |

`result` is validated against the canonical `HonestState` vocabulary read from
`kernel.contracts.results`, never against a list copied into this context.

## 4. Append-only

§2.2 rule 1: *Evidence is never edited or deleted. A superseded result is
retained with a `supersedes` edge.*

Enforced, not requested:

- the public authority exposes **`append`, `get`, `head`, `records`, `verify`**
  and nothing else. There is no `update`, `amend`, `overwrite`, `replace`,
  `delete` or `purge`, and a control asserts none appears;
- an ORM `before_update` refusal and a `before_delete` refusal on the table, so
  the invariant does not depend on callers choosing not to write;
- correcting an outcome means appending a **new** record that supersedes the old
  one. The superseded record stays visible in `records()` forever.

## 5. Integrity — recomputed, never trusted

`record_hash` is the SHA-256 content address of a canonical serialisation of
every field above **including `previous_hash` and `sequence`**. It is derived by
`evidence.audit` from the record's own content; no caller may supply one.

Because the digest covers the predecessor's digest, the chain is a hash chain:
altering any field of any record changes that record's digest, which breaks the
`previous_hash` of every record after it. `verify()` **recomputes** every digest
from the stored fields and compares — it never reads a stored status flag. There
is no `integrity_verified` boolean anywhere in this contract, and a control
asserts there is not.

`verify()` fails closed and reports the first structural fault it finds:

| Fault | Detected because |
|---|---|
| content or metadata mutation | recomputed digest ≠ stored `record_hash` |
| linkage mutation | `previous_hash` ≠ the predecessor's `record_hash` |
| missing predecessor | a non-genesis record whose `previous_hash` names no record |
| ordering corruption | `sequence` is not contiguous from 1 |
| more than one genesis | two records with `previous_hash IS NULL` |
| self-supersession | a record whose `supersedes` names itself |
| empty chain | reported as verified-empty, never as verified-good |

## 6. Linkage — no structurally orphaned evidence

§2.2 rule 3 says evidence not reachable from an `ARK-REQ` does not count toward
coverage. Counting is Phase 13. The **storage-level** invariant this phase owes
is narrower and is enforced at append time:

- `requirement_id` must be a real id in `REQUIREMENT_REGISTER.md`, the sole
  denominator, read at call time rather than copied here;
- `artifact_id` must reference an artifact `evidence.artifact` has actually
  registered — the foreign key guarantees it, and the append path raises a typed
  refusal rather than a driver error;
- `supersedes`, when present, must name an existing record, must not be the
  record itself, and a record may be superseded only once, so history stays a
  chain rather than a fan.

A record failing any of these never enters the chain.

## 7. Security

Writes request `WRITE_WORKSPACE_FILE`, reads `READ_FILE`, both through the
Phase 4 PEP. The two stable-mutation operation classes are never requested and
are deliberately not named in this context.

Every persisted string passes `assert_no_raw_secret` with sink
`"evidence artifact"` — the sink Phase 4 declared for the evidence path — so no
second secret model exists.

**No self-audit recursion.** Appending an evidence record is a governed write,
so it consults the PEP; the PEP records its decision on its own Phase 4 trail,
which is *not* the C-15 chain. `evidence.audit` never appends an evidence record
about its own append. A control asserts the append path performs exactly one
append.

## 8. Engine neutrality (ARK-REQ-0012, ADR-0006)

Declarative mapping only, on `kernel.persistence.PersistenceBase`. `String`,
`Integer`, `DateTime` and standard constraints, all rendered for SQLite and
PostgreSQL alike. No engine, no driver, no dialect branch, no raw SQL.
