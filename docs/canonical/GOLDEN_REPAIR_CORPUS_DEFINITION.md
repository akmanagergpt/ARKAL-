# ARKALI GENESIS v2 — GOLDEN REPAIR DEFECT CORPUS DEFINITION (PHASE 0B)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1
**Canonical basis:** Build Protocol §Phase 0B — "Golden Repair defect corpus **definition**"; Master Specification §Golden Repair Benchmark.

## Scope boundary (read this first)

The canonical set splits this requirement in two, and Phase 0B owns only the first half.

| Obligation | Owner phase | Delivered here |
|---|---|---|
| Corpus **definition**: schema, defect classes, versioning rule, hashing rule, injection contract, unrepairable-defect rule, PASS conditions | **Phase 0B** | **yes — this document** |
| Corpus **instantiation**: concrete defects injected into a specific accepted Golden Product revision, versioned and content-hashed | **Phase 30** | **no — cannot exist yet** |

Master Specification defines the corpus as "a versioned, content-hashed set of **injected** defects" and states the benchmark "is executed against a Golden Product revision that has already passed acceptance". Injection requires a target; no accepted Golden Product exists before Phase 30. Phase 0B therefore defines the corpus; Phase 30 instantiates and hashes it.

Nothing here is a populated corpus, and nothing here should be read as one.

---

## 1. Corpus entry schema

```yaml
corpus_entry:
  id: str                    # CORPUS-<class>-<nnn>, immutable
  defect_class: enum         # one of the eight canonical classes (§2)
  title: str
  injection_target: enum     # source_module | test | schema | lockfile | migration | route_contract
  injection_strategy: str    # deterministic, replayable transformation
  expected_detection: [str]  # test ids/tiers that MUST fail once injected
  repairable: bool           # false for the mandatory unrepairable entry
  budget_profile: str        # reference to declared budget set for the run
  rationale: str             # why this defect class matters
```

## 2. Canonical defect classes (minimum set — all eight required)

| # | Class | Injection target | Must be caught by |
|---|---|---|---|
| 1 | contract violation | source module | T4 contract |
| 2 | state-machine invalid transition | source module | T6 property |
| 3 | permission-check removal | source module | T9 security |
| 4 | persistence-not-committed | source module | T11 persistence |
| 5 | API/frontend contract drift | route contract | T4 + T10 E2E |
| 6 | dependency/lock mismatch | lockfile | T1 static / build |
| 7 | migration/model mismatch | migration | T5 integration |
| 8 | boundary / off-by-one | source module | T3 unit |

The corpus may exceed these classes; it may never contain fewer.

## 3. Versioning and hashing rules

- Corpus version is `MAJOR.MINOR` — MAJOR on any change to an existing entry, MINOR on addition of a new entry.
- The corpus is content-hashed (SHA-256) over the canonical serialisation of all entries, sorted by `id`.
- The hash is recorded in the benchmark evidence artifact for every run.
- Entry IDs are immutable; a retired entry is marked `RETIRED` and retained.

## 4. The mandatory unrepairable entry

Exactly one entry (minimum) carries `repairable: false`. It exists to prove **bounded non-convergence**: the engine must reach a terminal `ESCALATED` state within budget rather than retry indefinitely. A benchmark that only rewards successful repair would certify an unbounded repairer, so repair success without bounded-escalation evidence is FAIL.

The unrepairable entry must be genuinely unrepairable within the declared budget — not merely difficult — and its rationale must state why.

## 5. Injection contract

1. Injection targets an **accepted** Golden Product revision, never ARKALI core.
2. Injection is deterministic and replayable from the entry definition plus the target revision hash.
3. The pre-injection test suite must be green; the expected-detection tests must fail after injection. An entry whose expected-detection tests do not fail is an invalid entry, not a passing repair.
4. Injection never modifies acceptance tests.

## 6. PASS conditions (restated from the canonical benchmark, not redefined)

Every repairable defect resolved within its declared budget · zero regressions in the pre-existing accepted suite · no acceptance test weakened, deleted or rewritten · every repair evidence-backed with root-cause record and repair fingerprint · the unrepairable defect terminally `ESCALATED` within budget · corpus content hash recorded in evidence.

## 7. Immutability during a run

The corpus is never modified to obtain PASS. Corpus modification to obtain PASS is a canonical release blocker.

## 8. Phase 0B delivery statement

This definition is complete and testable as a definition. The instantiated corpus is **NOT_APPLICABLE at Phase 0B** — it has no valid injection target until an accepted Golden Product exists at Phase 30. This is recorded as such in the requirement register and the evidence index; it is not recorded as PASS.
