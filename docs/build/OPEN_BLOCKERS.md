# OPEN BLOCKERS — ARKALI GENESIS v2

**As of:** Phase 0 candidate

## Internal blockers

**None open.** Internal BLOCKER = 0, internal HIGH = 0. F-0015 (the one Phase 1 HIGH) was closed by governance erratum ERR-001.

Three HIGH defects were found by independent review at HUMAN GATE 1 and are now closed: F-0005 (false closure of ARK-REQ-0090/0091), F-0006 (five Phase 0A deliverables absent), F-0007 (ARK-REQ-0012 misclassification). See `KNOWN_FAILURES.md`.

## External blockers

| ID | Blocker | Type | Owner | Blocks |
|---|---|---|---|---|
| ~~EXT-001~~ | ~~HUMAN GATE 1 — Phase 0A+0B acceptance not yet granted~~ | HUMAN GATE | human acceptance authority | **CLOSED** — granted on candidate `007ebf6`, record `HGR-001` |
| ~~EXT-002~~ | ~~F-0015 — `engineering.import` module root is a Python reserved keyword~~ | HIGH / GOVERNANCE | human acceptance authority | **CLOSED** — governance erratum ERR-001 authorized and applied |

**No external blockers open.** Phase 1 is machine-accepted; Phase 2 is unlocked.

Next gate condition: **HUMAN GATE 2** at Phase 23 (Stable Core promotion), or an earlier trigger of GATE 4 (security boundary change), GATE 5 (applicability waiver), GATE 6 (migration APPLY to real/stable data) or GATE 8 (architecture budget exception).

## Deferred items (not blockers, tracked so they are not lost)

| ID | Item | Deferred to | Reason |
|---|---|---|---|
| DEF-001 | Architecture gate implementation + negative-control fixtures | Phase 2 | requires source code to analyse |
| DEF-002 | Phase Gate Checker implementation | Phase 2 | specification only in Phase 0 |
| DEF-003 | Isolation backend availability probe | Phase 4 | requires runtime |
| DEF-004 | Golden Repair corpus **instantiation** (ARK-REQ-0187, 0188) | Phase 30 | Definition delivered at Phase 0B per BP §Phase 0B. Instantiation requires an accepted Golden Product as injection target — state is NOT_APPLICABLE at Phase 0B, not deferred-and-closed |
| DEF-005 | Canonical Windows clean-test baseline **image** | Phase 36 | definition exists; VM snapshot is an acceptance-environment asset |
| DEF-006 | `ARKALI_RELEASE_QUALITY_REPORT.md` content contract | Phase 26 | LOW; undefined in the canonical set, carried forward honestly |
| ~~DEF-007~~ | ~~Contract inventory~~ | — | **WITHDRAWN.** Deferring it was defect F-0006: Build Protocol §Phase 0A requires the inventory at Phase 0A. Delivered as `docs/canonical/CONTRACT_INVENTORY.md`. Phase 2 implements the schemas, not the inventory |
| DEF-008 | Contract **schema files** under `docs/contracts/` | Phase 2 | the inventory (0A) names 36 families and their planned locations; the schemas themselves are implementation |

## Residual MEDIUM/LOW findings carried from the canonical repair

These were reported at the canonical repair and remain open by design; none blocks Phase 0.

Opened at Phase 3, **all now closed**: F-0018 closed by erratum ERR-002 (Plugin `REMOVED` is terminal) · F-0019 closed — all 9 numeric budgets are now evaluated by the gate · F-0020 closed by erratum ERR-003 (ratified budget measurement contract; three exposed violations repaired by decomposition) · F-0021 opened and closed within Phase 3 (expiring negative controls). No Phase 3 finding remains open.

MEDIUM: installer code-signing vs SmartScreen on a clean baseline · "Temporal-grade" unmeasurable except behaviorally · mutation-testing budget at system scale · fine-tuning acceptance path · air-gapped signing key management · Git branching/remote model unspecified · knowledge-lifecycle transition rules undefined · Phase 0 deliverable breadth · workflow derived-cache invalidation complexity · Import/Rescue phase-level budget.

LOW: `ARKALI_RELEASE_QUALITY_REPORT.md` contents · `ADR_INDEX` format conventions · PostgreSQL path unverified · "Transaction/Transactions" plural mismatch in the canonical set · `docs/canonical` vs `docs/contracts` scope overlap · MCP adapters unverified · skill-mode verification implied via Phase 27 rather than an explicit VDC clause.
