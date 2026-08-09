# ARKALI GENESIS v2 — CROSS-SESSION HANDOFF MANIFEST

> ## THIS DOCUMENT IS AN INDEX, NOT AN AUTHORITY
>
> It exists so a new session — ChatGPT, Claude, Gemini, DeepSeek, Qwen, Kimi, a
> local model, or a human engineer — can rebuild context from the repository
> without depending on conversation memory.
>
> **It cannot override, amend, reinterpret or substitute for:**
> the four canonical source documents · `REQUIREMENT_REGISTER.md` ·
> `AUTHORITY_MAP.yaml` · the accepted ADRs · `HUMAN_GATE_RECORDS.md` ·
> `BUILD_STATE.md` · `PHASE_HISTORY.md` · accepted Git history.
>
> **If this document and authoritative repository state disagree, the repository
> wins and continuation MUST STOP with `HANDOFF_DRIFT`.** Run
> `python scripts/check_handoff.py` to detect that mechanically.
>
> **Chat history is advisory only.** Nothing may be claimed as done without
> repository evidence.

---

## 1. Project identity

| Field | Value |
|---|---|
| Project | ARKALI GENESIS v2 |
| Mission | A local-first professional **Engineering Control Fabric**: converts natural-language goals into canonical requirements, orchestrates specialised engineering agents over multiple AI providers, executes work in isolated durable environments, and independently verifies results with executable evidence |
| Repository root | `C:\Users\lenovo\Desktop\ARKALI` (path is environment-specific; the repository itself is portable) |
| Branch | `main` |
| Current HEAD | `d9b8af47495c5dda6e486615a24f6568a3c1c6be` |
| Canonical stack | Python 3.13 · FastAPI · Pydantic v2 · SQLAlchemy 2.x · Alembic · pytest — React · TypeScript · Vite · Tailwind — Tauri 2.x — SQLite+WAL local-first, PostgreSQL-ready abstractions |

## 2. Authoritative source index

**Canonical set — never modify without an explicit human ruling:**

```
docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md
docs/CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md
docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md
docs/ARKALI_GENESIS_V2_START_COMMAND.txt
```

**Accepted Phase 0 governance (Human Gate 1):**

```
docs/canonical/REQUIREMENT_REGISTER.md          sole requirement denominator
docs/canonical/AUTHORITY_MAP.yaml               machine-readable authority map
docs/canonical/ARCHITECTURE.md                  layers, contexts, dependency rules
docs/canonical/SECURITY_ARCHITECTURE.md         PDP/PEP, TRUST tiers, Protected Core
docs/canonical/STATE_MACHINES.md                12 state machines
docs/canonical/EXECUTION_AND_CAPABILITY.md      capability graph, durable execution
docs/canonical/CONTRACT_INVENTORY.md            36 contract families
docs/canonical/VERIFICATION_ARCHITECTURE.md     test tiers, evidence graph
docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md  phase order + gates
docs/canonical/PHASE_GATE_CHECKER.md            checker specification
docs/canonical/GOLDEN_REPAIR_CORPUS_DEFINITION.md
docs/canonical/CLEAN_TEST_BASELINE.md
docs/adr/ADR_INDEX.md                           9 ADRs, all ACCEPTED and immutable
```

**Live governance state:**

```
docs/acceptance/HUMAN_GATE_RECORDS.md    human decisions + ERR-001 erratum
docs/build/BUILD_STATE.md                current phase status
docs/build/PHASE_HISTORY.md              phase outcomes and commits
docs/build/OPEN_BLOCKERS.md              open findings and deferrals
docs/build/KNOWN_FAILURES.md             recorded defects, historical values
docs/build/DECISION_LOG.md               decisions + human rulings
docs/acceptance/EVIDENCE_INDEX.md        EV-0001 .. EV-0050
```

**Executable governance (run these, do not trust prose):**

```
scripts/run_phase_gate.py                   Phase Gate Checker entry point
scripts/check_handoff.py                    this manifest vs repository truth
scripts/check_repository_structure.py       + _negative.py
scripts/check_phase_graph.py                + _negative.py
scripts/check_phase0_deliverables.py
backend/                                    pytest suite (1139 passed, 13 skipped)
backend/tests/surfaces/                     Command Center API integration (T5)
backend/tests/persistence/                  T11 persistence: real SQLite, WAL, durability, migrations
backend/tests/structural/                   ARK-REQ-0012 confinement, ARK-REQ-0229 vertical-slice
                                            linkage, contract drift, frontend boundaries,
                                            frontend stack, T10 harness integrity
backend/tests/security/                     PDP, PEP, isolation, secrets, drift
backend/tests/governance/test_handoff_drift.py  handoff negative controls
backend/tests/governance/test_dependency_rules.py  dependency-rule reconciliation (F-0028)
backend/tests/state_machines/               12 machines + canonical reconciliation
backend/tests/capability/                   C-13 schema + pre-activation behaviour
frontend/tests/                             vitest component tier (23)
frontend/tests/e2e/                         T10 Playwright journey (9), real Chromium
scripts/run_command_center.py               binds the real app to a socket for T10
```

