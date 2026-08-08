# ARKALI GENESIS v2 — EXECUTION, CAPABILITY, EVIDENCE ARCHITECTURE (PHASE 0A)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1

---

## 1. Capability Graph architecture and schema

Node schema (references only — never copies of another authority's state):

```yaml
capability_node:
  id: str                        # stable capability identifier
  version: int
  prerequisites: [capability_id]
  permission_refs: [policy_rule_id]        # -> control.policy
  evidence_requirement_refs: [ark_req_id]  # -> control.specification
  provider_refs: [provider_id]             # -> control.registry.provider
  isolation_tier: TRUST-0..4
  isolation_backend_probe_ref: probe_id    # -> control.isolation
  runtime_requirements: {...}
  platform_support: [...]
  fallback_refs: [capability_id]
  configured_state: CONFIGURED | UNCONFIGURED
```

**Resolution rule.** `can_perform(capability_id)` resolves every `*_ref` at query time against its owning authority. Health, cost, availability and fallback are **never** stored here — they belong to `control.registry.provider` (ADR-0001).

**Lifecycle.** Schema is delivered at Phase 3; activation at Phase 9B once `control.policy` (P4), `evidence.*` (P6) and `control.registry.provider` (P9) exist. Before activation every query returns `NOT_CONFIGURED` — a determinate answer, never a stub, default or assumption. Consumers between Phase 3 and 9B (notably `execution.scheduler`, Phase 8) must handle `NOT_CONFIGURED` and must not cache capability verdicts.

## 2. Provider / model authority relationship

```
control.registry.provider   (SOLE AUTHORITY)
   identity | model identity | configuration | health | availability | cost | fallback
        ^              ^                ^                    ^
        | ref          | ref            | ref                | ref
control.capability  execution.scheduler  engineering.agent  surfaces.operations
```

No consumer stores, caches, mirrors, defaults or re-derives these values. `surfaces.operations` displays provider state read live from the Registry — this is what makes "no fake telemetry" enforceable rather than aspirational.

## 3. Durable execution architecture

`execution.durable` owns: persistent job state, checkpoints, heartbeat, progress evidence, idempotency keys, bounded retries, timeout, cancel, pause/resume, approvals/signals, crash recovery, dead-letter. Temporal-grade durability is achieved with the local persistence layer; Temporal is not a dependency (ADR-0007).

No long AI work occurs inside an HTTP request. API handlers enqueue a durable job and return a job reference.

Crash recovery: on start, every `RUNNING` job without a live heartbeat transitions to `RECOVERABLE`, then `RESUMING`. Silent loss is a verification FAIL.

## 4. Worker / resource scheduler architecture

`execution.scheduler` owns allocation. Worker classes: agent, provider, build/test, browser, sandbox, local-AI, computer-use. Each worker declares: class, concurrency limit, resource profile, required TRUST tier, required isolation properties, heartbeat interval.

Admission control: a job is admitted only when (a) its capability resolves other than `NOT_CONFIGURED`, (b) an isolation composition satisfies its tier, and (c) resource budget is available. Failure of one worker class or provider must not crash unrelated capabilities (failure-domain isolation).

## 5. Workflow graph / executor architecture

```
   canonical_workflow_graph (persisted, versioned, content-hashed)   <-- SOLE AUTHORITY
        |                                    |
        | render                             | execute
        v                                    v
   UI graph view                    Workflow Executor
                                             |
                                    optional derived cache
                                    (deterministically derived,
                                     hash-bound, invalidated on change)
```

- The persisted versioned graph is the sole authority. UI and executor are two views of the same revision.
- A derived compiled/cached representation is permitted only if deterministically derived from the canonical revision, hash-bound to it, and invalidated by any change to it (ADR-0004).
- A derived representation whose bound hash ≠ current canonical revision is **never executed**.
- `HUMAN APPROVAL` is an enforced policy stop resolved by the PDP, not a visual element.

## 6. Artifact / provenance architecture

Artifacts are immutable, versioned, content-addressed. Metadata: content hash, producer agent, provider/model, task ID, specification version, context hash, parent artifacts, normalization, tests, evidence links, timestamps. `evidence.artifact` is the sole authority for artifact identity; `evidence.audit` for chain integrity.

## 7. Acceptance / evidence architecture

```
  Evidence Graph:  ARK-REQ -> Contract -> Artifact -> Test -> Evidence -> Result
                      ^                                              |
                      |______________ coverage denominator ___________|

  acceptance.engine
    +-- Phase Gate Checker (deterministic, from Phase 2)  -> phase gating pre-P13
    +-- Acceptance Engine  (from Phase 13)                -> capability verdicts
    +-- HUMAN GATES 1..8   (human authority)              -> reserved decisions
```

Coverage is computed **only** from `REQUIREMENT_REGISTER.md`. Applicability is read from the register; it is never judged at runtime by an implementing actor. Acceptance contracts and the engine are Protected Core, so an actor cannot weaken what measures it.

## 8. Backup / recovery architecture

Minimal backup/restore ships in Phase 5 with persistence. Full migration safety and integration land in Phase 20 — the two are distinct concerns and distinct phase titles so no duplicate-authority violation arises.

Migration sequence: impact → backup → dry run → integrity → candidate migration → application tests → **APPLY (HUMAN GATE 6 on real/stable data)** → verify → rollback point.

Recovery Supervisor (Phase 22B, before Self-Evolution at Phase 23): bad core candidate → launch → health check fails → `ROLLBACK_STABLE` atomic pointer switch to a previously verified immutable revision → failure record → stable available. It is deterministic, produces evidence, performs no content transformation, and is the only path that touches stable directly.
