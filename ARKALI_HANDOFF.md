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
| Current HEAD | `11ebf14088f69a09809c332749fcdf4e3f145313` |
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
docs/acceptance/EVIDENCE_INDEX.md        EV-0001 .. EV-0022
```

**Executable governance (run these, do not trust prose):**

```
scripts/run_phase_gate.py                   Phase Gate Checker entry point
scripts/check_handoff.py                    this manifest vs repository truth
scripts/check_repository_structure.py       + _negative.py
scripts/check_phase_graph.py                + _negative.py
scripts/check_phase0_deliverables.py
backend/                                    pytest suite (973 passed, 12 skipped)
backend/tests/persistence/                  T11 persistence: real SQLite, WAL, durability, migrations
backend/tests/structural/test_engine_confinement.py  ARK-REQ-0012 architecture control
backend/tests/security/                     PDP, PEP, isolation, secrets, drift
backend/tests/governance/test_handoff_drift.py  handoff negative controls
backend/tests/governance/test_dependency_rules.py  dependency-rule reconciliation (F-0028)
backend/tests/state_machines/               12 machines + canonical reconciliation
backend/tests/capability/                   C-13 schema + pre-activation behaviour
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
| Phase 5 | **UNLOCKED — IN PROGRESS, NOT ACCEPTED** ← current work. Package 1 (`kernel.persistence` C-03 foundation) delivered at `11ebf14`. No phase report, no traceability record, no gate run |
| Human Gates | `HUMAN_GATE_1` ACCEPTED. Gates 2–8 not reached |
| ADRs | 9 **ACCEPTED**, 0 PROPOSED — immutable; supersession needs a new ADR, and Gate 2 for Protected Core ADRs |
| Requirements | **313** total — 303 MANDATORY / 8 CONDITIONAL / 2 OPTIONAL |
| Cumulative verified | **65** MANDATORY (5 Phase 1 + 23 Phase 2 + 4 Phase 3 + 33 Phase 4), reconciled by check C6 against `phase_4_traceability.json` |
| BLOCKER / HIGH | **0 / 0** (derived by the validator from declared Status cells) |
| MEDIUM / LOW | tracked, non-blocking — **the count is held by `OPEN_BLOCKERS.md`, not mirrored here.** No mechanically derived total exists: the residual set is prose, so any number written here would be a transcription that re-rots on the next finding (F-0002, F-0011). Read the file |
| Recorded findings | every finding through **F-0029** is closed |
| Authority conflicts | **0** (39 concerns, one owner each) |
| Architecture violations | **0** (8 gates PASS over **43** real cross-context edges; all **9** numeric budgets measured under ratified contract 1.0.0). The direction gate now consumes `dependency_rules` rather than modelling it (F-0028) |
| State machines | **12** implemented, one per declared authority, reconciled against `STATE_MACHINES.md` on every run |
| Capability Graph | **schema only**; every query returns `NOT_CONFIGURED`; activation is Phase 9B (ADR-0003) |
| Security | one PDP · 14 operation classes · 5 TRUST tiers · 7 properties · 7 backends probed · Protected Core, Secret Vault and Local-Only boundaries enforced |
| Host isolation | TRUST-0/1 satisfiable. **TRUST-2/3/4 UNSUPPORTED** on this host (`NET_EGRESS_CONTROL`, `KERNEL_ISOLATION` unavailable). Re-probe; never assume |
| Execution surfaces | **none exist.** Policy bypass resistance is verified at CONTRACT level only |
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
| 35 | `11ebf14` | **PHASE 5 PACKAGE 1** — `kernel.persistence` C-03 foundation (ARK-REQ-0011, 0012); F-0029 closed. **Not a phase acceptance** ← HEAD at generation |

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
| TypeScript / Vite | not installed | **NOT_CONFIGURED** |
| Rust / Cargo / rustc | absent | **UNSUPPORTED** |
| Git 2.55.0 | present | PASS |
| ruff | absent | **NOT_CONFIGURED** |
| mypy 2.3.0 | present | PASS (strict, clean) |
| poetry / uv / pip-tools | absent | **NOT_CONFIGURED** (no Python lockfile) |
| pytest 9.1.1 · pydantic 2.8.0 · PyYAML 6.0.3 | present | PASS |
| SQLAlchemy 2.0.51 · Alembic 1.18.5 · FastAPI 0.111.0 | present | PASS — the Phase 5 backend stack is executable |
| SQLite library 3.49.1 (WAL-capable) | present | PASS |
| hypothesis (T6 property tier) | absent | **NOT_CONFIGURED** |
| Playwright (T10 browser/E2E) | absent; npm registry reachable | **NOT_CONFIGURED** — installable, not installed |