**Tracked root documentation — holds no governed value, never an authority:**

```
ARKALI_NEW_SESSION_PROMPT.txt        new-session bootstrap prompt
ARKALI_YENI_OTURUM_DEVAM_NOTU.md     session-continuation note (Turkish)
```

Neither file may be read as authority. Where either disagrees with the
repository, the repository wins.

## 3. Current verified state

| Item | Value |
|---|---|
| Phase 0A / 0B | **ACCEPTED** (one package, Human Gate 1) |
| Phase 1 | **MACHINE-ACCEPTED** |
| Phase 2 | **MACHINE-ACCEPTED** |
| Phase 3 | **MACHINE-ACCEPTED** |
| Phase 4 | **MACHINE-ACCEPTED** — superseding verdict, **RATIFIED** under GOV-001; the defective first revision is retained as `phase_4_report_rev1_defective.json` |
| Phase 5 | **MACHINE-ACCEPTED** — verdict `PHASE_ACCEPTED_BY_MACHINE` (`docs/acceptance/phase_5_report.json`, `phase_5_traceability.json`). C1–C6 PASS, PROTECTED_CORE **COMPLETE** (the change set touched `lifecycle.recovery`, so `select_profile` required security review, adversarial review and full regression — all executed at exit 0). Five atomic packages: C-03 persistence, C-12 registry, minimal backup/restore, the Command Center API, and the React/TypeScript/Vite/Tailwind frontend. **First real T10** in this build |
| Phase 6 | **UNLOCKED — NOT_STARTED** ← current work. Artifact / Evidence Plane (C-14, C-15). Unlocked by the Phase 5 gate run returning `progression: PERMITTED` |
| Human Gates | `HUMAN_GATE_1` ACCEPTED. Gates 2–8 not reached |
| ADRs | 9 **ACCEPTED**, 0 PROPOSED — immutable; supersession needs a new ADR, and Gate 2 for Protected Core ADRs |
| Requirements | **313** total — 303 MANDATORY / 8 CONDITIONAL / 2 OPTIONAL |
| Cumulative verified | **72** MANDATORY (5 Phase 1 + 23 Phase 2 + 4 Phase 3 + 33 Phase 4 + **7 Phase 5**), reconciled by check C6 against `phase_4_traceability.json` and `phase_5_traceability.json` |
| BLOCKER / HIGH | **0 / 0** (derived by the validator from declared Status cells) |
| MEDIUM / LOW | tracked, non-blocking — **the count is held by `OPEN_BLOCKERS.md`, not mirrored here.** No mechanically derived total exists: the residual set is prose, so any number written here would be a transcription that re-rots on the next finding (F-0002, F-0011). Read the file |
| Recorded findings | every finding through **F-0031** is closed |
| Authority conflicts | **0** (39 concerns, one owner each) |
| Architecture violations | **0** (8 gates PASS over **64** real cross-context edges; all **9** numeric budgets measured under ratified contract 1.0.0). The direction gate now consumes `dependency_rules` rather than modelling it (F-0028) |
| State machines | **12** implemented, one per declared authority, reconciled against `STATE_MACHINES.md` on every run |
| Capability Graph | **schema only**; every query returns `NOT_CONFIGURED`; activation is Phase 9B (ADR-0003) |
| Security | one PDP · 14 operation classes · 5 TRUST tiers · 7 properties · 7 backends probed · Protected Core, Secret Vault and Local-Only boundaries enforced |
| Host isolation | TRUST-0/1 satisfiable. **TRUST-2/3/4 UNSUPPORTED** on this host (`NET_EGRESS_CONTROL`, `KERNEL_ISOLATION` unavailable). Re-probe; never assume |
| Execution surfaces | **one exists: `surfaces.command`** (Command Center API — seven routes — plus its React frontend, Phase 5). Every route enforces through the Phase 4 PEP and is audited, and a real browser journey drives it end to end. The other five canonical paths — sandbox, scheduler, durable, workflow, operations — are absent. End-to-end bypass resistance across all six (ARK-REQ-0325, 0347) is Phase 31 and is **not** claimed |
| Working tree | clean at HEAD |

## 4. Accepted commit history

