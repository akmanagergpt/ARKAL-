# ARKALI GENESIS v2 — CANONICAL ARCHITECTURE (PHASE 0A)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1
**Derived from canonical set at:** `079c925996034017855fb9d1f1fa532077d7e86d`

This document is architecture only. It creates no application source code and unlocks no phase.

---

## 1. Final greenfield repository architecture

```
ARKALI/
  docs/                          canonical set + generated canonical artifacts
    canonical/                   architecture, register, authority map
    adr/                         architecture decision records
    contracts/                   public contract definitions (from Phase 2)
    build/                       build state, phase history, blockers
    acceptance/                  evidence index, acceptance reports
    security/                    security findings, threat notes
  backend/                       Python 3.13 / FastAPI            (from Phase 2)
    arkali/
      kernel/                    L0: persistence, observability, contracts
      control/                   L1: specification, architecture, policy,
                                     isolation, registries, capability
      evidence/                  L2: artifact fabric, provenance, audit
      acceptance/                L2: acceptance engine, evidence graph, gate checker
      execution/                 L3: durable runtime, scheduler, workers, workflow
      engineering/               L4: agents, codeintel, candidate, repair, factory,
                                     knowledge, project_import, plugin, localai
      lifecycle/                 L5: release, recovery, evolution
      surfaces/                  L6: operations api, command center api
    alembic/                     migrations
    tests/
  frontend/                      React / TypeScript / Vite        (from Phase 5 slices)
  src-tauri/                     Tauri 2.x desktop shell          (from Phase 28)
  golden/                        golden product specs + repair defect corpus
  .gitignore  .gitattributes
```

Directory layers map 1:1 to the layer model in §4. A bounded context lives in exactly one layer directory. No module may exist outside its declared context.

---

## 2. Four-plane architecture map

| Plane | Contains | Implemented in |
|---|---|---|
| **Control** | Specification Authority, Architecture/Contract Authority, Capability Graph, Project/Revision Registry, Provider/Model Registry, Policy Authority, Workflow Definitions, Resource Scheduler, Knowledge Authority, Release Authority | `control/`, `execution/workflow` (definitions store), `lifecycle/release` |
| **Execution** | Durable Job Runtime, Workflow Executor, Agent Workers, Provider Workers, Build/Test Workers, Browser Workers, Sandbox Executors, Local AI Workers, Computer-Use Workers | `execution/`, `engineering/`, `surfaces/operations` |
| **Evidence** | Artifact Provenance, Acceptance Evidence Graph, traces/metrics/logs, audit chain, benchmark history, failure/repair history, security findings, test evidence | `evidence/`, `acceptance/` |
| **Product** | Working Copies, Candidate Products, Stable Products, Imported Projects, Generated Products, AI-Native Child Products, Product Evolution SDK, ARKALI Candidate Core | `engineering/candidate`, `engineering/project_import`, `lifecycle/` |

**Plane dependency rule.** Execution depends on Control. Control never depends on Execution. Every plane may write to Evidence. Only Acceptance reads Evidence for verdicts. Product depends on Control + Execution + Evidence and is depended upon by nothing.

---

## 3. Bounded-context map

28 contexts. Each has exactly one owning module tree and one canonical authority.

| # | Context | Layer | Canonical responsibility |
|---|---|---|---|
| 1 | `kernel.persistence` | L0 | DB engine, session, migration runner |
| 2 | `kernel.observability` | L0 | correlation IDs, traces, metrics, logs |
| 3 | `kernel.contracts` | L0 | shared schema primitives, error taxonomy |
| 4 | `control.specification` | L1 | canonical requirements, ARK-REQ runtime view |
| 5 | `control.architecture` | L1 | authority map, budgets, ADR state |
| 6 | `control.policy` | L1 | Policy Authority, PDP, PEP, Permission Broker, Secret Vault |
| 7 | `control.isolation` | L1 | Isolation Backend registry, property resolution |
| 8 | `control.registry.provider` | L1 | Provider/Model Registry |
| 9 | `control.registry.project` | L1 | Project/Revision Registry |
| 10 | `control.capability` | L1 | Capability Graph |
| 11 | `evidence.artifact` | L2 | Artifact Fabric, content addressing, provenance |
| 12 | `evidence.audit` | L2 | audit chain, security findings, integrity |
| 13 | `acceptance.engine` | L2 | Acceptance Engine, Evidence Graph, Phase Gate Checker |
| 14 | `execution.durable` | L3 | Durable Job Runtime |
| 15 | `execution.workflow` | L3 | canonical workflow graph store + Workflow Executor |
| 16 | `execution.scheduler` | L3 | Resource Scheduler, worker contracts |
| 17 | `execution.sandbox` | L3 | Sandbox Executors (consumes `control.isolation`) |
| 18 | `engineering.agent` | L4 | Agent Runtime, Harness, Context Compiler |
| 19 | `engineering.codeintel` | L4 | Code Intelligence, Digital Twin |
| 20 | `engineering.candidate` | L4 | Candidate Workspace, Semantic Assembly |
| 21 | `engineering.repair` | L4 | Root-Cause and Convergence Engine, Golden Repair |
| 22 | `engineering.factory` | L4 | AI Software Factory |
| 23 | `engineering.knowledge` | L4 | Knowledge Authority, Verified Components |
| 24 | `engineering.import` | L4 | Import / Reverse Engineering / Rescue |
| 25 | `engineering.plugin` | L4 | Plugins, connectors, research |
| 26 | `engineering.localai` | L4 | Local AI adapters, Model Laboratory |
| 27 | `lifecycle.release` | L5 | Release Authority, stable-promotion machinery |
| 28 | `lifecycle.recovery` | L5 | Recovery Supervisor, backup/restore |
| 29 | `lifecycle.evolution` | L5 | Self-Evolution campaigns, Product Evolution SDK |
| 30 | `surfaces.operations` | L6 | Operations Center, hardware telemetry, Computer-Use Workers |
| 31 | `surfaces.command` | L6 | Command Center API + frontend, desktop shell |

