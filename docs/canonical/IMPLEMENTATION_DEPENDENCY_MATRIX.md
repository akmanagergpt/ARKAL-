# ARKALI GENESIS v2 — IMPLEMENTATION DEPENDENCY MATRIX (PHASE 0A)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1

Hard prerequisites per canonical phase. A phase may not begin until every prerequisite has produced its acceptance evidence. Prerequisites are transitive; only direct ones are listed.

Legend — `GATE n` = human gate required to exit · `DENY` = policy-enforced precondition, not convention.

| Phase | Title | Direct prerequisites | Produces (contracts / capabilities) | Gate |
|---|---|---|---|---|
| 0A | Canonical Architecture | canonical set | architecture, contract inventory, verification architecture, this matrix | — |
| 0B | Governance & Executable Contracts | 0A | register, authority map, budgets, protected core, isolation matrix, corpus definition, Checker spec | **GATE 1** (0A+0B as one package) |
| 1 | Repository Bootstrap | **GATE 1** | repository skeleton | — |
| 2 | Foundation + Contracts + Phase Gate Checker | 1 | C-01, C-04, C-17, C-18; T1–T4; 8 architecture gates + negative controls | — |
| 3 | Formal State Machines + Capability Graph **Schema** | 2 | 12 state machines, C-13 schema | — |
| 4 | Security + Governance + Isolation Backends | 2, 3 | C-07, C-08, C-09, C-10; PDP/PEP; Protected Core enforcement; backend probe | — |
| 5 | Persistence + Project Registry + Minimal Backup/Restore | 2, 4 | C-03, C-12; T5, T11; first frontend slice | — |
| 6 | Evidence Plane + Provenance + Artifact Store | 5 | C-14, C-15 | — |
| 7 | Durable Job + Workflow Core | 5, 6 | C-19 | — |
| 8 | Resource Scheduler + Worker Contracts | 7 | C-21 | — |
| 9 | Provider + Model Runtime | 4, 6, 8 | C-11 | — |
| **9B** | **Capability Graph Activation** | **3, 4, 6, 9** | activated C-13 (references resolve) | — |
| 10 | Agent Runtime + Harness Engineering | 9, 9B | C-22, C-23 | — |
| 11 | Code Intelligence + Digital Twin | 10 | C-24 | — |
| 12 | Candidate Workspace + Semantic Assembly | 11 | C-25 | — |
| 13 | Acceptance Infrastructure + Evidence Graph | 6, 12 | C-16; Acceptance Engine | — |
| 14 | Repair / Root Cause / Convergence | 13 | C-26 | — |
| 15 | Requirement + Architecture Intelligence | 13 | — | — |
| 16 | AI Software Factory | 12, 14, 15 | full generation pipeline | — |
| 17 | Visual Workflow Studio | 7, 8, 13 | C-20 | — |
| 18 | Knowledge + Verified Components | 13 | C-28 | — |
| 19 | Import / Reverse Engineering / Rescue | 4 (TRUST-3 backend), 12 | C-29 | GATE 4 per import |
| 20 | Database Migration Safety + Full Backup/Recovery | 5, 6 | migration safety chain | **GATE 6** on APPLY |
| 21 | Plugins + Integrations + Research | 4, 9 | C-30 | GATE 4 if boundary changes |
| 22 | Local AI + Model Laboratory | 4, 9 | local adapters | — |
| **22B** | **Recovery Supervisor + Core Rollback Verification** | **5, 20, 26** | C-32; verified rollback | — |
| 23 | Self-Evolution | **22B (DENY until verified)**, 13, 16 | C-33 | **GATE 2** |
| 24 | Generated Product Evolution SDK | 16, 13 | C-36 | GATE 3 where approval-gated |
| 25 | Operations + Hardware Intelligence | 7, 9, 11 | C-34 | — |
| 26 | Release / Supply Chain / Deployment | 6, 13 | C-31 | — |
| 27 | Command Center Consolidation + Skill Modes | 5…25 slices | C-35 consolidation | — |
| 28 | Tauri Desktop | 27 | desktop shell | — |
| 29 | Installer + Recovery Supervisor Integration | 26, 28, 22B | ARKALI_Setup.exe | — |
| 30 | Golden Product + Golden Repair Verification | 16, 14, 24 | Golden evidence; **instantiated corpus** | — |
| 31 | Chaos / Mutation / Generalization Verification | 30 | T7, T8, T12 evidence | — |
| 32–35 | Hardening Rounds 1–4 | 31 | round records with declared budgets | GATE 8 on budget exception |
| 36 | Clean Environment Full Acceptance | 29, 31, 35 | L3 evidence | — |
| 37 | Production Release | 36 | release + quality report | **GATE 7** |

## Critical ordering constraints (enforced, not advisory)

1. **9B after 4, 6 and 9.** The Capability Graph resolves permissions, evidence requirements and provider health by reference. Before activation every query returns `NOT_CONFIGURED`; Phase 8 consumers must tolerate it and must not cache capability verdicts.
2. **22B before 23.** Self-Evolution is `DENY` at the PDP until Recovery Supervisor rollback verification passes. A Recovery Supervisor that exists but is unverified does not satisfy it.
3. **Minimal backup/restore in 5, not 20.** State begins accumulating at Phase 5; a proven restore path must exist from the same phase. Phase 20 adds migration safety and full recovery — a distinct concern, distinctly titled, so no duplicate lifecycle authority arises.
4. **Frontend slices from Phase 5.** Every capability with a production-visible state ships its own UI increment. Phase 27 consolidates; it is not first integration.
5. **26 before 22B.** Rollback targets an immutable revision under Release Authority, so revision identity must exist first.
6. **30 before 31.** Mutation and chaos verification need a real generated product to perturb.

## Cycle check

The prerequisite relation was checked for cycles: **none found**. The graph is a DAG rooted at 0A with a single human-gate cut between 0B and 1.
