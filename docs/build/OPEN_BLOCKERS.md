# OPEN BLOCKERS — ARKALI GENESIS v2

**As of:** Phase 0 candidate

## Internal blockers

**None.** Internal BLOCKER count = 0, internal HIGH count = 0 (see `docs/build/PHASE_0_AUDIT.md`).

## External blockers

| ID | Blocker | Type | Owner | Blocks |
|---|---|---|---|---|
| EXT-001 | HUMAN GATE 1 — Phase 0A+0B acceptance not yet granted | HUMAN GATE | human acceptance authority | Phase 1 and all subsequent phases |

Phase 1 is locked. This is the designed state, not a defect.

## Deferred items (not blockers, tracked so they are not lost)

| ID | Item | Deferred to | Reason |
|---|---|---|---|
| DEF-001 | Architecture gate implementation + negative-control fixtures | Phase 2 | requires source code to analyse |
| DEF-002 | Phase Gate Checker implementation | Phase 2 | specification only in Phase 0 |
| DEF-003 | Isolation backend availability probe | Phase 4 | requires runtime |
| DEF-004 | Golden Repair defect corpus **content** | after first accepted Golden Product | corpus defined; instances need a real product |
| DEF-005 | Canonical Windows clean-test baseline **image** | Phase 36 | definition exists; VM snapshot is an acceptance-environment asset |
| DEF-006 | `ARKALI_RELEASE_QUALITY_REPORT.md` content contract | Phase 26 | LOW; undefined in the canonical set, carried forward honestly |
| DEF-007 | Contract inventory (public API/schema definitions) | Phase 2 | contract-first work belongs with foundations |

## Residual MEDIUM/LOW findings carried from the canonical repair

These were reported at the canonical repair and remain open by design; none blocks Phase 0.

MEDIUM: installer code-signing vs SmartScreen on a clean baseline · "Temporal-grade" unmeasurable except behaviorally · mutation-testing budget at system scale · fine-tuning acceptance path · air-gapped signing key management · Git branching/remote model unspecified · knowledge-lifecycle transition rules undefined · Phase 0 deliverable breadth · workflow derived-cache invalidation complexity · Import/Rescue phase-level budget.

LOW: `ARKALI_RELEASE_QUALITY_REPORT.md` contents · `ADR_INDEX` format conventions · PostgreSQL path unverified · "Transaction/Transactions" plural mismatch in the canonical set · `docs/canonical` vs `docs/contracts` scope overlap · MCP adapters unverified · skill-mode verification implied via Phase 27 rather than an explicit VDC clause.