---

## 4. Dependency direction rules

Layers, low to high: **L0 kernel → L1 control → L2 evidence/acceptance → L3 execution → L4 engineering → L5 lifecycle → L6 surfaces.**

1. A context may depend only on contexts in a **strictly lower** layer.
2. Same-layer dependencies are forbidden unless declared explicitly in `AUTHORITY_MAP.yaml` under `allowed_sibling_edges`.
3. Upward dependencies are forbidden without exception. Inversion uses events or interfaces declared in `kernel.contracts`.
4. No cycles at any granularity — context, module or package.
5. Every context may **write** to `evidence.*`. Only `acceptance.engine` may read evidence for a verdict.
6. `control.policy` is callable from every layer (PEP call sites) but depends on nothing above L1.
7. Golden-product domain logic never enters any ARKALI context.

Automated enforcement: `forbidden dependency direction = 0`, `forbidden cycles = 0` (VDC §Architecture verification), evaluated against `AUTHORITY_MAP.yaml`.

---

## 5. Canonical authority ownership map

Resolves the specification requirement that no concern has two authorities. Full machine-readable form in `AUTHORITY_MAP.yaml`.

| Concern | Sole canonical authority |
|---|---|
| Requirement identity and classification | `control.specification` |
| Architecture rules, budgets, ADR state | `control.architecture` |
| Protected Core membership | `control.architecture` (declaration) enforced by `control.policy` |
| Policy decision (AUTO/ASK_USER/DENY) | `control.policy` |
| Secret storage and brokering | `control.policy` (Secret Vault) |
| Isolation backend availability and property resolution | `control.isolation` |
| Provider identity, model identity, config, health, availability, cost, fallback | `control.registry.provider` |
| Project and revision identity | `control.registry.project` |
| Capability availability answer | `control.capability` (references only, never copies) |
| Artifact identity and provenance | `evidence.artifact` |
| Audit chain and evidence integrity | `evidence.audit` |
| Acceptance verdict | `acceptance.engine` |
| Phase gating before Phase 13 | `acceptance.engine` (Phase Gate Checker) |
| Durable job state | `execution.durable` |
| Canonical workflow graph | `execution.workflow` |
| Resource allocation | `execution.scheduler` |
| Candidate workspace content | `engineering.candidate` |
| Repair budget and convergence | `engineering.repair` |
| Knowledge validity state | `engineering.knowledge` |
| Stable promotion | `lifecycle.release` |
| Stable rollback | `lifecycle.recovery` |
| Evolution campaign state | `lifecycle.evolution` |
| Telemetry truth | `surfaces.operations` (reads only from owning authorities) |

**Deliberate separations.** Promotion (`lifecycle.release`) and rollback (`lifecycle.recovery`) are distinct authorities so a failed promotion cannot self-approve its own recovery. Capability answers (`control.capability`) reference but never copy provider state (`control.registry.provider`), per MS §Provider and Agent separation.

---

## 6. Lifecycle authority map

