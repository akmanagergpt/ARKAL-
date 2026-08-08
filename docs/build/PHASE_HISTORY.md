# PHASE HISTORY — ARKALI GENESIS v2

| # | Phase | Outcome | Commit | Notes |
|---|---|---|---|---|
| 1 | Repository bootstrap (pre-phase) | COMPLETE | `d8572dd` | canonical greenfield baseline: `.gitignore` + 4 canonical documents |
| 2 | Deterministic line endings (pre-phase) | COMPLETE | `4f9213f` | `.gitattributes`; LF stability proven by simulated fresh checkout |
| 3 | Canonical architecture repair (pre-phase) | COMPLETE | `079c925` | 9 BLOCKER + 16 HIGH findings repaired in the canonical set |
| 4 | **PHASE 0A — Canonical Architecture** | **CANDIDATE** | pending | architecture package produced; no implementation |
| 5 | **PHASE 0B — Governance & Executable Contracts** | **CANDIDATE** | pending | register, authority map, checker spec, ADRs |
| 6 | PHASE 0 acceptance package (candidate rev 1) | REJECTED by review | `85f3c1c` | HG1-01…HG1-04 |
| 7 | PHASE 0 acceptance package (candidate rev 2) | REJECTED by review | `5c6a28d` | HG1-05…HG1-09 |
| 8 | PHASE 0 acceptance package (candidate rev 3) | REJECTED by review | `63ab9a8` | HG1-10…HG1-12 |
| 9 | **PHASE 0 acceptance package (candidate rev 4)** | **ACCEPTED — HUMAN GATE 1** | `007ebf6` | record `HGR-001`; Phase 0A + 0B accepted as one package; 9 ADRs PROPOSED → ACCEPTED; Phase 1 unlocked |
| 10 | PHASE 1 — Repository Bootstrap (candidate rev 1) | NOT ACCEPTED | `0ad45a7` | F-0015 HIGH open; preserved unamended as the record of the defect |
| 11 | **ERR-001 governance erratum + PHASE 1 repair** | **MACHINE-ACCEPTED** | pending | validator 12/12, backend suite 7/7, negative control 6/6. 5/5 Phase 1 ARK-REQs PASS. BLOCKER 0, HIGH 0. **Phase 2 unlocked** |

## Phase 0 report

**Phase ID / objective.** Phase 0A+0B — produce the canonical architecture and governance contracts required before any implementation, resolving architectural ownership so no concern has two authorities.

**ARK-REQ IDs closed (18).** Register mechanism: 0033, 0034, 0035, 0036, 0039. Authority map / budgets / protected core: 0018, 0030, 0108, 0109. Golden Repair corpus **definition**: 0090, 0091. Phase model and single acceptance package: 0182, 0183. Repository state and Phase 0 deliverables: 0221, 0222, 0224, 0225. Contract inventory: 0230 (definition-level only — schemas are Phase 2).

**ARK-REQ IDs explicitly NOT closed, with state.** ARK-REQ-0187 and ARK-REQ-0188 (instantiated, content-hashed corpus) = **NOT_APPLICABLE at Phase 0B** — no accepted Golden Product exists as an injection target until Phase 30. All remaining 295 entries are open and owned by later phases.

**Correction record.** An earlier draft of this report claimed ARK-REQ-0090 and 0091 closed while `BUILD_STATE`, `OPEN_BLOCKERS` and `PHASE_0_AUDIT` recorded the corpus as unpopulated and deferred. That was a false closure of a mandatory requirement and an internal contradiction between Phase 0 artifacts. It is corrected here: the canonical Phase 0B obligation is the corpus *definition* (Build Protocol §Phase 0B), now delivered as `docs/canonical/GOLDEN_REPAIR_CORPUS_DEFINITION.md`; the instantiation obligation is separately registered as 0187/0188 against Phase 30. Logged as F-0005.

**Files created.** 20 Phase 0 artifacts (listed in `EVIDENCE_INDEX.md`). **Canonical source documents modified.** 0.

**Public contracts.** None implemented. 36 canonical contract families are **inventoried** in `docs/canonical/CONTRACT_INVENTORY.md` with owner, producer, consumers, category, planned schema location, versioning rule, compatibility class, evidence responsibility and implementation phase. Schema files are Phase 2 work; the inventory is Phase 0A work and is delivered.

**Migrations.** None.

**State-machine / capability changes.** Twelve state machines inventoried with states, transitions, forbidden transitions and authorities. Capability Graph schema defined; not populated.

**Tests actually executed.** Two mechanical validations, both run and recorded:
- `AUTHORITY_MAP.yaml` YAML parse + invariant check — exit 0. 31 contexts, 39 concerns, 14 operation classes, 8 gates, 0 duplicate concern authorities, all budgets numeric, `stable_mutation.direct_mutation_permitted_by == []`.
- `REQUIREMENT_REGISTER.md` structural count — exit 0. 313 entries, 313 unique, 0 duplicate IDs, 303 MANDATORY / 8 CONDITIONAL / 2 OPTIONAL, 0 CONDITIONAL entries missing an applicability rule, 0 orphan applicability rules.

No application test suite was executed: NOT_APPLICABLE — Phase 0 produces no implementation.

**Architecture checks.** NOT_TESTED. The eight gates require source code to analyse; they become executable in Phase 2.

**Duplicate / shadow check.** PASS at the declaration level — 0 duplicate concern authorities in `AUTHORITY_MAP.yaml`. Code-level detection is NOT_TESTED until Phase 2.

**Security findings.** None. Phase 0 introduces no executable surface.

**Fake-success scan.** PASS — no capability is claimed as implemented. Every unimplemented item is recorded as NOT_TESTED, NOT_CONFIGURED or NOT_APPLICABLE with a reason.

**Evidence created.** `EVIDENCE_INDEX.md` with two mechanical validation records.

**Second correction (HUMAN GATE 1, review 2).** Five further defects were found by independent review of the corrected package and are closed: F-0009 (phase-order deadlock 22B↔26 masked by a false-negative cycle check), F-0010 (impossible forward prerequisite C-03 + Phase 0B deliverable miscount 12 vs 11), F-0011 (stale denominators presented as current PASS basis in three artifacts). Two deterministic validators were added — `scripts/check_phase_graph.py` (9/9 PASS, with a negative control that reproduces the deadlock cycle) and `scripts/check_phase0_deliverables.py` (0A 16/16, 0B 11/11, counts parsed from the canonical lists).

**Limitations.** Phase 0 is documentation only. The architecture is unproven until code exists. Seven self-introduced defects are recorded in `KNOWN_FAILURES.md`: four caught by internal self-audit (F-0001…F-0004) and **three caught only by independent review** (F-0005 false closure of ARK-REQ-0090/0091, F-0006 five missing Phase 0A deliverables, F-0007 ARK-REQ-0012 misclassification). That the internal audit passed while three canonical traceability defects remained is itself the most significant limitation of this phase.

**Blockers.** None internal. External: HUMAN GATE 1.

**Next exact action.** Submit Phase 0A+0B as one package for HUMAN GATE 1. Do not begin Phase 1.

**Status.** **ACCEPTED.** HUMAN GATE 1 granted by the human acceptance authority on candidate `007ebf6e9275fa99d932022004440b1b869701d4`, following independent inspection of the actual artifacts and independent execution of the validation scripts. Recorded as `HGR-001` in `docs/acceptance/HUMAN_GATE_RECORDS.md`.

Phase 0 required four candidate revisions. Fourteen defects were recorded, ten of them found by independent review rather than self-audit — the record of that is retained in full and is not superseded by acceptance.
