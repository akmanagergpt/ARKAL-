# DECISION LOG — ARKALI GENESIS v2

Decisions taken during Phase 0 that are not large enough for an ADR, or that record a human ruling. Architectural decisions of consequence live in `docs/adr/ADR_INDEX.md`.

| # | Decision | Rationale | Authority |
|---|---|---|---|
| D-001 | 31 bounded contexts across a 7-layer model | Gives every canonical concern exactly one home and makes dependency direction mechanically checkable | Phase 0A |
| D-002 | Contexts consolidated into 4 architecture documents rather than one file per required artifact | The canonical set lists ~27 required 0A artifacts; coherent grouped documents beat 27 fragments that would drift apart | Phase 0A |
| D-003 | Layer rule: strictly-lower dependencies only, same-layer edges enumerated explicitly | An unenumerated same-layer edge is how cycles appear; making the 7 legitimate edges explicit makes the rest detectable | Phase 0A |
| D-004 | Promotion and rollback split across two lifecycle authorities | Prevents a failed promotion from approving its own recovery | ADR-0009 |
| D-005 | ID ranges allocated sparsely (MS 0001–0186, BP 0200–0243, VDC 0300–0380) | New requirements can be added inside their source block without renumbering; IDs are immutable | Phase 0B |
| D-006 | 9 CONDITIONAL entries only; everything else MANDATORY or OPTIONAL | Conditional classification is the main scope-narrowing exploit; each of the 9 has an objective machine-evaluable rule | Phase 0B |
| D-007 | Architecture budgets set deliberately generous (400 logical lines, fan-out 12) | Purpose is catching a central orchestrator, not policing ordinary modules; tight budgets would generate GATE 8 noise | ADR-0008 |
| D-008 | Phase Gate Checker specified but **not** implemented in Phase 0 | Canonical phase model places implementation in Phase 2; Phase 0 produces no code | Phase 0B |
| D-009 | Golden Repair corpus **defined** but not populated | Corpus instances require an accepted Golden Product to inject into | Phase 0B |
| D-010 | Phase 0 commits as a candidate, explicitly not accepted | Canonical set forbids self-acceptance; commit records work, GATE 1 records acceptance | Phase 0B |
| D-011 | PyYAML used only to validate the authority map parses | Read-only validation of a Phase 0 artifact; no runtime dependency added, no lockfile, no install performed | Phase 0B |
| D-012 | Golden Repair: **definition** at Phase 0B, **instantiation** at Phase 30 | Derived from canonical text, not chosen: BP §Phase 0B says "corpus **definition**" and every sibling item in that list is a definition/specification/declaration/design; MS defines the corpus as "**injected** defects" executed "against a Golden Product revision that has already passed acceptance". Injection requires a target that does not exist before Phase 30 | HG1-02 correction |
| D-013 | Instantiation registered as new ARK-REQ-0187/0188 rather than by amending 0090/0091 | MS §Canonical Requirement Register makes IDs immutable and forbids reuse/renumbering. The reserved gap 0187–0199 in the MS block exists for exactly this | HG1-02 correction |
| D-014 | ARK-REQ-0012 reclassified CONDITIONAL → MANDATORY | MS §Frozen technology direction states "PostgreSQL-ready abstractions" unconditionally. The prior rule made the abstraction inapplicable in the default SQLite deployment — narrowing an unconditional requirement, the exact scope-reduction exploit the register exists to prevent | HG1-03 correction |
| D-015 | Verified *operation* on PostgreSQL is not registered as a requirement | No canonical statement requires it. Registering an unrequired obligation would be as wrong as omitting a required one | HG1-03 correction |
| D-016 | Contract inventory delivered at Phase 0A, not deferred to Phase 2 | BP §Phase 0A lists "contract inventory" explicitly. Phase 2 implements schemas; the inventory is architecture | HG1-01 correction |

## Human rulings incorporated (recorded, not decided here)

| Ruling | Source | Effect |
|---|---|---|
| HUMAN GATE 8 ratified | human authority | Architecture-budget exception is a human gate |
| Direct-AI benchmark states | human authority | `NOT_CONFIGURED` / verified `EXTERNAL_UNAVAILABLE` do not block release; never fabricate an external PASS |
| Phase 0 split 0A/0B | human authority | Two parts, one acceptance package, one gate |
| Workflow derived caches | human authority | Permitted when deterministically derived, hash-bound and invalidated |
| ROLLBACK_STABLE constraints | human authority | Recovery-Supervisor-only, verified immutable target, atomic pointer switch preferred, no transformation |
| Autonomy model | human authority | Machine acceptance for normal phases; stop only at the 8 gates or a failed machine gate |
| Isolation Backend abstraction | human authority | Properties, not technologies; unsatisfiable ⇒ UNSUPPORTED/DENY; never silently downgrade |