No unavailable toolchain may be reported as PASS.

## 7. Open items

| Item | Reference |
|---|---|
| 0 BLOCKER, 0 HIGH | `OPEN_BLOCKERS.md` |
| MEDIUM / LOW findings are tracked and non-blocking; **the file holds the count, this index does not** | `OPEN_BLOCKERS.md` |
| **F-0027 closed** — structure check 12 was phase-scoped and would have rejected legitimate Phase 5 constructs in the context canonical architecture assigns them to. Now scoped by authority: a runtime construct may be built only inside its owning context, resolved from `ARCHITECTURE.md` §3 against `AUTHORITY_MAP.yaml`, over tracked **and** untracked files, failing closed on unresolvable authority or ownership. Sixth instance of the phase-scoped-check family | `KNOWN_FAILURES.md` · `OPEN_BLOCKERS.md` |
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

## 8. Current phase contract — Phase 5

Derived from authoritative artifacts, not from memory.

| Field | Value | Source |
|---|---|---|
| Name | **Persistence + Project Registry + Minimal Backup/Restore** | `IMPLEMENTATION_DEPENDENCY_MATRIX.md` |
| Prerequisites | Phases **2** and **4** (both MACHINE-ACCEPTED) | matrix Prerequisites column |
| ARK-REQ IDs | **7** MANDATORY — 0009, 0011, 0012, 0153, 0178, 0229, 0335 | `REQUIREMENT_REGISTER.md` (Phase column) |
| Contract IDs | **C-03** (implementation; defined at Phase 2), **C-12** project/revision record | `CONTRACT_INVENTORY.md` |
| Owners | `kernel.persistence` (2), `lifecycle.recovery` (2), `surfaces.command` (2), `control.architecture` (1) | register Owner column |
| Test tiers first owed | **T5** integration on real persistence, **T11** persistence (restart, durability, backup→restore→verify); **T10** browser/E2E from Phase 5 onward | `VERIFICATION_ARCHITECTURE.md` §test tiers |
| State machines | none new. **Project**, **BackupRestore** and the other ten were implemented at Phase 3 and are reconciled against `STATE_MACHINES.md` on every run; Phase 5 gives Project and BackupRestore persistence and a real executor | `STATE_MACHINES.md` §1, §9 |
| Human gate | none | matrix Gate column |

**In scope.** SQLite+WAL behind engine-neutral repositories with PostgreSQL-ready
abstractions (ADR-0006, ARK-REQ-0011/0012) — **no raw SQL outside
`kernel.persistence`**, enforced by architecture test. The Project/Revision
registry (C-12). Minimal backup/restore under `lifecycle.recovery`, where a
backup is not verified until proven by an actual restore (§9 of
`STATE_MACHINES.md`). The first frontend slice under `surfaces.command`.

**Forbidden scope.** Capability Graph activation (Phase 9B). Provider runtime
(Phase 9). Stable Core promotion (Phase 23, GATE 2). The Recovery *Supervisor*
is Phase 22B — Phase 5 delivers minimal backup/restore, not `ROLLBACK_STABLE`,
which the PDP denies for every actor.