| # | Commit | Meaning |
|---|---|---|
| 1 | `d8572dd` | canonical greenfield baseline |
| 2 | `4f9213f` | deterministic line endings |
| 3 | `079c925` | canonical architecture repair — 9 BLOCKER + 16 HIGH fixed before Phase 0 |
| 4 | `85f3c1c` | Phase 0 candidate rev 1 — REJECTED (HG1-01…04) |
| 5 | `5c6a28d` | Phase 0 candidate rev 2 — REJECTED (HG1-05…09) |
| 6 | `63ab9a8` | Phase 0 candidate rev 3 — REJECTED (HG1-10…12) |
| 7 | `007ebf6` | Phase 0 candidate rev 4 — **ACCEPTED** |
| 8 | `3378054` | **HUMAN GATE 1 ACCEPTED** — ADRs PROPOSED→ACCEPTED, Phase 1 unlocked |
| 9 | `0ad45a7` | Phase 1 candidate — NOT ACCEPTED (F-0015) |
| 10 | `1ae0835` | **ERR-001 erratum + Phase 1 MACHINE-ACCEPTED** |
| 11 | `76edd26` | **Phase 2 MACHINE-ACCEPTED** |
| 12 | `fc239ff` | cross-session handoff protocol; fixes F-0016 |
| 13 | `a08af56` | handoff manifest refreshed to committed HEAD (§12 rule) |
| 14 | `74a9ccf` | **F-0017** — vacuous handoff negative control repaired |
| 15 | `e323c67` | session-continuation note tracked as documentation |
| 16 | `fc8c98d` | handoff manifest refreshed after note tracking (§12 rule) |
| 17 | `85cbcda` | pre-Phase-3 governance hygiene: GH-001/002/003 |
| 18 | `c69d1dd` | handoff manifest refreshed after hygiene (§12 rule) |
| 19 | `4321611` | **PHASE 3 MACHINE-ACCEPTED** — 12 state machines, C-13 schema |
| 20 | `bd38bb6` | handoff manifest refreshed after Phase 3 acceptance (§12 rule) |
| 21 | `39d1c34` | **ERR-002 + ERR-003** — Phase 3 human rulings applied; 3 budget violations repaired |
| 22 | `5fa4d90` | handoff manifest refreshed after the errata (§12 rule) |
| 23 | `1ea79f3` | **PHASE 4 MACHINE-ACCEPTED** — PDP/PEP, isolation, Protected Core, secrets, Local-Only. Later found **DEFECTIVE** (F-0024) |
| 24 | `191958d` | handoff manifest refreshed after Phase 4 acceptance (§12 rule) |
| 25 | `6d6296d` | **F-0024 reopened** — ARK-REQ-0111 discharged without an implementation; Phase 5 blocked |
| 26 | `0bf585c` | handoff manifest refreshed after F-0024 (§12 rule) |
| 27 | `765bb07` | **ERR-004 remediation** — ARK-REQ-0111 implemented, finding parser fixed, **Phase 4 re-accepted** |
| 28 | `e5e36bd` | handoff manifest refreshed after the remediation (§12 rule) |
| 29 | `bd41b34` | **GOV-001** — superseding re-acceptance rule; Phase 4 re-acceptance ratified |
| 30 | `552c80f` | handoff manifest refreshed after GOV-001 (§12 rule) |
| 31 | `c99cf14` | **F-0026 closed** — GOV-001 enforced in the acceptance path |
| 32 | `161b4a2` | handoff manifest refreshed after F-0026 closure (§12 rule) |
| 33 | `d933869` | **F-0027 + F-0028 closed** — pre-Phase-5 structural governance repair; no Phase 5 functionality |
| 34 | `da27863` | handoff manifest refreshed after F-0027/F-0028 (§12 rule) |
| 35 | `11ebf14` | **PHASE 5 PACKAGE 1** — `kernel.persistence` C-03 foundation (ARK-REQ-0011, 0012); F-0029 closed. **Not a phase acceptance** |
| 36 | `0b93587` | handoff manifest refreshed after Package 1 (§12 rule) |
| 37 | `3c116f2` | **PHASE 5 PACKAGE 2** — C-12 Project/Revision Registry persistence; F-0030 closed. **Not a phase acceptance** |
| 38 | `b7f0ff8` | handoff manifest refreshed after Package 2 (§12 rule) |
| 39 | `7406cef` | **PHASE 5 PACKAGE 3 (PARTIAL)** — WAL-safe backup/restore *mechanics* in `kernel.persistence` |
| 40 | `21c1b9a` | handoff manifest refreshed after the partial checkpoint (§12 rule) |
| 41 | `fb9000e` | **PHASE 5 PACKAGE 3 COMPLETE** — minimal backup/restore under `lifecycle.recovery`; A→B→restore→verify proven |
| 42 | `2148610` | handoff manifest refreshed after Package 3 (§12 rule) |
| 43 | `884db7e` | **PHASE 5 PACKAGE 4 (PARTIAL)** — Command Center API under `surfaces.command`. Frontend **not** built |
| 44 | `1880449` | handoff manifest refreshed after the partial checkpoint (§12 rule) |
| 45 | `6ab0692` | **PHASE 5 PACKAGE 4 COMPLETE** — the frontend increment and the ARK-REQ-0229 vertical-slice linkage control. Not a phase acceptance |
| 46 | `4ff5004` | handoff manifest refreshed after Package 4 (§12 rule) |
| 47 | `3edc171` | **PHASE 5 MACHINE-ACCEPTED** — Package 5: real T10 browser journey, evidence records, traceability, phase report and the gate run. **Phase 6 unlocked.** F-0031 opened and closed |
| 48 | `d9b8af4` | handoff manifest refreshed after Phase 5 acceptance (§12 rule) ← HEAD at generation |

