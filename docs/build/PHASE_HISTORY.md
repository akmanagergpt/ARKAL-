# PHASE HISTORY — ARKALI GENESIS v2

| # | Phase | Outcome | Commit | Notes |
|---|---|---|---|---|
| 1 | Repository bootstrap (pre-phase) | COMPLETE | `d8572dd` | canonical greenfield baseline: `.gitignore` + 4 canonical documents |
| 2 | Deterministic line endings (pre-phase) | COMPLETE | `4f9213f` | `.gitattributes`; LF stability proven by simulated fresh checkout |
| 3 | Canonical architecture repair (pre-phase) | COMPLETE | `079c925` | 9 BLOCKER + 16 HIGH findings repaired in the canonical set |
| 4 | **PHASE 0A — Canonical Architecture** | **CANDIDATE** | pending | architecture package produced; no implementation |
| 5 | **PHASE 0B — Governance & Executable Contracts** | **CANDIDATE** | pending | register, authority map, checker spec, ADRs |
| 6 | PHASE 0 acceptance package | **AWAITING HUMAN GATE 1** | — | not self-accepted |

## Phase 0 report

**Phase ID / objective.** Phase 0A+0B — produce the canonical architecture and governance contracts required before any implementation, resolving architectural ownership so no concern has two authorities.

**ARK-REQ IDs closed.** ARK-REQ-0033, 0034, 0035, 0036, 0039 (register mechanism); ARK-REQ-0018, 0030, 0108, 0109 (authority map, budgets, protected core declaration); ARK-REQ-0090, 0091 (Golden Repair corpus definition); ARK-REQ-0182, 0183 (phase model, single acceptance package); ARK-REQ-0221, 0222, 0224, 0225 (repository state and Phase 0 deliverables). All remaining 296 entries are open and owned by later phases.

**Files created.** 12 (listed in `EVIDENCE_INDEX.md`). **Files modified.** 0 canonical documents.

**Public contracts.** None — Phase 0 defines no runtime contracts. Contract inventory is scheduled for Phase 2.

**Migrations.** None.

**State-machine / capability changes.** Twelve state machines inventoried with states, transitions, forbidden transitions and authorities. Capability Graph schema defined; not populated.

**Tests actually executed.** Two mechanical validations, both run and recorded:
- `AUTHORITY_MAP.yaml` YAML parse + invariant check — exit 0. 31 contexts, 39 concerns, 14 operation classes, 8 gates, 0 duplicate concern authorities, all budgets numeric, `stable_mutation.direct_mutation_permitted_by == []`.
- `REQUIREMENT_REGISTER.md` structural count — exit 0. 311 entries, 311 unique, 0 duplicate IDs, 300 MANDATORY / 9 CONDITIONAL / 2 OPTIONAL, 0 CONDITIONAL entries missing an applicability rule.

No application test suite was executed: NOT_APPLICABLE — Phase 0 produces no implementation.

**Architecture checks.** NOT_TESTED. The eight gates require source code to analyse; they become executable in Phase 2.

**Duplicate / shadow check.** PASS at the declaration level — 0 duplicate concern authorities in `AUTHORITY_MAP.yaml`. Code-level detection is NOT_TESTED until Phase 2.

**Security findings.** None. Phase 0 introduces no executable surface.

**Fake-success scan.** PASS — no capability is claimed as implemented. Every unimplemented item is recorded as NOT_TESTED, NOT_CONFIGURED or NOT_APPLICABLE with a reason.

**Evidence created.** `EVIDENCE_INDEX.md` with two mechanical validation records.

**Limitations.** Phase 0 is documentation only. The architecture is unproven until code exists. Two self-introduced defects were caught during self-audit and corrected before commit (a fullwidth `＃` breaking YAML parsing; unverified coverage counts in the register's Appendix B) — both are recorded in `KNOWN_FAILURES.md`.

**Blockers.** None internal. External: HUMAN GATE 1.

**Next exact action.** Submit Phase 0A+0B as one package for HUMAN GATE 1. Do not begin Phase 1.

**Status.** PASS (internal audit) — **AWAITING HUMAN GATE 1**. Not accepted.