**Carry forward from Phase 4.** All persistence work is now governed: writes are
subject to the PDP, `kernel.persistence` is not Protected Core but
`lifecycle.recovery` is, and `WRITE_STABLE_FILE` is DENY for every actor.

**Machine acceptance.** Produce a phase report satisfying C-17, then run
`python scripts/run_phase_gate.py 5 6`. Acceptance requires verdict
`PHASE_ACCEPTED_BY_MACHINE`: C1–C5 PASS, 8 architecture gates non-failing,
0 open BLOCKER/HIGH, prerequisites accepted.

**Read before starting.** ADR-0006, `ARCHITECTURE.md` §10 (persistence),
`STATE_MACHINES.md` §9, and `CONTRACT_INVENTORY.md` rows C-03 and C-12.

## 9. Next exact action

**Continue Phase 5 — Atomic Package 2.** Phase 5 is IN PROGRESS and NOT
ACCEPTED. Package 1 is done; do **not** re-do it and do **not** run the phase
gate for Phase 5 yet.

**Delivered by Package 1** (`11ebf14`): the `kernel.persistence` C-03 foundation
— engine with verified WAL, base schema, engine-neutral repository, Alembic and
the first migration, the C-03 contract document, and the ARK-REQ-0012
confinement control. `ARK-REQ-0011` and `ARK-REQ-0012` are implemented and
controlled but **not discharged**: nothing may be counted as closed until a
Phase 5 phase report and `phase_5_traceability.json` exist and the gate runs.

**Remaining Phase 5 scope**, all still open: the Project/Revision registry
(C-12, ARK-REQ unassigned to Package 1), minimal backup/restore under
`lifecycle.recovery` (ARK-REQ-0153, 0335), the first frontend slice
(ARK-REQ-0009, 0178) and the vertical-slice control (ARK-REQ-0229), then the
phase report, traceability record and gate run.

Do not begin any later phase. Do not activate the Capability Graph — that is
Phase 9B. Do not implement the Recovery Supervisor or Stable Core promotion.

**Two acceptance rules now bind every phase report you write.** They exist
because Phase 4's first revision discharged a requirement it had not
implemented, and they are not optional:

* **C6** — a requirement may appear in `ark_req_ids_closed` only if
  `docs/acceptance/phase_5_traceability.json` claims it SATISFIED with a named
  implementation and a named evidence source. Any other state, a missing claim,
  or an unbacked claim fails the gate.
* **PROTECTED_CORE** — if the phase touches a protected-core path, the report
  must carry three real executions whose summaries name *security review*,
  *adversarial review* and *full regression*. There is no flag that substitutes
  for them.
* **RESCORING** — a phase with **no** prior acceptance record is unaffected;
  Phase 5's first acceptance needs no authorization. Re-running the gate on an
  already-accepted phase returns `AWAITING_RESCORING_AUTHORITY` unless
  `HUMAN_GATE_RECORDS.md` carries a GRANTED authorization for that phase and its
  exact evidence-package digest (GOV-001, RSA-001).

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
| Generated at HEAD | `11ebf14088f69a09809c332749fcdf4e3f145313` |
| Generated after | **Phase 5 Atomic Package 1** — the `kernel.persistence` C-03 foundation, plus the closure of F-0029. `BUILD_STATE.md` and `OPEN_BLOCKERS.md` changed, so the §12 refresh was mechanically required. **Phase 5 is not accepted**: no phase report, no traceability record, no gate run, no requirement discharged, and Phase 6 is not unlocked. Phase 4 remains MACHINE-ACCEPTED under RSA-001. Superseded note follows |
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
head: 11ebf14088f69a09809c332749fcdf4e3f145313
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
cumulative_verified: 65

accepted_phases: ["0", "0A", "0B", "1", "2", "3", "4"]
unlocked_phase: "5"
next_exact_action_phase: "5"

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