Rejected candidates are preserved unamended. They are evidence, not noise.

## 5. Important human / governance decisions

Referenced, not duplicated. Read the cited artifact before relying on any of these.

| Decision | Authority |
|---|---|
| Eight canonical HUMAN GATES; normal phases are machine-accepted | `CLAUDE_..._BUILD_PROTOCOL.md` §Canonical HUMAN GATES |
| Gate 8 — architecture-budget exception | Build Protocol; `AUTHORITY_MAP.yaml` `architecture_budgets` |
| No direct Stable mutation by any actor | Master Spec Constitution rule 6 |
| `ROLLBACK_STABLE` — Recovery Supervisor only, verified immutable target, no transformation | Master Spec §ROLLBACK_STABLE |
| Phase 0A + 0B are one acceptance package under one gate | Master Spec §Canonical Implementation Phases |
| Canonical workflow graph is sole authority; derived caches hash-bound | ADR-0004 |
| Provider/Model Registry is sole provider authority; graph holds references | ADR-0001, Master Spec §Provider and Agent separation |
| Isolation Backends provide *properties*, not technologies; unsatisfiable ⇒ UNSUPPORTED/DENY | ADR-0002, `SECURITY_ARCHITECTURE.md` |
| Protected Core membership and modification path | ADR-0005, Master Spec §Protected Core |
| Direct-AI benchmark states; `NOT_CONFIGURED`/`EXTERNAL_UNAVAILABLE` do not block release | Verification Contract §Direct-AI benchmark |
| **`engineering.import` logical identity retained; physical package is `engineering/project_import`** | **ERR-001** in `HUMAN_GATE_RECORDS.md` |
| **Plugin `REMOVED` is terminal; reintroduction starts a new lifecycle instance** | **ERR-002** in `HUMAN_GATE_RECORDS.md` |
| **Every numeric architecture budget has one ratified measurement formula; the gate reads it as data** | **ERR-003** in `HUMAN_GATE_RECORDS.md`; `AUTHORITY_MAP.yaml` `architecture_budget_measurement` |
| **The PDP receives isolation posture as an injected fact, never by importing `control.isolation`** — both are layer rank 1 and `allow_same_layer: false` | `DECISION_LOG.md`; `SECURITY_ARCHITECTURE.md` §1 |
| **`ROLLBACK_STABLE` is DENY for every actor** until a verified Recovery Supervisor exists (Phase 22B) | `DECISION_LOG.md`; `pdp.py::_rollback_rule` |

## 6. Current environment

Re-detected at generation. **Re-detect rather than trusting these values.**

| Tool | State | Terminology |
|---|---|---|
| Python 3.12.10 | present | PASS for structural work |
| Python 3.13 (canonical target) | absent | **NOT_CONFIGURED** |
| Node 24.18.0 / npm 11.16.0 | present | PASS |
| TypeScript 5.6 / Vite 5.4 / React 18 / Tailwind 3.4 / Vitest 2.1 | installed (`frontend/node_modules`) | PASS — typecheck clean, 23 tests pass, production build succeeds |
| Rust / Cargo / rustc | absent | **UNSUPPORTED** |
| Git 2.55.0 | present | PASS |
| ruff | absent | **NOT_CONFIGURED** |
| mypy 2.3.0 | present | PASS (strict, clean) |
| poetry / uv / pip-tools | absent | **NOT_CONFIGURED** (no Python lockfile) |
| pytest 9.1.1 · pydantic 2.8.0 · PyYAML 6.0.3 | present | PASS |
| SQLAlchemy 2.0.51 · Alembic 1.18.5 · FastAPI 0.111.0 | present | PASS — the Phase 5 backend stack is executable |
| SQLite library 3.49.1 (WAL-capable) | present | PASS |
| hypothesis (T6 property tier) | absent | **NOT_CONFIGURED** |
| Playwright 1.62.1 + Chromium 151.0.7922.34 (T10 browser/E2E) | installed | **PASS** — 9 browser tests green against the production build and a live API. Firefox and WebKit are NOT installed; no cross-browser claim |

No unavailable toolchain may be reported as PASS.

## 7. Open items