| Lifecycle | Authority | Human gate |
|---|---|---|
| Project | `control.registry.project` | — |
| Candidate Product → Stable Product | `lifecycle.release` | GATE 3 when approval-gated |
| Candidate Core → Stable Core | `lifecycle.release` | **GATE 2 always** |
| Stable → prior Stable (rollback) | `lifecycle.recovery` only | none (deterministic, evidence-producing) |
| Job | `execution.durable` | — |
| Workflow Execution | `execution.workflow` | GATE per HUMAN APPROVAL node |
| Provider Health | `control.registry.provider` | — |
| Plugin Lifecycle | `engineering.plugin` | GATE 4 if it changes a security boundary |
| Release | `lifecycle.release` | GATE 7 for production release |
| Core Upgrade | `lifecycle.evolution` → `lifecycle.release` | GATE 2 |
| Backup/Restore | `lifecycle.recovery` | GATE 6 for migration APPLY |
| Evolution Campaign | `lifecycle.evolution` | GATE 2 at promotion |
| Hardening Round | `acceptance.engine` | GATE 8 on budget exception |
| Import Project | `engineering.import` | GATE per TRUST-3/4 approval |

---

## 7. Candidate / Stable / Rollback architecture

```
StableRevision (immutable, content-hashed)
      |  snapshot
      v
TaskSnapshot -> EphemeralWorkspace -> AgentChanges -> LocalTests
      |
      v
ArtifactCandidate -> SemanticAssembly -> CandidateRevision (immutable)
      |
      v
Verification -> Acceptance (acceptance.engine) -> Promotion (lifecycle.release)
      |                                                    |
      |                                                    v
      |                                            new StableRevision
      |
      +--- rejected -> terminal, no automatic successor

Recovery path (the ONLY direct stable mutation):
  lifecycle.recovery -> ROLLBACK_STABLE -> atomic pointer switch to a
  previously verified immutable StableRevision -> rollback evidence artifact
```

**Invariants (enforced, not conventional):**
- `WRITE_STABLE_FILE` resolves DENY for every actor including deterministic transformers and human-operated tools.
- `ROLLBACK_STABLE` is callable only by `lifecycle.recovery`, targets only a previously verified immutable revision, performs no content transformation, and emits evidence.
- Stable revisions are immutable; promotion creates a new revision and switches a pointer atomically.
- A rejected candidate never auto-generates a successor.

---

## 8. Architecture budgets (numeric)

Canonical values live in `AUTHORITY_MAP.yaml`. Any exception is HUMAN GATE 8 plus an ADR.

| Budget | Value |
|---|---|
| Max module logical lines (excl. tests/generated) | 400 |
| Max public symbols per module | 20 |
| Max fan-in per module | 15 |
| Max fan-out per module | 12 |
| Max public surface per bounded context | 40 |
| Max orchestration depth (call chain across contexts) | 4 |
| Max cyclomatic complexity per function | 12 |
| Max parameters per public function | 6 |
| Max contexts touched by one module | 3 |

Chosen deliberately generous: the purpose is to catch a central orchestrator, not to police ordinary modules.

---

## 9. Observability architecture

Every durable job, workflow execution, provider call, agent task, sandbox execution, build, test and repair emits: correlation ID, causation ID, context name, state, duration, error class, evidence links. OpenTelemetry-compatible export. `kernel.observability` owns emission; `surfaces.operations` owns display and may not compute state independently of the owning authority.

---

## 10. Persistence architecture

SQLite + WAL local-first behind SQLAlchemy 2.x repositories with PostgreSQL-ready abstractions. No raw SQL outside `kernel.persistence`. Alembic migrations are forward-only with a recorded rollback point. Runtime database files are never committed (`.gitignore`); migrations always are.

Minimal backup/restore ships **with** persistence in Phase 5, not at Phase 20, so no state accumulates without a proven restore path.

---

## 11. Code Intelligence / Digital Twin architecture

`engineering.codeintel` maintains symbol, import, dependency, route, model and frontend-contract graphs for Python (native AST) and other languages (Tree-sitter adapters). The Digital Twin composes: specification view, architecture view, code graph, data graph, runtime graph, deployment graph, test view, version view, failure view. It is a **derived** store — never an authority — and is rebuildable from source plus the owning authorities.

---

## 12. Initial ADR set

| ADR | Decision |
|---|---|
| ADR-0001 | Canonical authority map and machine-readable enforcement |
| ADR-0002 | Isolation Backend abstraction (properties, not technologies) |
| ADR-0003 | Capability Graph split: schema at Phase 3, activation at Phase 9B |
| ADR-0004 | Canonical workflow graph as sole authority; hash-bound derived caches |
| ADR-0005 | Protected Core membership and modification path |
| ADR-0006 | SQLite+WAL local-first with PostgreSQL-ready abstractions |
| ADR-0007 | Durable runtime without a mandatory Temporal dependency |
| ADR-0008 | Numeric architecture budgets and GATE 8 exception path |
| ADR-0009 | Promotion and rollback as separate lifecycle authorities |
