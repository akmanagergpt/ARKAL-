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
| Current HEAD | `85cbcda0bc4e1b26fab9d2059adbb81f8edbcd3f` |
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
backend/                                    pytest suite (88 tests)
backend/tests/governance/test_handoff_drift.py  handoff negative controls
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
| Phase 3 | **UNLOCKED — NOT_STARTED** ← current work |
| Human Gates | `HUMAN_GATE_1` ACCEPTED. Gates 2–8 not reached |
| ADRs | 9 **ACCEPTED**, 0 PROPOSED — immutable; supersession needs a new ADR, and Gate 2 for Protected Core ADRs |
| Requirements | **313** total — 303 MANDATORY / 8 CONDITIONAL / 2 OPTIONAL |
| Cumulative verified | **28** MANDATORY (5 Phase 1 + 23 Phase 2) |
| BLOCKER / HIGH | **0 / 0** |
| MEDIUM / LOW | 14 / 9 (tracked, non-blocking) |
| Authority conflicts | **0** (39 concerns, one owner each) |
| Architecture violations | **0** (8 gates PASS over 16 real cross-context edges) |
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
| 17 | `85cbcda` | pre-Phase-3 governance hygiene: GH-001/002/003 ← HEAD at generation |

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
| pytest · pydantic 2.8.0 · PyYAML | present | PASS |

No unavailable toolchain may be reported as PASS.

## 7. Open items

| Item | Reference |
|---|---|
| 0 BLOCKER, 0 HIGH | `OPEN_BLOCKERS.md` |
| 14 MEDIUM, 9 LOW | `OPEN_BLOCKERS.md` |
| Register exhaustiveness is by construction, not mechanical extraction (M-P0-1) | `PHASE_0_AUDIT.md` |
| Golden Repair corpus instantiation deferred to Phase 30 (DEF-004) | `OPEN_BLOCKERS.md` |
| Contract schema files under `docs/contracts/` deferred (DEF-008) | `OPEN_BLOCKERS.md` |
| Clean-test baseline VM image deferred to Phase 36 (DEF-005) | `OPEN_BLOCKERS.md` |
| Unsigned installer vs SmartScreen on a clean baseline (MEDIUM) | `CLEAN_TEST_BASELINE.md` §7 |
| Recorded defects retained as permanent evidence — count is held by the file, not mirrored here | `KNOWN_FAILURES.md` |

## 8. Current phase contract — Phase 3

Derived from authoritative artifacts, not from memory.

| Field | Value | Source |
|---|---|---|
| Name | **Formal State Machines + Capability Graph Schema** | Master Spec §Canonical Implementation Phases |
| Prerequisites | Phase **2** (MACHINE-ACCEPTED) | `IMPLEMENTATION_DEPENDENCY_MATRIX.md` |
| ARK-REQ IDs | **0043, 0044, 0045, 0049** — all MANDATORY | `REQUIREMENT_REGISTER.md` |
| Contract IDs | **C-13** Capability node + query result (`3 (schema) / 9B`) | `CONTRACT_INVENTORY.md` |
| Human gate | none (machine acceptance) | matrix Gate column |

**In scope.** The twelve canonical state machines (`STATE_MACHINES.md`) with states, transitions and *structurally impossible* invalid transitions (0043, 0044). The Capability Graph **schema** — node shape carrying references only (0045). Pre-activation query behaviour returning `NOT_CONFIGURED` (0049).

**Forbidden scope.** Capability Graph **activation** — that is Phase 9B (ADR-0003); population with real permissions, evidence requirements or provider health; any provider runtime; any persistence engine; anything owned by a later phase.

**Evidence required.** `unit` and `prop` for 0043/0044 · `contract` for 0045 · `unit` for 0049.

**Machine acceptance.** Produce a phase report satisfying C-17, then run
`python scripts/run_phase_gate.py 3 4`. Acceptance requires verdict
`PHASE_ACCEPTED_BY_MACHINE`: C1–C5 PASS, 8 architecture gates non-failing,
0 open BLOCKER/HIGH, prerequisites accepted.

## 9. Next exact action

**Begin Phase 3 — Formal State Machines + Capability Graph Schema.**

Do not begin any later phase. Do not activate the Capability Graph.

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
| Generated at HEAD | `85cbcda0bc4e1b26fab9d2059adbb81f8edbcd3f` |
| Generated after | pre-Phase-3 governance hygiene (GH-001 defect-count dereference, GH-002 Phase 2 commit identity, GH-003 advisory-note state removal). Governed artifacts changed, so the §12 refresh was mechanically required, not discretionary. No phase, gate, ADR or requirement state changed |
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
head: 85cbcda0bc4e1b26fab9d2059adbb81f8edbcd3f
branch: main
working_tree_clean: true

requirements_total: 313
requirements_mandatory: 303
requirements_conditional: 8
requirements_optional: 2

verified_by_phase:
  "1": 5
  "2": 23
cumulative_verified: 28

accepted_phases: ["0", "0A", "0B", "1", "2"]
unlocked_phase: "3"
next_exact_action_phase: "3"

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