| Item | Reference |
|---|---|
| 0 BLOCKER, 0 HIGH | `OPEN_BLOCKERS.md` |
| MEDIUM / LOW findings are tracked and non-blocking; **the file holds the count, this index does not** | `OPEN_BLOCKERS.md` |
| **F-0027 closed** — structure check 12 was phase-scoped and would have rejected legitimate Phase 5 constructs in the context canonical architecture assigns them to. Now scoped by authority: a runtime construct may be built only inside its owning context, resolved from `ARCHITECTURE.md` §3 against `AUTHORITY_MAP.yaml`, over tracked **and** untracked files, failing closed on unresolvable authority or ownership. Sixth instance of the phase-scoped-check family | `KNOWN_FAILURES.md` · `OPEN_BLOCKERS.md` |
| **F-0030 closed** — Package 1's engine-confinement control banned the `sqlalchemy` import outside `kernel.persistence`, stricter than ARK-REQ-0012, which forbids *engine-specific* SQL while ADR-0006 places SQLite "behind SQLAlchemy 2.x repositories". It would have refused C-12 its declarative mapping. Restated to the canonical property and **strengthened**: drivers, `sqlalchemy.dialects*` and engine-construction calls are now named and confined. MEDIUM, failing in the **rejecting** direction | `KNOWN_FAILURES.md` · `OPEN_BLOCKERS.md` |
| **F-0029 closed** — `check_handoff.py`'s current-phase derivation required both `UNLOCKED` and `NOT_STARTED`, the only two states that existed while every phase shipped in one commit. Phase 5 is the first delivered in atomic packages, so a truthful "IN PROGRESS, NOT ACCEPTED" made it invisible. The derivation now selects the single `UNLOCKED` phase that `PhaseStatus.is_accepted` reports as not accepted. Seventh instance of the family; MEDIUM, failing in the **detecting** direction | `KNOWN_FAILURES.md` · `OPEN_BLOCKERS.md` |
| **F-0028 closed** — `ForbiddenDependencyDirectionGate` never consumed `dependency_rules`, so it rejected the two exceptions `ARCHITECTURE.md` §4 rules 5 and 6 grant (`policy_callable_from_any_layer`, `evidence_write_from_any_layer`). `AuthorityMap` now parses the section and owns `edge_permitted()`. Failed **closed**, so no accepted phase is affected. No `control.policy` import was added anywhere and no sibling edge was introduced | `KNOWN_FAILURES.md` · `DECISION_LOG.md` |
| Every Phase 3 finding (F-0018 … F-0021) is **closed**; F-0018 by ERR-002 and F-0020 by ERR-003 | `KNOWN_FAILURES.md` · `HUMAN_GATE_RECORDS.md` |
| Every Phase 4 finding (F-0022 … F-0025) is **closed**; F-0024 and F-0025 by the ERR-004 remediation | `KNOWN_FAILURES.md` · `HUMAN_GATE_RECORDS.md` |
| **F-0026 closed** — GOV-001 is enforced by the checker. Re-running the gate on an accepted phase without authorization returns `AWAITING_RESCORING_AUTHORITY` | `KNOWN_FAILURES.md` · EV-0040 |
| Re-running the gate for **Phase 2 or 3** returns `AWAITING_RESCORING_AUTHORITY`. That is the mechanism, not a regression — their recorded acceptance stands | `BUILD_STATE.md` · EV-0042 |
| **Re-accepting a previously accepted phase requires explicit re-scoring authorization *before* the re-score.** The original record stays immutable and marked superseded; nothing is amended, deleted or concealed. Phase 4's remediate-then-report ordering was authorized retrospectively and is **not** precedent | **GOV-001** in `HUMAN_GATE_RECORDS.md` (resolves the question left open by ERR-004) |
| **TRUST-2/3/4 are UNSUPPORTED on this host** — a real probe result, not a defect. Re-probe on any new host | `phase_4_report.json` · EV-0033 |
| **No execution surface exists**, so policy bypass resistance is CONTRACT-level only | EV-0032 |
| Isolation backend probe deferral **DEF-003 is closed** | `OPEN_BLOCKERS.md` |
| Register exhaustiveness is by construction, not mechanical extraction (M-P0-1) | `PHASE_0_AUDIT.md` |
| Golden Repair corpus instantiation deferred to Phase 30 (DEF-004) | `OPEN_BLOCKERS.md` |
| Contract schema files under `docs/contracts/` deferred (DEF-008) | `OPEN_BLOCKERS.md` |
| Clean-test baseline VM image deferred to Phase 36 (DEF-005) | `OPEN_BLOCKERS.md` |
| Unsigned installer vs SmartScreen on a clean baseline (MEDIUM) | `CLEAN_TEST_BASELINE.md` §7 |
| Recorded defects retained as permanent evidence — count is held by the file, not mirrored here | `KNOWN_FAILURES.md` |

## 8. Current phase contract — Phase 6

Derived from authoritative artifacts, not from memory. **Phase 5 is closed;** its contract is in
`phase_5_report.json` and `PHASE_HISTORY.md`.

