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
| Current HEAD | `3574e04c02baeaf3cb4350ba860eea68d7fcecfc` |
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
docs/acceptance/EVIDENCE_INDEX.md        EV-0001 .. EV-0059 (Phase 6 added EV-0051 .. EV-0059)
```

**Executable governance (run these, do not trust prose):**

```
scripts/run_phase_gate.py                   Phase Gate Checker entry point
scripts/check_handoff.py                    this manifest vs repository truth
scripts/check_repository_structure.py       + _negative.py
scripts/check_phase_graph.py                + _negative.py
scripts/check_phase0_deliverables.py
backend/                                    pytest suite (1623 passed, 13 skipped)
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
backend/tests/execution/                    C-19 durable jobs: identity, idempotency across reopen,
                                            checkpoints, lifecycle delegation, PEP · attempts,
                                            heartbeat/ownership, bounded retries, timeout,
                                            cancellation, dead-letter (durable_harness.py is the
                                            shared real-infrastructure harness, not a test module)
backend/tests/evidence/                     C-14 artifact identity/provenance · C-15 chain,
                                            integrity, supersession, boundaries · the C-14/C-15
                                            composed journey, provenance and graph readiness
                                            (plane_harness.py is the shared real-infrastructure
                                            harness, not a test module)
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
| Phase 6 | **MACHINE-ACCEPTED** — verdict `PHASE_ACCEPTED_BY_MACHINE` on the **first** submission (`docs/acceptance/phase_6_report.json`, `phase_6_traceability.json`). C1–C6 PASS, PROTECTED_CORE **COMPLETE** (the change set touched `acceptance.engine`, `control.architecture` and `evidence.audit`, so `select_profile` required security review, adversarial review and full regression — all executed at exit 0), RESCORING NOT_APPLICABLE, HUMAN_GATE NOT_APPLICABLE. Three atomic packages: C-14 artifact descriptor + provenance (`evidence.artifact`), C-15 append-only evidence integrity chain (`evidence.audit`, Protected Core), and the composed Evidence Plane evidence. Migrations `0003` and `0004`. **3/3 requirements discharged** |
| Phase 7 | **MACHINE-ACCEPTED** — verdict `PHASE_ACCEPTED_BY_MACHINE`, progression PERMITTED, on the **first** submission (`docs/acceptance/phase_7_report.json`, `phase_7_traceability.json`). C1–C6 PASS, PROTECTED_CORE **COMPLETE** (member `control.architecture`, from Package 1's kernel-error decomposition; security review 188, adversarial review 538, full regression 1614, all exit 0), RESCORING NOT_APPLICABLE, FINDINGS PASS, PREREQ 2/2, HUMAN_GATE NOT_APPLICABLE. Five atomic packages delivering C-19 and the `ARK-REQ-0027` enqueue surface; migrations `0005`–`0007`. **5/5 requirements discharged** — four MANDATORY plus `ARK-REQ-0060`, the first CONDITIONAL requirement any phase has discharged |
| Phase 8 | **UNLOCKED — IN PROGRESS, NOT ACCEPTED** ← current work. Resource Scheduler + Worker Contracts (C-21). **Packages 1 and 2 of 3 complete.** Package 1: `docs/contracts/worker.md`, `worker_vocabulary` (canonical classes and dimensions parsed, never transcribed) and `worker_contract` (declaration model, PEP-governed). Package 2: the three-condition §4 admission decision — capability, isolation, resource, all required — decomposed across `capability_admission`, `isolation_admission`, `resource_admission` and `admission`. C-21 is INT — no table, no migration, no state machine, no allocation. **Production admission returns `CAPABILITY_NOT_CONFIGURED` for every request** because Phase 9B has not activated the Capability Graph; that is designed behaviour, not a stub. **No requirement discharged and none claimable** — the register assigns Phase 8 zero entries. No traceability record, phase report or gate run exists |
| Human Gates | `HUMAN_GATE_1` ACCEPTED. Gates 2–8 not reached |
| ADRs | 9 **ACCEPTED**, 0 PROPOSED — immutable; supersession needs a new ADR, and Gate 2 for Protected Core ADRs |
| Requirements | **313** total — 303 MANDATORY / 8 CONDITIONAL / 2 OPTIONAL |
| Cumulative verified | **80** discharged (5 Phase 1 + 23 Phase 2 + 4 Phase 3 + 33 Phase 4 + 7 Phase 5 + 3 Phase 6 + **5 Phase 7**), reconciled by check C6 against each phase's traceability record. Of the 80, **79 are MANDATORY**: Phase 7's `ARK-REQ-0060` is the one CONDITIONAL discharged so far. Phase 8 adds none — its denominator is zero |
| BLOCKER / HIGH | **0 / 0** (derived by the validator from declared Status cells) |
| MEDIUM / LOW | tracked, non-blocking — **the count is held by `OPEN_BLOCKERS.md`, not mirrored here.** No mechanically derived total exists: the residual set is prose, so any number written here would be a transcription that re-rots on the next finding (F-0002, F-0011). Read the file |
| Recorded findings | every finding through **F-0044** is closed |
| Phase-state parsing | **acceptance is declared, never inferred** (F-0034). `GovernanceState` reads the leading declared state of a status cell against a canonical vocabulary; only `ACCEPTED` and `MACHINE-ACCEPTED` grant acceptance, and unknown, empty or self-contradictory cells are refused. Explanatory prose has **zero** effect, so a phase row may be written for its readers. One rule, one place: consumers call `current_work_phase()` rather than restating it, and a control fails any module that classifies a phase by searching `status_text` |
| Authority conflicts | **0** (39 concerns, one owner each) |
| Architecture violations | **0** (8 gates PASS over **100** real cross-context edges; all **9** numeric budgets measured under ratified contract 1.0.0). `kernel.contracts.errors` fan-in is **15 of 15** and `kernel.contracts.state_machine` fan-in is **15 of 15**. **`max_orchestration_depth` is 4 of 4** — `surfaces.command → execution.durable → control.policy → kernel.contracts` — at its ceiling. Phase 8 Package 2's 466-line scheduler authority test was decomposed under ADR-0008; no GATE 8 exception was requested |
| Evidence Plane | **storage and integrity only.** C-14 artifact identity/provenance and C-15 append-only chain exist and are accepted. The evidence **graph**, coverage and verdicts (C-16) are **Phase 13** and are not implemented, not computed and not claimed. No Phase 6 capability is reachable from any execution surface |
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
| 48 | `d9b8af4` | handoff manifest refreshed after Phase 5 acceptance (§12 rule) |
| 49 | `346c074` | manifest pointed at the refresh commit (governed-clean ancestor rule) |
| 50 | `c291ee4` | **PHASE 6 PACKAGE 1** — C-14 artifact descriptor + provenance. F-0032 closed |
| 51 | `efaaac7` | handoff manifest refreshed after Package 1 (§12 rule) |
| 52 | `c911269` | **PHASE 6 PACKAGE 2** — C-15 append-only evidence integrity chain; the shared content-address primitive moved to `kernel.contracts`. **Not a phase acceptance** |
| 53 | `712be6c` | handoff manifest refreshed after Package 2 (§12 rule) |
| 54 | `1bb7ceb` | **PHASE 6 MACHINE-ACCEPTED** — Package 3: the composed C-14/C-15 evidence, provenance, graph readiness, `phase_6_traceability.json`, `phase_6_report.json` and the gate run. F-0033 opened and closed. **Phase 7 unlocked** |
| 55 | `2f7e234` | handoff manifest refreshed after Phase 6 acceptance (§12 rule) |
| 56 | `4809941` | **PRE-PHASE-7 GOVERNANCE REPAIR** — F-0034 (HIGH) and F-0035 (MEDIUM) closed. Acceptance is read from a declared state instead of a prose substring. **Not a phase acceptance and not a re-score**: Phase 6's report and traceability are byte-unchanged |
| 57 | `45726b7` | handoff manifest refreshed after the governance repair (§12 rule) |
| 58 | `fa11e2d` | **PHASE 7 PACKAGE 1** — C-19 durable-job persistence foundation under `execution.durable`; migration `0005_durable_job`. The Phase 4 durable-surface tripwire fired as designed and was replaced by a stronger live PEP control. **Not a phase acceptance** |
| 59 | `32a1e39` | handoff manifest refreshed after Package 1 (§12 rule) |
| 60 | `baa581a` | **PHASE 7 PACKAGE 2** — C-19 durability semantics: attempts, heartbeat/ownership, bounded retries, timeout, cancellation, dead-letter; migration `0006_durable_execution`. **Not a phase acceptance** |
| 61 | `0e4c740` | handoff manifest refreshed after Package 2 (§12 rule) |
| 62 | `9b7bf61` | **PHASE 7 PACKAGE 3** — C-19 job-type registry (`ARK-REQ-0060` made evaluable), pause/resume and the crash-recovery sweep; migration `0007_job_type_registry`. F-0036 opened and closed. **Not a phase acceptance** |
| 63 | `d99018c` | handoff manifest refreshed after Package 3 (§12 rule) |
| 64 | `975b1df` | **PHASE 7 PACKAGE 4** — the `ARK-REQ-0027` enqueue surface under `surfaces.command`: `POST /api/jobs` persists durable work and returns a reference without executing it. F-0037, F-0038 and F-0039 opened and closed. **Not a phase acceptance** |
| 65 | `872f138` | handoff manifest refreshed after Package 4 (§12 rule) |
| 66 | `4bd2843` | **PHASE 7 MACHINE ACCEPTANCE** — Package 5: the composed durable journey across six runtimes, real fault-injection evidence at the available tier, `phase_7_traceability.json`, `phase_7_report.json` and one gate run returning `PHASE_ACCEPTED_BY_MACHINE` on the first submission. **5/5 requirements discharged; Phase 8 unlocked** |
| 67 | `b76b730` | handoff manifest refreshed after Phase 7 acceptance (§12 rule) |
| 68 | `f98ae16` | **PRE-PHASE-8 GOVERNANCE REPAIR** — F-0040: traceability emptiness is judged against the requirement denominator instead of absolutely, so the four canonical zero-denominator phases (8, 15, 33, 34) can hold an honest record. **Not a phase acceptance and not Phase 8 work**: no scheduler code, no Phase 8 artifact, no gate run |
| 69 | `ec65d46` | handoff manifest refreshed after the pre-Phase-8 governance repair (§12 rule) |
| 70 | `20f9d7e` | **PHASE 8 PACKAGE 1** — C-21 worker contract and worker declarations: `docs/contracts/worker.md`, the parsed worker vocabulary and the PEP-governed declaration authority. `kernel.contracts.error_base` decomposition under ADR-0008 after `errors.py` hit its fan-in budget — no call site changed, no GATE 8 exception. F-0041 opened and closed (two phase titles drifted from the canonical matrix). **Not a phase acceptance**: no admission decision, no Phase 8 artifact, no gate run, no requirement discharged |
| 71 | `95895d3` | handoff manifest refreshed after Phase 8 Package 1 (§12 rule) |
| 72 | `ce25410` | **PHASE 8 PACKAGE 2** — the three-condition §4 admission decision: capability, isolation and resource, all required. Production admission returns `CAPABILITY_NOT_CONFIGURED` because Phase 9B has not activated the graph; the mechanism is real and the answer is honest. No cached capability verdict, proven by counting the authority's calls. `test_scheduler_authority.py` hit 466 logical lines and was split under ADR-0008. **Not a phase acceptance**: no allocation, no Phase 8 artifact, no gate run, no requirement discharged |
| 73 | `3574e04` | handoff manifest refreshed after Phase 8 Package 2 (§12 rule) |
| 74 | `f9c983a` | handoff drift repaired after Phase 8 Package 2 |
| 75 | `d3a0a9b` | **PRE-PACKAGE-3 ENVIRONMENT REMEDIATION** — the repository was installed from its own manifest onto a clean Python **3.13.15** for the first time, which exposed three latent MEDIUM defects. **F-0042**: the real runtime entrypoint imported `uvicorn`, declared in no manifest group — now `uvicorn>=0.52` in `[project].dependencies` by human ruling. **F-0043**: `fastapi.testclient` binds an HTTP backend declared nowhere, so pytest could not COLLECT the suite — now `httpx2>=2.0.0` in the `dev` extra, derived from starlette's own metadata. **F-0044**: a C-17 contract control refused an unchanged contract because Pydantic 2.13 spells `additionalProperties: true` explicitly where 2.8 left it implicit — proven stale before editing, strength unchanged for every real constraint. One derived control now covers the manifest family. **No lockfile created, no accepted evidence edited, no test weakened.** **Not a phase acceptance**: no Phase 8 artifact, no gate run, no requirement discharged ← HEAD at generation |
| 73 | `3574e04` | handoff manifest refreshed after Phase 8 Package 2 (§12 rule) ← HEAD at generation |

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
| **F-0033 closed** — `alembic/env.py` set `target_metadata = PersistenceBase.metadata` having imported only the base, and that object is populated by the *import side effect* of the modules declaring mapped classes. The migration tool's picture of the schema was therefore one table out of seven, and autogenerate treats an unseen table as removed — it was configured to propose dropping six real tables. The same dependency made the schema-comparison control order-sensitive: green under `pytest -q`, red under `pytest tests/persistence -q`. Repaired at the migration composition root, **not** in `kernel.persistence`, which is rank 0 and cannot import rank 1 and rank 2 contexts. Three derived controls now fail if `env.py` omits, over-declares or fails to import a mapped module. MEDIUM; failed in the **detecting** direction and no migration in the chain was autogenerated | `KNOWN_FAILURES.md` · `OPEN_BLOCKERS.md` |
| **One acceptance guard is weaker than Phase 6's own traceability record.** C-15 is mapped onto ARK-REQ-0004 in full, but check C6's contract requires only that a SATISFIED claim *name* an implementation and an evidence source — there is no per-contract granularity. Proven mechanically as case D2 of the acceptance-guard run, **not** assumed. No control was added: no accepted traceability record names a contract id at all, so a repository-wide rule would fail Phases 2–5. Strengthening it is Phase 13 work | `phase_6_report.json` limitations · `DECISION_LOG.md` |
| **F-0034 closed** — the phase-status parser decided acceptance by prose substring and could report an unaccepted phase as accepted. `"ACCEPTED" in status_text and "NOT ACCEPTED" not in status_text` searched the whole free-text cell **and** inferred acceptance from the absence of a negation, so Phase 7's own row saying "Phases 5 and 6 are accepted" accepted Phase 7 — a fail-**open** in the acceptance path, since `checker.check_prerequisites` reads the same property. HIGH, following F-0024's consequence class rather than F-0025's mechanism class. Repaired by reading a declared state; backward compatibility proven over every live row, no phase changed meaning, and Phase 7's row is written plainly again as the live proof | `KNOWN_FAILURES.md` · `OPEN_BLOCKERS.md` · `DECISION_LOG.md` |
| **F-0035 closed** — blank lines split the `OPEN_BLOCKERS.md` findings table, so **F-0027 … F-0034 were invisible** to `stopping_findings`. Found because F-0034 was opened as HIGH and the gate still reported none open. Every hidden row was CLOSED, so no false PASS was produced. Repaired in the document, not in Protected Core `findings.py`; a derived control now fails if any declared finding row is unreachable. MEDIUM, following F-0025 | `KNOWN_FAILURES.md` · `OPEN_BLOCKERS.md` |
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

## 8. Current phase contract — Phase 8

Derived from authoritative artifacts, not from memory.

| Field | Value |
|---|---|
| Name | **Resource Scheduler + Worker Contracts** (`IMPLEMENTATION_DEPENDENCY_MATRIX.md` row 8) |
| Status | **UNLOCKED — IN PROGRESS, NOT ACCEPTED**. Packages 1 and 2 of 3 complete; Package 3 not started |
| Prerequisites | Phase **7**, MACHINE-ACCEPTED |
| Contract IDs | **C-21** (worker contract and admission, `execution.scheduler`) — `docs/contracts/worker.md`; kind `INT`, so no table or migration |
| Human gate | none (matrix Gate column `—`) |
| ARK-REQ IDs | **none**. `RequirementRegister.for_phase("8")` returns an empty denominator; cumulative verified therefore remains 80 |
| Verification profile | derive Package 3 from its changed paths with `select_profile`; Package 1 was PROTECTED_CORE and Package 2 was NORMAL |
| Evidence hazard | C-21 must be evidenced from the test tier and C-17 report. A production `scheduler → evidence.*` edge would exceed orchestration depth; `ARK-REQ-0354` belongs to Phase 31 and is NOT CLAIMED |

Packages 1 and 2 are committed as `20f9d7e` and `ce25410`. Production admission
honestly returns `CAPABILITY_NOT_CONFIGURED` until Phase 9B activates the
Capability Graph. Package 3 is the final integration/evidence/traceability/report
package described in §9; it has not begun.

## 9. Next exact action

**Begin Phase 8 Package 3 — final integration and evidence, zero-requirement
traceability (`claims: []`), the C-17 phase report, and the first machine-
acceptance submission; Phase 9 unlocks only if it is genuinely earned.**
Packages 1 (`20f9d7e`) and 2 (`ce25410`) are complete and committed. Do not
rebuild either, and do not rebuild Phase 7.

**RUN EVERYTHING FROM THE CANONICAL ENVIRONMENT.** The official runtime is
Python **3.13.15** in the repository-local `.venv`, which is git-ignored. Use
`.\.venv\Scripts\python.exe` for pytest, mypy, every validator and the gate.
The system Python 3.12 is NOT canonical (`requires-python = ">=3.13"`), and it
carries ad-hoc extras that masked F-0042, F-0043 and F-0044 for three phases.
The repository still has **no Python lockfile**; do not create one.

**What Packages 1 and 2 leave ready.** `AdmissionService.evaluate(request)`
answers §4 for one request: it resolves the C-21 declaration through the
PEP-governed `WorkerContract`, asks `control.capability` live, asks
`control.isolation` live, and applies the pure resource test to a caller-supplied
availability snapshot. Every refusal carries the refusing authority's own reason.
Package 3 composes and evidences this; it should not need to change it.

**The traceability record is `claims: []`, and that is the only truthful shape.**
`ark_req_ids_closed` is `[]` too. This is legal because and only because the
denominator is empty — F-0040's repair made C6 judge emptiness against the
denominator rather than absolutely, and it now refuses a non-empty record against
an empty denominator just as hard as the reverse. **No synthetic claim, no
contract-id-as-requirement claim, no foreign-phase claim.** Cumulative verified
stays **80**.

**Report the capability position honestly.** Production admission returns
`CAPABILITY_NOT_CONFIGURED` for every request, because Phase 9B has not
activated the graph. State that plainly; never present the test-only-resolver
success path as production capability. `ARK-REQ-0354` is **Phase 31** and must be
named NOT CLAIMED.

**Evidence comes from the test tier.** A `scheduler → evidence.*` production edge
measures depth 5 and a control now asserts its absence. C-15's `EvidenceInput`
requires a register-validated `requirement_id`, so C-21 has no legal audit-chain
anchor — evidence C-21 through the report's `public_contracts`,
`tests_executed` and `evidence_created`, exactly as Phases 6 and 7 did.

Two facts from the scope derivation still dominate everything Phase 8 does:

- **Phase 8's requirement denominator is exactly zero.** No register row carries
  Phase 8; `execution.scheduler`'s only registered requirement is
  `ARK-REQ-0354`, and it belongs to **Phase 31**. Phase 8's obligation is the
  **C-21** contract from `CONTRACT_INVENTORY.md` — kind `INT`, ADDITIVE,
  document `docs/contracts/worker.md`, verified by *admission tests*. `INT` is
  not `DB`: **no table, no migration.**
- **`execution.scheduler → execution.durable` is FORBIDDEN.** Both are rank 3,
  `allow_same_layer: false`, and no sibling edge involves the scheduler. The
  scheduler cannot import the durable runtime, so a second lease/heartbeat
  authority is impossible by construction. It may reach `control.policy`,
  `control.capability`, `control.isolation`, `control.registry.provider`,
  `kernel.*` and `evidence.*`; the only legal composition root for scheduler and
  durable together is a rank-6 `surfaces.*` context.

**Admission cannot succeed at Phase 8, and must refuse honestly.**
`EXECUTION_AND_CAPABILITY.md` §4 admits a job only when capability resolves
other than `NOT_CONFIGURED`, an isolation composition satisfies its tier, and
resource budget is available. §3 activates the Capability Graph at **Phase 9B**
and names `execution.scheduler` (Phase 8) as a consumer that *must handle
`NOT_CONFIGURED` and must not cache capability verdicts*. So condition (a) can
never hold yet: build admission, and have it return a determinate
`NOT_CONFIGURED` — never a stub, never a default, never `True`.

**Canonical authority requires no queue, priority or fairness.** None appears in
§4, in C-21 or in the register. Do not invent one. `execution.scheduler` owns
exactly one concern: `resource_allocation`. There is **no worker state machine**
declared anywhere — do not create one.

**Depth is safe, with one trap.** Every legal design measures 4 of 4. The only
breaching designs are `scheduler → execution.durable` (already forbidden) and
**`scheduler → evidence.*` combined with a surface root**, which measures 5.
Record Phase 8 evidence **from the test tier**, as Phases 6 and 7 did — no
context imports `evidence.audit` today.

**Zero-denominator acceptance is now supported** (F-0040, repaired in `f98ae16`):
a Phase 8 traceability record is `claims: []` with `ark_req_ids_closed: []`,
valid because and only because the register assigns Phase 8 nothing. **No
synthetic claim, no contract-id-as-requirement claim, no foreign-phase claim** —
C6 refuses all three. Cumulative verified stays **80**. C-21's completion is
evidenced through the report's `public_contracts`, `tests_executed` and
`evidence_created`, not by pretending C-21 is an `ARK-REQ`. Note that C-15's
`EvidenceInput` requires a register-validated `requirement_id`, so a C-21
audit-chain record has no legal anchor — keep contract evidence in the report.

**Both corrections owed in Package 1 are done.** `docs/contracts/worker.md` now
exists and reconciles with the implementation in both directions. The Phase 8
title is now the canonical **"Resource Scheduler + Worker Contracts"**, and the
same control caught a second drift nobody was looking for — Phase 6 read
*"Artifact / Evidence Plane"* against the matrix's *"Evidence Plane +
Provenance + Artifact Store"*. Both corrected under **F-0041**, and
`test_every_build_state_phase_title_matches_the_matrix` now reconciles every
phase both documents name.

**One budget fact changed in Package 1.** `kernel.contracts.errors` was at
`max_fan_in_per_module` (15) and the scheduler would have been the sixteenth
importer, so under ADR-0008 the abstract base layer — `ArkaliError`,
`ContractViolation`, `GovernanceStateError`, `AuthoritativeSourceError` — moved
to **`kernel.contracts.error_base`**, which `errors.py` re-exports. No call site
changed and no GATE 8 exception was authored. A context that needs a base error
type must now import `error_base`; `errors.py` is back at **15 of 15** and has
no headroom. Note `kernel.contracts.state_machine` is also at **15 of 15**.

**Watch the surfaces controls if the scheduler is ever composed there.**
`jobs.py` bans the identifier *scheduler* and the import
`arkali.execution.scheduler`, and `app.py` is at the 3-context ceiling — so a
composition would need its own module, or the tripwire precedent applied.

*(the derivation these facts came from is retained below)*

Read, in this order, and derive rather than assume:

- `REQUIREMENT_REGISTER.md` — every requirement whose **Phase column is 8**,
  with its classification, owner and evidence keys. That set is the
  denominator; nothing else is.
- `CONTRACT_INVENTORY.md` — the **C-21** row: owner, kind, versioning,
  compatibility and what verifies it.
- `IMPLEMENTATION_DEPENDENCY_MATRIX.md` — Phase 8's prerequisites and whether
  its Gate column is empty.
- `ARCHITECTURE.md` §3 and `EXECUTION_AND_CAPABILITY.md` §3 — what
  `execution.scheduler` actually owns. §3 already names worker classes and
  declares that each worker states its class, concurrency limit, resource
  profile, required TRUST tier, required isolation properties and heartbeat
  interval. **Read it there; do not carry forward Phase 7's phrasing.**

**Phase 7 told you only what scheduling is NOT.** Its controls assert the
absence of admission, allocation, dispatch, priority, capacity, worker pools
and owner selection from `execution.durable` and `surfaces.command`. That is a
boundary, not a specification, and those controls must keep passing: Phase 8
builds scheduling **in `execution.scheduler`**, not by relaxing them.

What Phase 7 leaves ready: a recovered job waits in `RESUMING` for someone to
pick it up; `begin_attempt` is the only way to start work and the canonical Job
machine refuses it from anywhere illegal; execution ownership is persisted and a
stale owner is refused. Phase 8 decides *who* runs a job. Phase 7 already
decided *whether an execution is still alive*, and that split is enforced.

**Two budget facts to carry in.** `max_orchestration_depth` is at **4 of 4** on
`surfaces.command → execution.durable → control.policy → kernel.contracts`; a
further hop on that chain breaches it and must be decomposed under ADR-0008,
never excepted. `kernel.contracts.errors` fan-in is **14 of 15**.

**Do not re-run `python scripts/run_phase_gate.py 7 8`.** Phase 7 carries an
acceptance record, so a second run returns `AWAITING_RESCORING_AUTHORITY` — that
is GOV-001 protecting an accepted phase, not a regression, and it is not a
proof of anything about Phase 7.

**Controls added in Phase 7 Package 4 that must not be weakened.** In
`tests/structural/test_enqueue_surface_authority.py` and
`tests/surfaces/test_command_jobs_api.py`: no route may call anything that
drives execution — **the forbidden set is derived from `JobExecution` and
`JobRecovery`**, so a method added to either is covered automatically; nothing
in the surface may wait, poll, sleep or spawn; no provider or scheduling
identifier may appear, checked as a **substring of every AST identifier
including both halves of an alias**, because a word-boundary search cannot match
`provider_completion` and an alias hid the original name (both found by
mutation); no route may construct an engine, issue a query or assign a lifecycle
state; idempotency may not be reimplemented at the surface; every route must
take a policy decision and declare exactly one audience; the response contract
must forbid extra fields and expose nothing executional. Behaviourally: after an
enqueue the job must sit in the canonical initial state with **zero attempts and
zero checkpoints**, and that must survive a full application restart.

**Controls added in Phase 7 Packages 1–3 that must not be weakened.** All
mutation-tested (12/12, then 14/14, then 14/14 with each catch verified to be
the *intended* control), split across
`tests/structural/test_durable_authority.py`,
`test_durable_governed_operations.py` and `test_durable_recovery_authority.py`
over `durable_reader.py`: the canonical machine is the only transition
authority; no state literal or transition table is restated; the lifecycle
column is assigned in exactly one method, derived as the one that calls
`evaluate`; no engine is constructed *or imported*; no raw SQL; no Stable class
named; **nothing schedules, admits, claims, leases, allocates or selects an
owner** — Phase 8 owns that and the controls fail on the vocabulary; every
method that operates on the session takes a policy decision; every service class
holding a session consults the PEP; retry accounting is rows and no counter
column may appear; the deadline stays an absolute instant. Also
`TestSurfaceCoverageIsHonest::test_every_built_execution_package_enforces_and_the_rest_are_absent`
— **Package 4 builds a new package under a surface context and must satisfy it.**

Package 3 added, and these are the ones most easily weakened by a later package:

- **`RESUMING` has one authority and one entry shape.** Derived over the whole
  context: only `recovery.py` may request it, every use of the name must be a
  transition target, and the Package 2 retry/timeout/cancel/dead-letter methods
  must have no path to it. This *replaced* Package 2's single-file tripwire,
  which was proven unable to fire before it was touched.
- **The heartbeat term and the deadline term stay distinct (F-0036).** Any
  function named for the heartbeat must read `heartbeat_at`, resolved one level
  through private helpers; the timeout rule must read `deadline_at` and must not
  read `heartbeat_at`. The old conflated name is banned.
- **Recovery is not scheduling.** The sweep must not call `begin_attempt`, must
  not re-decide the disposition Package 2 owns, and must not name `DEAD_LETTER`.
- **Time is injected.** Exactly one wall-clock source in the context, identified
  by the function that holds it; nothing sleeps, waits or polls.
- **Column types are derived, not listed.** Every mapped column's type must come
  from SQLAlchemy's generic namespace, and the mapped-record set is derived from
  the module — a record added later cannot escape the check the way
  `JobTypeRecord` escaped the hand-written list.

**Controls added in Phase 6 that must not be weakened.** All mutation-tested:
`test_artifact_authority.py` (one identity authority, no shadow chain, no second
persistence authority, no Stable mutation path, contract/schema reconciliation,
dependency direction), `test_evidence_authority.py` (sole chain writer, no
artifact-identity minting in `evidence.audit`, no same-layer sibling import, no
amend/delete escape, no stored verification flag, every column in the digest),
and `TestAutogenerateTargetIsComplete` (F-0033 — `env.py` must declare and
import every module that maps a table). `test_live_repository_uses_no_exempt_edge`
is the F-0028 vacuity guard — if a later package makes it fail, change the
design, not the control.

**Re-running `python scripts/run_phase_gate.py 6 7` now returns
`AWAITING_RESCORING_AUTHORITY`.** That is GOV-001 working, not a Phase 6
regression. Verify Phase 6's acceptance through `GovernanceState` and the
recorded report instead.

Do not implement Phase 13 evidence-graph computation, coverage or verdicts
(C-16), new Acceptance Engine functionality, provider runtime, Capability Graph
activation, the Recovery Supervisor, Stable Core promotion or release/SBOM.

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
| Generated at HEAD | `3574e04c02baeaf3cb4350ba860eea68d7fcecfc` |
| Refresh reason | **HANDOFF_DRIFT repair after the Phase 8 Package 2 §12 refresh** — all live HEAD/state claims re-derived from repository truth; no feature, runtime, accepted evidence or phase state changed |
| Generated after | **PRE-PHASE-8 GOVERNANCE REPAIR (F-0040)** — the traceability loader assumed every phase owns at least one requirement, and four canonical phases do not. `TraceabilityRecord.load` refused any empty `claims` list; reproduced against the untouched tree, the refusal was **identical** for Phase 4 (denominator 33) and Phase 8 (denominator 0), so it consulted no denominator at all. `RequirementRegister.for_phase` returns zero for phases **8, 15, 33 and 34**, every one of which is in the canonical phase list — so the only truthful record was rejected while any non-empty record would assert a claim the phase does not own, and C6 failed either way. **The invariant had no canonical source:** "traceability" appears nowhere in the Build Protocol or the VDC and no ADR governs it; the record is `acceptance.engine`'s own mechanism from the F-0024 remediation, whose purpose is to make a *false discharge* impossible — and it was proven in memory that the refusal is not load-bearing for that purpose, because `reconcile_discharge` already refuses every non-empty discharged set against an empty record. **The C-17 report contract was already zero-aware** (`PhaseReport.ALLOWED_EMPTY` contains `ark_req_ids_closed`), so the report half of an acceptance package permitted exactly what the traceability half forbade. Not the transcribed-value family and nothing expired — an **unbacked invariant**, failing in the **rejecting** direction. MEDIUM. **The rule was moved, not deleted:** the loader keeps every well-formedness refusal and stops treating an empty-but-well-formed list as malformed, while C6 gains `discharge_shape.check_claim_shape`, where the register already lives. Both directions fail closed and the second is **strictly stronger than anything before** — a phase owning no requirement may not claim *anything*, so a synthetic, contract-id or foreign-phase claim can no longer be manufactured to satisfy an invariant, a hole the old absolute rule left open for every phase. `reconcile_discharge` is **unchanged**. The subject is derived from the register, so assigning a requirement to 8/15/33/34 moves these controls instead of expiring them, and all six live accepted records were asserted unchanged in meaning. Two 400 logical-line budgets fired (`checker.py` 424, `test_false_discharge.py` 405) and both were answered by **decomposition under ADR-0008** along real seams, not by an exception. Classified **PROTECTED_CORE** by `select_profile` from its own paths (member `acceptance.engine`); all three categories at exit 0 — security review 188, adversarial review 547, full regression **1623** — plus mypy strict clean over **129** modules, 8 gates over 91 edges, 9 budgets, structure 12/12 with both negative controls, phase graph 10/10. **9 mutations injected, 9 caught**; one was initially **missed** and exposed a real gap — every shape control exercised `check_claim_shape` directly, so none proved C6 *calls* it, and a mutation making C6 ignore the result passed (the F-0017 shape). A real end-to-end control now drives `PhaseGateChecker.check_discharge_integrity` over a copied canonical document tree. **Not a phase acceptance and not Phase 8 work:** no scheduler code, no Phase 8 traceability or report artifact, no gate run. Phase 7 remains MACHINE-ACCEPTED, Phase 8 remains UNLOCKED — NOT_STARTED, cumulative verified remains **80** |
| Previously generated after | **PHASE 7 MACHINE ACCEPTANCE** — Atomic Package 5: the composed durable journey, real fault-injection evidence, traceability, the C-17 report and the gate run. **Verdict `PHASE_ACCEPTED_BY_MACHINE`, progression PERMITTED, on the FIRST submission.** C1–C6 PASS; **PROTECTED_CORE COMPLETE** — the profile was derived from the phase's own changed paths and came out PROTECTED_CORE (member `control.architecture`, from Package 1's kernel-error decomposition), so it was **not assumed NORMAL from Packages 2–4**, and all three canonical categories ran at exit 0: security review 188, adversarial review 538, full regression 1614. RESCORING NOT_APPLICABLE; FINDINGS, PREREQ (2/2) and 8 gates over **91** edges PASS; HUMAN_GATE NOT_APPLICABLE. **The denominator was re-derived from the register**, not trusted: five requirements, four MANDATORY and one CONDITIONAL, all owned by `execution.durable`, all five SATISFIED with a named implementation and a named evidence source. **`ARK-REQ-0060` is the first CONDITIONAL requirement any phase has discharged, and it is applicable on its merits** — its Appendix A rule text is parsed out of `REQUIREMENT_REGISTER.md`, the field it names is asserted to be a real persisted column, and it evaluates TRUE against real data across restarts; an unpausable type coexisting with a pausable one is proven **not** to retire it, because reading the rule that way would let one registration silently retire a live obligation. **The chaos key for 0059/0061 is discharged at the available tier and nowhere near T12** — real process loss with persisted `RUNNING` state, heartbeat expiry observed by a process that never watched the job start, a returning zombie owner, a failed transaction, a duplicate attempt refused by the primary key, retry exhaustion to `DEAD_LETTER`, timeout while the worker still reports, and sweep idempotency across restarts; **T12, `ARK-REQ-0327` and Phase 31 are NOT CLAIMED**, and a control derives from the register that `ARK-REQ-0327` is not Phase 7's to discharge. The final journey carries one durable job across **six separate runtimes** on one real SQLite file, and Phase 7 evidence is recorded through the Phase 6 C-14/C-15 authorities unchanged — no second evidence mechanism, no Phase 13 graph. **15 anti-vacuity cases injected and 15 rejected; 8 defective traceability variants rejected by C6 before the gate ran**, with the real record restored byte-for-byte and its digest re-verified. Two background mutation runs were killed mid-flight and each left a mutation behind; both were caught and restored, after which **git became the restore authority**. Package 5 added **no production module and no import edge**, because `max_orchestration_depth` was already 4 of 4. Cumulative discharged 75 → **80**; MANDATORY verified 75 → **79** — the two diverge for the first time and both are recorded. **Phase 8 unlocked** |
| Previously generated after | **PHASE 7 ATOMIC PACKAGE 4** — the `ARK-REQ-0027` enqueue surface under `surfaces.command`. Not a phase acceptance: no requirement is discharged, no traceability record, no report, no gate run, and Phase 8 stays locked behind Phase 7. `POST /api/jobs` persists durable work through C-19 and returns a durable reference; `GET /api/jobs/{job_id}` resolves one. **The guarantee is architectural, not a latency budget** — the register gives `ARK-REQ-0027` `arch` evidence, and **no timing measurement appears anywhere in the evidence**. What is asserted is that after the response the work demonstrably has *not* started: the job sits in the state the canonical machine declares initial, with **zero execution attempts and zero checkpoints**, which a handler that had run the job could not produce. The forbidden call set is **derived from the public surface of `JobExecution` and `JobRecovery`**, so a method added to either later is covered without editing a control. **`202 Accepted`** is the honest status — the request was accepted and the processing has not completed — and it avoids inventing a created-versus-existing distinction that C-19's persisted idempotency makes irrelevant; a repeated `(job_type, idempotency_key)` resolves to the recorded job **across a full application restart**, which an in-memory cache could not survive. The route builds no engine, issues no query, writes no lifecycle state and names no scheduler, worker, dispatch or provider concept. **The job-type registry is not an admission gate at the surface either:** an undeclared type enqueues, because requiring registration to submit would be admission control and that is C-21 at Phase 8. **The surface was decomposed before it was written** — `app.py` and `error_mapping.py` were each already at `max_contexts_touched_by_module`, measured first, so the routes went into `jobs.py` and the durable error table into `job_error_mapping.py` under ADR-0008. **Three findings opened and closed, two of them pre-existing Phase 5 defects reproduced on the Phase 5 routes alone before repair:** F-0037, a contract control that assumed every backend route was also a browser-slice route and expired on the repository's first backend-only route — routes now declare an audience tag read off the live OpenAPI document, failing closed on a route nobody classified; F-0038, one durable timestamp with two wire representations depending on whether the row was still in the session; F-0039, `PolicyDenied` mapped to 403 but unreachable from any route because `guard()` runs before the `try`, so a real denial surfaced as HTTP 500 — and the control meant to cover it asserted the *table*, never the *route*. All three MEDIUM; **none failed open**. Classified **NORMAL** by `select_profile` with no unresolved path; the battery ran in full: **1582 passed / 13 skipped**, mypy strict clean over **128** modules, 8 gates PASS over **91** edges, 9 budgets, structure 12/12 with both negative controls, phase graph 10/10. **13 mutations injected, 13 caught.** One was initially missed and exposed a genuinely weak control — a word-boundary search cannot match `provider_completion` because `_` is a word character, and an aliased import hid the original name — so the control was strengthened to derive identifiers from the AST and check both halves of an alias, then re-verified against four separate spellings. **`max_orchestration_depth` is now 4 of 4** and the next hop on that chain must be decomposed |
| Previously generated after | **PHASE 7 ATOMIC PACKAGE 3** — the C-19 job-type registry, pause/resume and crash recovery. Not a phase acceptance: no requirement is discharged, no traceability record, no report, no gate run, and Phase 8 stays locked behind Phase 7. **The canonical relation was read before any code was written, and it decided the routes.** `RESUMING` has exactly two predecessors, `PAUSED` and `RECOVERABLE`, so pause and crash recovery share one lifecycle meaning because the machine says so rather than because this package arranged it; and `RUNNING → RECOVERABLE` is **not declared** — `evaluate` refuses it — so recovery travels `RUNNING → FAILED → RECOVERABLE → RESUMING`, which is exactly the disposition Package 2 already owns, **composed rather than repeated**. `EXECUTION_AND_CAPABILITY.md` §3 names the states a crashed job resolves *to*; `STATE_MACHINES.md` §3 owns the edges it travels, and the apparent conflict dissolves once the route is derived instead of read as an edge list. **Nothing was added to the canonical machine.** `durable_job_type` is the registry `ARK-REQ-0060`'s Appendix A rule reads; governing rule 7 resolves an unwaived unevaluable rule to APPLICABLE, so declining to build it never avoided the requirement. An unregistered type **raises rather than defaulting** — an absent row is an unanswered question, and answering it either way decides something nobody declared. Declaration is write-once, and the join is by natural key with **no foreign key**, because a FK would make registration a precondition of submitting, which is admission control and belongs to C-21. **Pause suspends, recovery disposes:** a paused job keeps its open attempt, owner, absolute deadline and place in the retry budget, because closing it would consume an attempt and pausing is not failing; a crashed job's attempt is closed, which is precisely what stops a returning zombie worker from heartbeating, completing or failing it. A paused job is **never swept however silent** — the sweep selects `RUNNING`, a filter that is load-bearing rather than tidy. The sweep is idempotent by construction, stops at `RESUMING` and starts nothing. **F-0036 was opened and closed:** Package 2's `heartbeat_expired` resolved to a comparison against `deadline_at` and never read `heartbeat_at`, proven by AST against the untouched tree first — harmless there, because both callers meant timeout, but the canonical recovery rule keys on the heartbeat, so consuming it as written would have swept live workers and left dead ones holding their jobs. The name is **gone rather than reinterpreted**. **Package 2's RESUMING tripwire read one file and could not fire** for work in any other module of the same context; it was verified passing against the finished Package 3 tree before being touched, then replaced with a context-wide derived control — the opposite proof from the usual stale-control case. Classified **NORMAL** by `select_profile` from its own paths, with no unresolved path; the battery ran in full anyway: **1535 passed / 13 skipped**, mypy strict clean over **126** modules, 8 gates PASS over **86** edges, 9 budgets, structure 12/12 with both negative controls, phase graph 10/10. **14 mutations injected, 14 caught**, each re-run to confirm it failed its *intended* control rather than incidentally. The 400 logical-line budget fired at 440 on a test module and was answered by **decomposition under ADR-0008** along a real seam — decide correctly versus survive a restart — with no GATE 8 exception requested |
| Previously generated after | **PHASE 7 ATOMIC PACKAGE 2** — the C-19 durability semantics. Not a phase acceptance: no requirement is discharged, no traceability record, no report, no gate run, and Phase 8 stays locked behind Phase 7. `job_execution_attempt` records one row per attempt — owner, `started_at`, `heartbeat_at`, an absolute `deadline_at`, and `ended_at`/`outcome` on close — with migration `0006_durable_execution`, which also records `max_attempts` and `attempt_timeout_seconds` on the job. **The canonical Job machine was checked first and found sufficient; nothing was added to it.** Three properties therefore come from the canonical relation rather than from code: `DEAD_LETTER` has no outgoing transition, so a dead-lettered job cannot be retried at all; `CANCELLED` is reachable only from `RUNNING`, so a queued job cannot be cancelled and a terminal one cannot be cancelled twice. **Retry accounting is rows, not a counter** — the count is `count(job_execution_attempt)`, and the primary key (`job_id`, `attempt`) is the concurrency backstop, proven by inserting a duplicate past the service and being refused by the database. The deadline is an absolute instant, so a restart cannot move the timeout basis. A stale owner cannot heartbeat, complete or fail an attempt; a closed attempt cannot be written again; timing out twice is idempotent and an unreached deadline is refused. **Nothing sleeps** — the clock is injected and advanced explicitly. **Package 2 never enters `RESUMING`**, runs no recovery sweep and implements no pause/resume: a control fails on those tokens, and what it records is exactly what Package 3 will read. Naming a target would have put a second copy of the state vocabulary in the context, so the names moved into `job_state_machine.py` resolved through `DEFINITION.states` — **the control was not relaxed to fit the code**. Classified **NORMAL** (no Protected Core touched); the battery ran in full anyway: 1447 passed / 13 skipped, 8 gates over **82** edges, 9 budgets, mypy clean over 124 modules. **14 mutations injected, 14 caught**; three initially missed were all real control gaps — a direct lifecycle-state write that every behavioural test tolerated, and a guard dropped from a private method the old sweep could not see — and both controls were strengthened. Both new test modules hit the 400-line budget and were decomposed under ADR-0008 |
| Previously generated after | **PHASE 7 ATOMIC PACKAGE 1** — the C-19 durable-job persistence foundation. Not a phase acceptance: no requirement is discharged, there is no traceability record, no report and no gate run, and Phase 8 stays locked behind Phase 7. `execution.durable` now holds the durable job record, its idempotency identity and the checkpoint record, with migration `0005_durable_job`. **Two identities, one store**: `job_id` is the primary key and (`job_type`, `idempotency_key`) is a named unique constraint, because a separate idempotency table would be a second place answering the same question — proven by writing the row past the service and being refused by the database, and by a repeat resolving to the existing job across a dispose/reopen. Checkpoint ordering *is* identity and checkpoints refuse update and delete. The Phase 3 `Job` machine remains the sole transition authority; the store writes no state literal and derives its initial state from the machine's own relation. Every governed operation passes an injected PEP, and a **real PDP loaded from a denying authority map** proves a refusal prevents the write. The clock is injected, so no test sleeps. **The Phase 4 durable-surface tripwire fired as designed** when the first module appeared, naming its own obligation; it was satisfied first and only then replaced — by a control that derives which execution packages are built and requires each to consult a PEP, so it keeps failing for the next unenforced package instead of going quiet. **The kernel error fan-in budget fired again at 16/15** and was answered by completing the `control.architecture` refusal decomposition Phase 6 had left half-applied, taking it to 14; no GATE 8 exception was requested. Classified **PROTECTED_CORE** (member `control.architecture`); security review 188, adversarial review 479 and full regression 1404 all at exit 0. **12 mutations injected, 12 caught** — three initially missed, of which two were semantic no-ops and one had the wrong subject; correcting them exposed two controls that measured the wrong thing, and both were strengthened |
| Previously generated after | **PRE-PHASE-7 GOVERNANCE REPAIR** — F-0034 and F-0035. Not a phase acceptance, not a re-score, and no Phase 7 work. `PhaseStatus.is_accepted` decided acceptance by searching the whole status cell for `ACCEPTED` and inferring it from the absence of `NOT ACCEPTED`; five of fifteen reproduction fixtures returned a **false accept**, including the exact wording Phase 6's own acceptance recording had to be contorted to avoid. Because `checker.check_prerequisites` reads that property, an unimplemented phase could have satisfied a later phase's prerequisite — a fail-open in the acceptance path, hence HIGH by F-0024's consequence class rather than F-0025's mechanism class. Acceptance is now **declared**: the leading segment of the cell is resolved against a canonical vocabulary read off the rows that already exist, only `ACCEPTED` and `MACHINE-ACCEPTED` grant it, and unknown, empty or self-contradictory cells are refused. Two adjacent instances of the same habit went with it — `is_locked` read `LOCKED` out of `UNLOCKED`, and `check_handoff.py` kept its own prose search, now replaced by `GovernanceState.current_work_phase()`. **F-0035 was found while opening F-0034**: blank lines had split the findings table so that F-0027…F-0034 were invisible to the acceptance gate, which is why an OPEN HIGH produced an empty `open_stopping_findings`; repaired in the document rather than in Protected Core `findings.py`. Backward compatibility proven over all ten live rows — no phase changed meaning — and Phase 7's row is written plainly again as the live proof. 44 new controls, **none naming a phase number**; 9 mutations injected and all 9 caught. Phase 6 remains MACHINE-ACCEPTED with its report and traceability byte-unchanged; Phase 7 remains UNLOCKED — NOT_STARTED |
| Previously generated after | **PHASE 6 MACHINE ACCEPTANCE** — Atomic Package 3: the composed C-14/C-15 evidence, the provenance and graph-readiness evidence, `phase_6_traceability.json`, `phase_6_report.json` and the gate run, which returned `PHASE_ACCEPTED_BY_MACHINE` on the **first** submission with C1–C6 PASS and PROTECTED_CORE COMPLETE over three members. **The acceptance mechanism was proved able to fail before the verdict was taken**: six controlled mutations of the real Phase 6 package each produced `PHASE_BLOCKED` — a claim set to DEFERRED, a claim without an implementation, a claim without evidence, a claim with its evidence emptied, and each of two Protected Core categories removed — with both artifacts verified byte-identical to their pre-run digests afterwards. A seventh case is reported as an **ACCEPT** and is the honest result rather than a hidden gap: removing only the C-15 half of ARK-REQ-0004's evidence is still accepted, because check C6's contract has no per-contract granularity, and no control was added because no accepted phase's traceability record names a contract id at all. **F-0033 was opened and closed**: `alembic/env.py` held one table out of seven as its autogenerate target, so the migration tool was configured to propose dropping six real tables; found by running the T11 tier standalone, repaired at the migration composition root rather than in `kernel.persistence`, which cannot import rank 1 and rank 2 contexts. Seven injected mutations were all caught and 22 anti-vacuity controls all pass. Two structure-validator checks fired against this package's own first draft — a 400-line budget and a banned substitution marker — and the **evidence changed, not the checks**. `ARK-REQ-0004`, `0057` and `0349` are discharged; cumulative verified rises 72 → **75**; Phase 7 is unlocked and not started |
| Previously generated after | **Phase 6 Atomic Package 2 (C-15)** — the append-only audit / evidence integrity chain under `evidence.audit` (Protected Core). `BUILD_STATE.md` and `DECISION_LOG.md` changed and NEXT EXACT ACTION moved, so the §12 refresh was mechanically required. The chain is a real hash chain whose digest covers its predecessor; `verify()` recomputes and there is no stored flag to trust. Update *and* delete are refused; supersession appends and preserves. **The package turned on an architectural repair**: the first shape imported `evidence.artifact` across the layer, which `test_live_repository_uses_no_exempt_edge` caught — the exemption it leaned on is about *writing* evidence, not reading a sibling. The exemption was left alone and the content-address mechanism moved to `kernel.contracts` (the Phase 3 shape: mechanism in the kernel, authority with the context), while artifact linkage became the persisted foreign key. 8 gates PASS over 77 edges with `allow_same_layer` still false. Classified **PROTECTED_CORE** by `select_profile` (members `control.architecture`, `evidence.audit`); security review, adversarial review and full regression all ran at exit 0. Five structural controls mutation-tested. **No requirement is discharged**; Phase 6 IN PROGRESS, NOT ACCEPTED; Phase 7 LOCKED |
| Previously generated after | **Phase 6 Atomic Package 1 (C-14)** — the artifact descriptor and provenance foundation under `evidence.artifact`. `BUILD_STATE.md`, `KNOWN_FAILURES.md` and `OPEN_BLOCKERS.md` changed and NEXT EXACT ACTION moved, so the §12 refresh was mechanically required. Identity is the content address and is derived from the bytes, never supplied; artifacts and provenance are immutable by ORM refusal; a tampered blob is detected and never repaired; blob writes are PEP-governed under `WRITE_WORKSPACE_FILE`. **C-12 was not touched** — a 71-character address fits its existing column, and the rank 1 → rank 2 import ban still holds. A real architecture budget was hit (kernel error fan-in 16 > 15) and answered by decomposition per ADR-0008, not by an exception. **F-0032 opened and closed**: three tests transcribed the migration-chain head and expired when the chain advanced — proven stale before being touched, then repaired by deriving the head. Ninth instance of that family. **C-15 is not implemented and the Protected Core profile has NOT been run or claimed.** No requirement is discharged; Phase 6 is IN PROGRESS, NOT ACCEPTED; Phase 7 LOCKED; Phase 5 remains MACHINE-ACCEPTED |
| Previously generated after | **PHASE 5 MACHINE ACCEPTANCE** — Atomic Package 5: the real T10 browser journey, the evidence records, `phase_5_traceability.json`, `phase_5_report.json` and the gate run, which returned `PHASE_ACCEPTED_BY_MACHINE` with C1–C6 PASS and PROTECTED_CORE COMPLETE. **Both acceptance guards were proved able to fail** before the verdict was recorded: setting one traceability claim to DEFERRED yields `PHASE_BLOCKED` on C6, and removing the adversarial-review run yields `PHASE_BLOCKED` on PROTECTED_CORE. Phase 5 is accepted and Phase 6 is unlocked; cumulative verified rises 65 → **72**. **F-0031** was opened and closed: two re-scoring controls named Phase 5 as their example of an unaccepted phase and expired on its acceptance — proven mechanically to be a stale subject rather than a defect, since the same path still returns NOT_APPLICABLE for phase 6, and repaired by deriving the subject from `GovernanceState`. Eighth instance of the phase-scoped-check family. `EVIDENCE_INDEX.md`'s deliberately-absent table was also repaired: rows Phase 5 made false are moved to a superseded table rather than deleted. Phase 4 remains MACHINE-ACCEPTED under RSA-001 |
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
head: d3a0a9b13785f748b1ac823d927138c9c06e1596
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
  "6": 3
  "7": 5
cumulative_verified: 80

accepted_phases: ["0", "0A", "0B", "1", "2", "3", "4", "5", "6", "7"]
unlocked_phase: "8"
next_exact_action_phase: "8"

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
