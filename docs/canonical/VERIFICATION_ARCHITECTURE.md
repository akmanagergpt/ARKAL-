# ARKALI GENESIS v2 — VERIFICATION / TEST ARCHITECTURE AND EVIDENCE GRAPH STRATEGY (PHASE 0A)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1
**Scope:** architecture only. No test is implemented in Phase 0.

---

# Part 1 — Verification / test architecture

## 1.1 Test tiers

| Tier | Purpose | Mocks | Owner | From phase |
|---|---|---|---|---|
| T1 static | type check, lint, import hygiene | n/a | `kernel.contracts` | 2 |
| T2 architecture | 8 authority-map gates + budgets, each with a negative-control fixture | n/a | `control.architecture` | 2 |
| T3 unit | single module behaviour | permitted | owning context | 2 |
| T4 contract | producer/consumer conformance per contract family (C-01…C-36) | permitted at boundary | owning context | 2 |
| T5 integration | cross-context behaviour on real persistence | not for the subject | owning context | 5 |
| T6 property | invariants over generated inputs | no | `acceptance.engine` | 3 |
| T7 mutation | tests-of-tests; injected mutations must be caught | no | `acceptance.engine` | 31 |
| T8 fuzz | parsers, security boundaries, AI-output deserializers (mandatory); elsewhere per register rule | no | `acceptance.engine` | 31 |
| T9 security | escape tests per TRUST tier, policy bypass, secret leakage, negative controls | no | `control.policy`, `control.isolation` | 4 |
| T10 browser/E2E | real user journeys via Playwright | no | `surfaces.command` | 5 onward |
| T11 persistence | restart, durability, backup→restore→verify | no | `lifecycle.recovery` | 5 |
| T12 chaos | 12 canonical failure-injection scenarios | no | `acceptance.engine` | 31 |
| T13 real-product | generation through the actual pipeline (Golden suite, generalization, Golden Repair) | **no** | `engineering.factory` | 30 |
| T14 clean-environment | packaged release on the canonical Windows baseline | no | `lifecycle.release` | 36 |

**Mock policy.** Mocks are permitted only in T3/T4. Any tier from T5 upward that substitutes a provider, a sandbox, a database or a generated product produces NOT_CONFIGURED, never PASS. Golden Factory Acceptance requires a real provider or a working local model.

## 1.2 Execution levels

`L1` simulation (controlled failures) · `L2` real execution (source, build, process, DB, browser, runtime) · `L3` clean environment (packaged release on the snapshot baseline). Production PASS requires applicable L2/L3 evidence; simulation alone can never produce it.

Mapping: T1–T9 run at L1/L2 · T10–T13 at L2 · T14 at L3.

## 1.3 Gate topology

```
  per-commit      T1 T2 T3 T4                      (fast; blocks merge)
  per-phase       + T5 T6 T9 T11                   (Phase Gate Checker C3/C4 reads results)
  per-capability  + T10 (if UI) T13 (if factory)   (Acceptance Engine, from Phase 13)
  pre-delivery    + T7 T8 T12 T14                  (Phases 31, 36)
```

**Determinism.** T2, T6, T7 and the Phase Gate Checker must be deterministic: same repository state ⇒ same verdict. Non-deterministic tests are quarantined, never retried-until-green.

**Negative controls are mandatory** for T2 (each of the 8 gates), T7 (mutation must be caught), and T9 (isolation must DENY when a required property is unavailable). A detector that has never detected is not evidence.

## 1.4 What may declare a verdict

| Verdict | Authority |
|---|---|
| test result | the test runner (exit code, recorded) |
| phase gate | Phase Gate Checker (deterministic, Phase 2) |
| capability verdict | Acceptance Engine (Phase 13) |
| release verdict | Release Authority + HUMAN GATE 7 |
| the 8 human gates | human acceptance authority |

No implementing actor may issue, re-score or override any of these. Acceptance contracts are Protected Core.

---

# Part 2 — Evidence graph strategy

## 2.1 Graph shape

```
ARK-REQ ──owns──> Contract ──realised_by──> Artifact ──exercised_by──> Test
   │                                                                     │
   │                                                                 produces
   │                                                                     v
   └────────────────────── covered_by ──────────────────────────────> Evidence ──yields──> Result
```

Node types: `Requirement` (ARK-REQ, immutable ID) · `Contract` (C-nn) · `Artifact` (content hash) · `Test` (id + tier) · `Evidence` (record + timestamp + producer) · `Result` (PASS/FAIL/BLOCKED/NOT_TESTED/NOT_CONFIGURED/UNSUPPORTED/NOT_APPLICABLE).

Edge types: `owns`, `realised_by`, `exercised_by`, `produces`, `covered_by`, `yields`, `supersedes`.

## 2.2 Rules

1. **Append-only.** Evidence is never edited or deleted. A superseded result is retained with a `supersedes` edge.
2. **Content-addressed.** Every Artifact node carries its content hash; every Evidence node references the artifact hash it was produced against.
3. **No orphan evidence.** Evidence not reachable from an ARK-REQ does not count toward coverage.
4. **No orphan requirement.** Every MANDATORY ARK-REQ must be reachable to at least one Result before Production Ready.
5. **Coverage is graph-derived**, computed only from the register denominator. It is never asserted in prose.
6. **Applicability is read, not judged** — a CONDITIONAL requirement resolves via its register rule against recorded system state.
7. **Integrity is Protected Core.** `evidence.audit` owns the chain; no other context may write or amend an evidence record.

## 2.3 Coverage computation

```
mandatory_coverage  = |MANDATORY reqs with ≥1 PASS Result| / |MANDATORY reqs|
conditional_applied = CONDITIONAL reqs whose rule evaluates true (same treatment as MANDATORY)
evidence_coverage   = |required evidence kinds present| / |required evidence kinds declared|
```
Both must equal 100% for Production Ready. `NOT_TESTED`, `NOT_CONFIGURED`, `UNSUPPORTED` and `BLOCKED` count as **not covered**. `NOT_APPLICABLE` removes the requirement from the denominator **only** when its register rule evaluates false.

## 2.4 Phase 0 coverage position

0 of 301 MANDATORY requirements are verified. Phase 0 establishes the denominator and the graph shape; it verifies no capability and claims no coverage.