| Field | Value |
|---|---|
| Name | **Artifact / Evidence Plane** | `IMPLEMENTATION_DEPENDENCY_MATRIX.md` |
| Status | **UNLOCKED — NOT_STARTED**. Unlocked by the Phase 5 gate run, which returned `progression: PERMITTED` |
| Contract IDs | **C-14**, **C-15** — read `CONTRACT_INVENTORY.md` before starting |
| Read first | `CONTRACT_INVENTORY.md` rows C-14/C-15 · `VERIFICATION_ARCHITECTURE.md` Part 2 (evidence graph strategy) · ADR-0006 |

**Why it matters downstream.** Phase 6 supplies the content-addressed revision identity that Phase 5
deliberately left as a nullable `provenance_ref`, and it is a prerequisite of Phase 22B (Recovery
Supervisor). Re-derive its requirement set from `REQUIREMENT_REGISTER.md`'s Phase column rather than
trusting any summary, including this one.

**Machine acceptance.** Produce a phase report satisfying C-17, then run
`python scripts/run_phase_gate.py 6 7`. Acceptance requires verdict `PHASE_ACCEPTED_BY_MACHINE`.

## 9. Next exact action

**Begin Phase 6 — Artifact / Evidence Plane (C-14, C-15).** Phase 5 is MACHINE-ACCEPTED and Phase 6
is unlocked. Do not re-run the Phase 5 gate: Phase 5 now carries an acceptance record, so a re-run
correctly returns `AWAITING_RESCORING_AUTHORITY` (GOV-001). That is the mechanism, not a regression,
and the recorded acceptance stands.

**What Phase 5 delivered, and what it did not.** SQLite+WAL persistence behind engine-neutral
repositories, the C-12 Project/Revision Registry, minimal backup/restore under `lifecycle.recovery`,
the `surfaces.command` API under the Phase 4 PEP, and the React/TypeScript/Vite/Tailwind Project
Registry frontend — closed by **9 real browser tests** in Chromium against the Vite production build,
a live uvicorn-served API and a real SQLite file. All **7/7** Phase 5 requirements are SATISFIED with
named implementations and named evidence, and discharged under C6.

**Not delivered, and not claimed:** cross-browser E2E (Chromium only), a browser journey for any
capability other than the Project Registry, the Recovery *Supervisor* or `ROLLBACK_STABLE` (Phase
22B; the PDP denies it for every actor), restore across a schema-revision change (Phase 20),
content-addressed revision identity (Phase 6 — this is the next job), the T6 property tier
(`hypothesis` absent), and bypass resistance across all six execution surfaces, five of which do not
exist (ARK-REQ-0325/0347, Phase 31).

**Controls added in Phase 5 that must not be weakened.** All were mutation-tested before being
relied on:

* `backend/tests/structural/test_vertical_slice_linkage.py` — ARK-REQ-0229, both chains;
* `test_contract_drift.py` — frontend transport types vs the live OpenAPI document, field by field;
* `test_frontend_boundaries.py` — no shadow state machine, no shadow policy, no fabricated data;
* `test_frontend_stack.py` — ARK-REQ-0009, the stack parsed from the Master Spec;
* `test_browser_journey_integrity.py` — the T10 harness cannot be hollowed out;
* `test_engine_confinement.py` — ARK-REQ-0012.

**Standing acceptance rules.** C6 (a requirement may be discharged only if traceability claims it
SATISFIED with a named implementation and evidence), PROTECTED_CORE (three real executions if the
change set touches a protected-core path — derived from the paths, never declared), and RESCORING
(GOV-001: an accepted phase needs explicit authorization bound to its exact evidence-package digest
before it may be re-scored).

Do not begin any later phase. Do not activate the Capability Graph — that is Phase 9B. Do not
implement the Recovery Supervisor or Stable Core promotion.

## 10. New-session bootstrap protocol

A new session MUST, in order:

1. Open the repository. It is the source of truth.
2. Read this manifest for orientation only.
3. `git rev-parse HEAD` — compare against §1. Mismatch ⇒ this manifest is stale.
4. `git status --porcelain -uall` — confirm the working-tree claim in §3.
5. Read `docs/build/BUILD_STATE.md` for authoritative phase status.
6. Read `docs/acceptance/HUMAN_GATE_RECORDS.md` for gate decisions.
7. Verify requirement counts from `REQUIREMENT_REGISTER.md`, not from §3.
8. Run `python scripts/check_handoff.py`. **Non-zero ⇒ STOP with `HANDOFF_DRIFT`.**
9. Read only the authoritative sources relevant to §9 NEXT EXACT ACTION.
10. Continue from §9. Never restart the architecture from scratch.
11. Never claim prior work without repository evidence.
12. On any drift between this manifest and the repository: **repository wins, stop.**

## 11. Handoff integrity

