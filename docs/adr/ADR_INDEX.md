# ADR INDEX — ARKALI GENESIS v2

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1

ADRs are immutable once accepted. A superseded ADR is retained and marked, never deleted or edited in place.

| ADR | Title | Status | Resolves |
|---|---|---|---|
| ADR-0001 | Canonical authority map and machine-readable enforcement | PROPOSED | ARK-REQ-0018, 0019, 0052, 0351 |
| ADR-0002 | Isolation Backend abstraction — properties, not technologies | PROPOSED | ARK-REQ-0017, 0113, 0118–0123 |
| ADR-0003 | Capability Graph split: schema Phase 3, activation Phase 9B | PROPOSED | ARK-REQ-0046, 0047, 0048, 0049 |
| ADR-0004 | Canonical workflow graph sole authority; hash-bound derived caches | PROPOSED | ARK-REQ-0063, 0064, 0065, 0332 |
| ADR-0005 | Protected Core membership and modification path | PROPOSED | ARK-REQ-0108–0112, 0236 |
| ADR-0006 | SQLite+WAL local-first with PostgreSQL-ready abstractions | PROPOSED | ARK-REQ-0011, 0012 |
| ADR-0007 | Durable runtime without a mandatory Temporal dependency | PROPOSED | ARK-REQ-0059, 0061 |
| ADR-0008 | Numeric architecture budgets and GATE 8 exception path | PROPOSED | ARK-REQ-0030, 0031, 0032 |
| ADR-0009 | Promotion and rollback as separate lifecycle authorities | PROPOSED | ARK-REQ-0023, 0155, 0156 |

---

## ADR-0001 — Canonical authority map and machine-readable enforcement
**Context.** The specification forbids duplicate authorities and makes it a zero-tolerance release gate, but a prose architecture cannot be checked mechanically, and a checker that searches duplicate class names would pass vacuously.
**Decision.** `docs/canonical/AUTHORITY_MAP.yaml` is the machine-readable declaration of concern→owner, bounded contexts, dependency direction, lifecycle and state-machine authorities, protected-core membership and architecture budgets. All eight architecture gates evaluate against it, and each must demonstrate detection on a deliberately violating fixture.
**Consequences.** Adding a concern requires a map entry. A detector returning 0 without a passing negative control is treated as FAIL.

## ADR-0002 — Isolation Backend abstraction
**Context.** Trust tiers were descriptive, naming no enforcement mechanism, while sandbox enforcement is a mandatory security verification. Binding tiers directly to Windows Sandbox or Hyper-V would make the whole product depend on a host feature.
**Decision.** Tiers declare required **security properties**; Isolation Backends declare **provided properties**; backends compose. A capability executes only if some available composition satisfies all required properties. Otherwise the capability is UNSUPPORTED and execution is DENY.
**Consequences.** Losing kernel-isolation backends disables TRUST-3/4 capabilities only; the factory, TRUST-2 generation and verification continue. A tier is never silently downgraded. New backends can be added without touching tier definitions.

## ADR-0003 — Capability Graph split
**Context.** The graph's node attributes include permissions (Phase 4), evidence requirements (Phase 6) and provider health (Phase 9), yet the graph was scheduled at Phase 3 — a forward dependency that would force stubs, and stubs would become a shadow authority.
**Decision.** Phase 3 delivers schema only. Phase 9B activates the graph after its referenced authorities exist. Between them every capability query returns `NOT_CONFIGURED`.
**Consequences.** `NOT_CONFIGURED` is a determinate answer, preserving the determinism requirement. Phase 8 consumers must tolerate it and must not cache capability verdicts.

## ADR-0004 — Canonical workflow graph authority
**Context.** UI graph and backend execution must be the same workflow, but a naive reading forbids all compilation and caching, which is impractical for an executor.
**Decision.** The persisted versioned graph is the sole authority. Derived compiled or cached representations are permitted only when deterministically derived from it, hash-bound to it, and invalidated by any change to it. A derived representation whose bound hash differs from the current canonical revision is never executed.
**Consequences.** Caching is allowed; divergence is not. Acceptance proves invalidation and stale-hash non-execution.

## ADR-0005 — Protected Core
**Context.** Acceptance independence cannot be procedural if the implementing actor can edit the contracts measuring it, and the canonical set made protected-core violations a zero-tolerance gate without defining membership.
**Decision.** Membership is declared in `AUTHORITY_MAP.yaml` (`protected_core: true`) covering policy, isolation, architecture definitions, evidence integrity, acceptance engine, release and recovery. Changes run the Stable Core candidate lifecycle under the stronger verification profile and require HUMAN GATE 2.
**Consequences.** Independence becomes structural. Routine acceptance-contract evolution is possible but gated.

## ADR-0006 — SQLite+WAL with PostgreSQL-ready abstractions
**Context.** Local-first is a product requirement; PostgreSQL readiness is stated but never verified.
**Decision.** SQLite+WAL is the shipping engine. Repository interfaces are engine-neutral so a PostgreSQL adapter remains possible. The **abstraction property is MANDATORY** (ARK-REQ-0012) and is verified by architecture test — no engine-specific SQL outside `kernel.persistence`. Verified *operation* on PostgreSQL is not a canonical requirement and is therefore not registered.
**Consequences.** No raw SQL outside `kernel.persistence`. The abstraction is enforced from Phase 5. PostgreSQL as a runtime target remains unexercised and is reported honestly as such, without weakening the abstraction requirement.

## ADR-0007 — Durable runtime without Temporal
**Context.** Temporal-grade durability is required; a mandatory Temporal dependency is not acceptable for a local-first desktop product.
**Decision.** Implement durability on the local persistence layer: persistent job state, checkpoints, heartbeats, idempotency keys, bounded retries, crash recovery, dead-letter.
**Consequences.** "Temporal-grade" is verified behaviorally through chaos and durable-restart evidence, not by comparison to Temporal.

## ADR-0008 — Numeric architecture budgets
**Context.** The prohibition on giant orchestration modules was absolute in one document and waivable by written justification in another — self-justifiable by an AI.
**Decision.** Budgets are numeric and declared in `AUTHORITY_MAP.yaml`. Any exception requires an approved ADR and HUMAN GATE 8, and may never rest on a justification authored by an implementing actor.
**Consequences.** Initial budgets are deliberately generous; the purpose is to catch a central orchestrator, not to police ordinary modules.

## ADR-0009 — Promotion and rollback as separate authorities
**Context.** If one component both promotes and rolls back, a failed promotion could approve its own recovery.
**Decision.** `lifecycle.release` owns promotion; `lifecycle.recovery` owns rollback. `ROLLBACK_STABLE` is invocable only by the Recovery Supervisor, targets only a previously verified immutable revision, performs no transformation, and emits evidence.
**Consequences.** Two authorities, one direction of trust. Recovery Supervisor must be verified (Phase 22B) before Self-Evolution (Phase 23) is permitted.
