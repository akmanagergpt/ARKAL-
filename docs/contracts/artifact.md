# C-14 — Artifact descriptor + provenance record

**Owner:** `evidence.artifact` · **Producer:** every artifact producer · **Consumers:** acceptance, release, export
**Kind:** ART · **Versioning:** **content-addressed + semver** · **Compatibility:** **STRICT** · **Phase:** 6
**Verified by:** `evidence.artifact` — provenance evidence

All fields above are the `CONTRACT_INVENTORY.md` row for C-14, not a restatement.
Where this document and the code or the canonical set disagree, they win and this
document is the defect.

## 1. Compatibility semantics

**STRICT** means a consumer compiled against version *N* must not be silently
handed a shape it cannot validate. For this contract that resolves to:

- a field may be **added** only as optional with a defined absent-value meaning;
- a field may not be removed, renamed, or have its type or nullability narrowed
  without a **major** version increment;
- `artifact_id` is identity and never changes meaning;
- a schema change reaches the database only through an Alembic revision, so the
  contract version and the migration chain move together (C-03).

Two versioning axes coexist and are not the same thing. **Content addressing**
identifies a *byte sequence*: the same bytes always yield the same
`artifact_id`, on any host, in any order. **Semver** versions the *shape of this
contract*. Changing the record's fields is a semver event; changing an artifact's
bytes is not a version of that artifact at all — it is a different artifact.

## 2. Identity — content addressing

`artifact_id` is the canonical content address, rendered
`<algorithm>:<lowercase hex digest>` — for example
`sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.

Rules, each enforced by executable control rather than convention:

1. **Derived, never supplied.** No caller may present an `artifact_id`. It is
   computed from the bytes by `content_address.address_of`. A store that accepted
   a caller-supplied identity would let identity and content disagree, which is
   the one thing content addressing exists to prevent.
2. **Deterministic.** Identical bytes produce an identical address across
   processes and hosts. The digest is of the raw bytes; no timestamp, no
   filename, no host fact participates.
3. **Total.** Every byte sequence has an address, including the empty one.
4. **Collision-visible.** Registering different bytes under an existing address
   is impossible by construction (the address is derived), and registering the
   *same* bytes twice is idempotent, returning the existing record rather than a
   duplicate.
5. **Verifiable after the fact.** `verify` re-reads the stored bytes, recomputes
   the address and compares. A single flipped byte changes the digest and is
   reported as `ArtifactContentMismatch`. The record is never repaired to match
   the bytes: a mismatch is a finding, not a maintenance task.

`hash_algorithm` and `digest` are stored as separate columns as well as in the
composed `artifact_id`, so a consumer can select by algorithm without parsing a
string, and so an algorithm migration remains expressible.

## 3. Immutability

An artifact record and its provenance record are **immutable once persisted**.
Enforcement is an ORM `before_update` refusal on both tables, raising
`ArtifactImmutabilityViolation` — the same mechanism `control.registry.project`
uses for revisions (`ARCHITECTURE.md` §7). It does not depend on callers
choosing not to write.

Immutability here is stronger than for a project revision, and deliberately so:
a revision may legitimately supersede another, whereas an artifact whose bytes
changed is by definition a *different* artifact with a *different* address.
There is no update path and no "supersede" edge on this contract.

## 4. Records this contract owns

| Record | Fields |
|---|---|
| `artifact` | `artifact_id` (PK, content address) · `hash_algorithm` · `digest` · `byte_size` · `normalization` · `created_at` |
| `artifact_provenance` | `artifact_id` (PK, FK → `artifact`) · `producer_agent` · `provider_model` · `task_id` · `specification_version` · `context_hash` · `tests` (JSON) · `evidence` (JSON) · `recorded_at` |
| `artifact_parent` | `artifact_id` (FK) · `parent_artifact_id` (FK) · `position` — PK (`artifact_id`, `parent_artifact_id`) |

The eleven metadata items `MS §Artifact Fabric` and `VDC §Provenance` both name
map onto these columns exactly:

| Canonical metadata | Where it lives |
|---|---|
| content hash | `artifact.artifact_id`, `hash_algorithm`, `digest` |
| producer agent | `artifact_provenance.producer_agent` |
| provider/model | `artifact_provenance.provider_model` |
| task ID | `artifact_provenance.task_id` |
| specification version | `artifact_provenance.specification_version` |
| context hash | `artifact_provenance.context_hash` |
| parent artifacts | `artifact_parent` edges |
| normalization | `artifact.normalization` |
| tests | `artifact_provenance.tests` |
| evidence | `artifact_provenance.evidence` |
| timestamps | `artifact.created_at`, `artifact_provenance.recorded_at` |

A control reads this table against the mapped columns, so the mapping cannot
drift into two descriptions of the same thing.

**Parent artifacts are real edges, not a JSON list.** A foreign key means a
parent must exist before a child can claim it, so a provenance chain cannot
reference an artifact that was never registered. `position` preserves declared
order without making order part of identity.

## 5. What this contract does NOT own

- **The audit / evidence integrity chain.** That is **C-15**, owned by
  `evidence.audit`, which is Protected Core. `VERIFICATION_ARCHITECTURE.md` §2.2
  rule 7 is explicit: `evidence.audit` owns the chain and no other context may
  write or amend an evidence record. `artifact_provenance.evidence` holds
  *references*, never chain records, and nothing in `evidence.artifact` appends
  to an audit chain.
- **Evidence-graph computation, coverage and verdicts.** `VERIFICATION_ARCHITECTURE.md`
  §2.3 coverage and the Acceptance Engine are **Phase 13** (C-16). This contract
  supplies the `Artifact` node; it computes nothing over the graph.
- **Project and revision identity.** That is C-12, owned by
  `control.registry.project`. `evidence.artifact` sits at layer rank 2 and
  `control.registry.project` at rank 1, so the resolution direction is one-way:
  this context may read a revision's `provenance_ref`, and the registry may never
  import this one.
- **Release manifests, SBOM and signing.** `VDC §Provenance` requires a release
  manifest with cryptographic hashes; that is C-31 at **Phase 26**.
- **Blob lifecycle beyond registration.** No deletion, no garbage collection, no
  compaction. An artifact store that can delete is not append-only.

## 6. Storage and security

Bytes are stored under a workspace root at a path derived from the address, so
the filesystem layout *is* the index and a misfiled blob is impossible to
address. Every write is a governed operation: the store requires
`WRITE_WORKSPACE_FILE` through the Phase 4 PEP before touching the filesystem.

`WRITE_STABLE_FILE` and `ROLLBACK_STABLE` are **never** requested by this
context, and a control asserts neither string appears in its source.

Secrets never enter an artifact or provenance record. Every persisted string
field is passed through `control.policy.secret_reference.assert_no_raw_secret`
with sink `"evidence artifact"` — the guard Phase 4 already declared for exactly
this boundary — so no second secret model exists here.

## 7. Engine neutrality (ARK-REQ-0012, ADR-0006)

Declarative mapping only: `String`, `Integer`, `DateTime`, `JSON` and standard
constraints, all of which SQLAlchemy renders for SQLite and PostgreSQL alike. No
PRAGMA, no raw SQL, no dialect branch, no engine construction. The engine is
built only by `kernel.persistence`, and `test_engine_confinement.py` fails if
that stops being true.

PostgreSQL remains **unexercised**, and this document does not claim otherwise.
The requirement is the abstraction, not verified operation on another engine.