| Field | Value |
|---|---|
| Schema | `ARKALI-HANDOFF-V1` |
| Generated at HEAD | `d9b8af47495c5dda6e486615a24f6568a3c1c6be` |
| Generated after | **PHASE 5 MACHINE ACCEPTANCE** — Atomic Package 5: the real T10 browser journey, the evidence records, `phase_5_traceability.json`, `phase_5_report.json` and the gate run, which returned `PHASE_ACCEPTED_BY_MACHINE` with C1–C6 PASS and PROTECTED_CORE COMPLETE. **Both acceptance guards were proved able to fail** before the verdict was recorded: setting one traceability claim to DEFERRED yields `PHASE_BLOCKED` on C6, and removing the adversarial-review run yields `PHASE_BLOCKED` on PROTECTED_CORE. Phase 5 is accepted and Phase 6 is unlocked; cumulative verified rises 65 → **72**. **F-0031** was opened and closed: two re-scoring controls named Phase 5 as their example of an unaccepted phase and expired on its acceptance — proven mechanically to be a stale subject rather than a defect, since the same path still returns NOT_APPLICABLE for phase 6, and repaired by deriving the subject from `GovernanceState`. Eighth instance of the phase-scoped-check family. `EVIDENCE_INDEX.md`'s deliberately-absent table was also repaired: rows Phase 5 made false are moved to a superseded table rather than deleted. Phase 4 remains MACHINE-ACCEPTED under RSA-001 |
| Previously generated after | **Phase 5 Atomic Package 4 (complete)** — the frontend increment and the ARK-REQ-0229 vertical-slice linkage control. `BUILD_STATE.md` and `DECISION_LOG.md` changed and NEXT EXACT ACTION moved, so the §12 refresh was mechanically required. React/TypeScript/Vite/Tailwind now actually run: `npm ci` from the tracked lockfile, the Vitest tier added through real npm tooling, typecheck clean, 23 component tests green, production build succeeds. One backend contract was added — `GET /api/lifecycle/project` publishes the machine's state *vocabulary* and deliberately not its transition relation — for a demonstrated defect, recorded in `DECISION_LOG.md` and tested in both directions. **`ARK-REQ-0009`, `ARK-REQ-0178` and `ARK-REQ-0229` are implemented and controlled but NOT discharged**, and their `e2e` obligation is **unmet**: **T10 = NOT_CONFIGURED**, no browser ran, and the jsdom tests are not a substitute. Every new control was mutation-tested; the first linkage check did not fail its mutation and was repaired before being believed. **No requirement is discharged and no finding was opened.** Phase 5 remains IN PROGRESS, NOT ACCEPTED; Phase 6 LOCKED; Phase 4 MACHINE-ACCEPTED under RSA-001 |
| Previously generated after | **Phase 5 Atomic Package 4 (partial)** — the Command Center API under `surfaces.command`, backend half only.  `BUILD_STATE.md` changed, so the §12 refresh was mechanically required. The package was stopped at a green, internally consistent checkpoint rather than rushed; **the frontend is not built and ARK-REQ-0009/0178/0229 are not satisfied**. A Phase 4 tripwire fired as designed when the first execution surface appeared and was replaced by the obligation it named — see `DECISION_LOG.md`; not a finding, because nothing was defective. **No requirement is discharged.** Phase 5 remains IN PROGRESS, NOT ACCEPTED; Phase 6 LOCKED; Phase 4 MACHINE-ACCEPTED under RSA-001 |
| Previously generated after | **Phase 5 Atomic Package 3 (complete)** — minimal backup/restore under `lifecycle.recovery`, with the canonical A→backup→B→restore→verify proof and 18 lifecycle negative controls. `BUILD_STATE.md` changed, so the §12 refresh was mechanically required. The change set was classified **PROTECTED_CORE** by `select_profile` from its own changed paths, and all three required categories ran at exit 0. **No requirement is discharged and no finding was opened.** Phase 5 remains IN PROGRESS, NOT ACCEPTED; Phase 6 LOCKED; Phase 4 MACHINE-ACCEPTED under RSA-001 |
| Previously generated after | **Phase 5 Atomic Package 3 (partial)** — WAL-safe backup/restore mechanics in `kernel.persistence`. `BUILD_STATE.md` changed, so the §12 refresh was mechanically required. The package was stopped deliberately at a green, internally consistent checkpoint rather than rushed; `lifecycle.recovery` is untouched, so no half-written Protected Core surface exists. **No requirement is discharged and no finding was opened.** Phase 5 remains IN PROGRESS, NOT ACCEPTED; Phase 6 LOCKED; Phase 4 MACHINE-ACCEPTED under RSA-001 |
| Previously generated after | **Phase 5 Atomic Package 2** — the C-12 Project/Revision Registry, plus the closure of F-0030. `BUILD_STATE.md` and `OPEN_BLOCKERS.md` changed, so the §12 refresh was mechanically required. **Phase 5 is not accepted**: no phase report, no traceability record, no gate run, no requirement discharged, and Phase 6 is not unlocked. Phase 4 remains MACHINE-ACCEPTED under RSA-001 |
| Previously generated after | **Phase 5 Atomic Package 1** — the `kernel.persistence` C-03 foundation, plus the closure of F-0029. `BUILD_STATE.md` and `OPEN_BLOCKERS.md` changed, so the §12 refresh was mechanically required. **Phase 5 is not accepted**: no phase report, no traceability record, no gate run, no requirement discharged, and Phase 6 is not unlocked. Phase 4 remains MACHINE-ACCEPTED under RSA-001. Superseded note follows |
| Previously generated after | **F-0027 + F-0028 closure** — the pre-Phase-5 structural governance repair. Governed artifacts changed (`BUILD_STATE.md`, `OPEN_BLOCKERS.md`), so the §12 refresh was mechanically required. **No Phase 5 functionality was implemented.** No phase, gate, ADR or requirement state changed: Phase 4 remains MACHINE-ACCEPTED under RSA-001 and Phase 5 remains UNLOCKED — NOT_STARTED. Two stale values in the previous revision were corrected by re-derivation rather than carried forward: the §7 MEDIUM count, which disagreed with §3 and which no artifact derives mechanically, is now a pointer to `OPEN_BLOCKERS.md`; and §8's reading of the matrix's `T5, T11` as state machines is corrected to the test tiers `VERIFICATION_ARCHITECTURE.md` defines |
| Generating role | Principal Software Architect / implementation lead (not the acceptance authority) |
| Validator | `scripts/check_handoff.py` |
| Refresh rule | see §12 |

Source artifacts are identified by Git blob id, which is content-addressed: if a
source changes, its blob id changes and the reference below becomes stale.

```
docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md              tracked at HEAD
docs/CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md             tracked at HEAD
docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md tracked at HEAD
docs/ARKALI_GENESIS_V2_START_COMMAND.txt                    tracked at HEAD
docs/canonical/REQUIREMENT_REGISTER.md                      tracked at HEAD
docs/canonical/AUTHORITY_MAP.yaml                           tracked at HEAD
docs/adr/ADR_INDEX.md                                       tracked at HEAD
docs/acceptance/HUMAN_GATE_RECORDS.md                       tracked at HEAD
docs/build/BUILD_STATE.md                                   tracked at HEAD
```

Exact blob ids are obtainable with `git rev-parse HEAD:<path>` and are verified
by the validator through the derived-truth comparison rather than by
transcription, so no stale hash can silently pass.

## 12. Refresh rule (institutionalised)

This manifest MUST be regenerated from authoritative repository state after any of:

- every machine-accepted phase;
- every Human Gate decision;
- every accepted governance erratum;
- Stable Core promotion;
- any rollback;
- any new BLOCKER or HIGH that changes continuation strategy;
- any change to NEXT EXACT ACTION.

Refresh means **re-derive from the repository**, never hand-edit to match a
memory of the state. The manifest may never become a second authority; it holds
no governed value that the repository does not already hold.

---

```yaml
# ARKALI-HANDOFF-CLAIMS
# Machine-readable claims. scripts/check_handoff.py compares every value below
# against truth derived from Git and the accepted governance artifacts.
# These are CLAIMS, not authority: on disagreement the repository wins.
schema_version: ARKALI-HANDOFF-V1
head: d9b8af47495c5dda6e486615a24f6568a3c1c6be
branch: main
working_tree_clean: true

requirements_total: 313
requirements_mandatory: 303
requirements_conditional: 8
requirements_optional: 2

verified_by_phase:
  "1": 5
  "2": 23
  "3": 4
  "4": 33
  "5": 7
cumulative_verified: 72

accepted_phases: ["0", "0A", "0B", "1", "2", "3", "4", "5"]
unlocked_phase: "6"
next_exact_action_phase: "6"

accepted_human_gates: ["HUMAN_GATE_1"]
adr_accepted: 9
adr_proposed: 0
open_blocker_high: []

authoritative_sources:
  - docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md
  - docs/CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md
  - docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md
  - docs/ARKALI_GENESIS_V2_START_COMMAND.txt
  - docs/canonical/REQUIREMENT_REGISTER.md
  - docs/canonical/AUTHORITY_MAP.yaml
  - docs/canonical/ARCHITECTURE.md
  - docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md
  - docs/canonical/PHASE_GATE_CHECKER.md
  - docs/adr/ADR_INDEX.md
  - docs/acceptance/HUMAN_GATE_RECORDS.md
  - docs/build/BUILD_STATE.md
  - docs/build/PHASE_HISTORY.md
  - docs/build/OPEN_BLOCKERS.md
```
