# ARKALI GENESIS v2 — MASTER SPECIFICATION

**Status:** FROZEN / AUTHORITATIVE
**Revision:** canonical architecture repair applied before Phase 0

ARKALI GENESIS v2 is a local-first professional **Engineering Control Fabric**. It converts natural-language goals into canonical requirements, orchestrates specialized engineering agents over multiple AI providers, executes work in isolated durable environments, creates provenance-tracked artifacts, assembles candidate products, independently verifies them with executable evidence, performs bounded root-cause repair, manages full lifecycle/recovery, learns only from verified outcomes, supports local/cloud AI, can optionally generate AI-native self-evolving child products, and can evolve itself only through isolated candidate-core lifecycles.

## Core architectural planes

### Control Plane
Specification Authority, Architecture/Contract Authority, Capability Graph, Project/Revision Registry, Provider/Model Registry, Policy Authority, Workflow Definitions, Resource Scheduler, Knowledge Authority, Release Authority.

### Execution Plane
Durable Job Runtime, Workflow Executor, Agent Workers, Provider Workers, Build/Test Workers, Browser Workers, Sandbox Executors, Local AI Workers, Computer-Use Workers.

### Evidence Plane
Artifact Provenance, Acceptance Evidence Graph, traces/metrics/logs, audit chain, benchmark history, failure/repair history, security findings, test evidence.

### Product Plane
Working Copies, Candidate Products, Stable Products, Imported Projects, Generated Products, AI-Native Child Products, Product Evolution SDK, ARKALI Candidate Core.

A **Stable Product revision** is a promoted product revision under Release Authority. A **Stable Core revision** is a promoted ARKALI core revision. "Stable" without a qualifier refers to both. These definitions take effect from the first revision designated Stable by the Release Authority; repository development before that designation is ordinary human-directed engineering.

## Frozen technology direction
Backend: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic.
Frontend: React, TypeScript, Vite, Tailwind CSS.
Desktop: Tauri 2.x.
Persistence: SQLite+WAL local-first, PostgreSQL-ready abstractions.
Testing: pytest, contract/integration/architecture/property/mutation/chaos tests, Playwright E2E.
Observability: OpenTelemetry-compatible.
Source control/provenance: Git-linked revisions, content hashes, SBOM/signing-ready release design.
Local AI: adapter-based; no hard dependency on one runtime.
Isolation: Isolation Backend abstraction; Windows-first backends include Win32 Job Objects, restricted/low-integrity tokens, per-workspace ACLs, Windows Firewall/WFP controls, Windows Sandbox and Hyper-V isolation.

## Engineering constitution
1. One canonical authority per concern.
2. Duplicate/shadow active definitions are CI failures.
3. No giant factory/orchestration module.
4. No patch-stack architecture as the normal development method.
5. Deterministic Core / Probabilistic Edge.
6. No actor or mechanism may directly mutate a Stable Core or Stable Product revision. This includes AI agents, deterministic transformers, workflows, plugins, computer-use workers and human-operated engineering tools. All changes use stable → candidate → verification → acceptance → promotion. The sole exception is deterministic Recovery Supervisor rollback, governed by the ROLLBACK_STABLE rules below.
7. No fake success, fake metrics, fake providers, dead UI, TODO-as-implementation.
8. No long AI work in HTTP requests.
9. Evidence is authoritative; AI opinion is not.
10. Repair loops are formally budgeted and bounded.

Rules 2 and 3 are enforced against the numeric architecture budgets recorded in the canonical authority map. An exception requires an approved ADR and HUMAN GATE 8. No exception may rest on a justification authored by an implementing actor.

## Canonical Requirement Register
Every normative requirement in the canonical set carries an immutable identifier `ARK-REQ-####` recorded in `docs/canonical/REQUIREMENT_REGISTER.md`, produced in Phase 0B.

Each entry records: ID; requirement statement; source document and section; classification MANDATORY | CONDITIONAL | OPTIONAL; owning phase; owning component; required acceptance evidence; and, for CONDITIONAL entries, the objective applicability rule.

IDs are immutable. They are never reused, renumbered or retired; superseded requirements are marked SUPERSEDED_BY and retained.

Any normative statement in the canonical set that is not classified in the register defaults to MANDATORY.

The register is the sole denominator for all requirement and evidence coverage measurement. Coverage computed against any other set is invalid.

### Applicability
MANDATORY entries are always applicable and can never be waived by any automated actor. CONDITIONAL entries carry an objective, machine-evaluable applicability rule; the rule is authored only in the register and only with human approval.

Implementing agents may evaluate applicability rules. They may not author, amend, broaden or reinterpret them, and may not classify any requirement themselves.

An exceptional applicability waiver requires written justification, HUMAN GATE 5 approval, a recorded waiver evidence artifact, and an expiry or review condition. Unwaived, unevaluable rules resolve to APPLICABLE.

## Formal state machines
Critical entities use explicit validated state machines: Project, Candidate, Job, Workflow Execution, Provider Health, Plugin Lifecycle, Release, Core Upgrade, Backup/Restore. Invalid transitions such as DRAFT→STABLE must be structurally impossible.

## Capability Graph
Every significant capability is represented as a versioned node with prerequisites, permissions, runtime requirements, health, cost profile, evidence requirements, dependencies, fallbacks, platform support and configured state. ARKALI must answer “Can I perform this?” deterministically from the graph.

Node attributes sourced from other authorities — permissions (Security/Governance), evidence requirements (Evidence Plane), and provider health, availability, cost and fallback (Provider/Model Registry) — are stored as references, never copies, and are resolved at query time.

The graph is delivered as schema at Phase 3 and activated at Phase 9B, after its referenced authorities exist. Before activation every capability query returns NOT_CONFIGURED. It never returns a stubbed, defaulted or assumed value. NOT_CONFIGURED is a determinate answer and satisfies the determinism requirement above.

## Provider and Agent separation
Agents are engineering roles. Providers are execution backends. A Backend Engineer role may use Claude, GPT, Gemini or a local model. Agents operate under bounded task/context/permissions and cannot mutate canonical requirements or declare their own output accepted.

The Provider/Model Registry is the sole canonical authority for provider identity, model identity, provider configuration, health, availability, cost metadata and provider fallback configuration. No other component may store, cache, mirror, default or re-derive these values. All consumers resolve them from the Registry at query time.

## Harness Engineering
Every engineering task is executed as:
Task Specification + Context Package + Tools + Permissions + Workspace + Environment + Acceptance Target + Repair Budget.
The primitive is not “send a prompt”; the primitive is “execute a bounded engineering task”.

## Context Compiler
ARKALI sends only relevant files, symbols, contracts, tests, ADRs, failures and verified knowledge to a model. Context provenance is recorded.

## Ephemeral Engineering Workspaces
Stable Repository → Task Snapshot → Ephemeral Workspace → Agent Changes → Local Tests → Artifact Candidate → Semantic Reconciliation. Agents cannot casually overwrite each other.

## Artifact Fabric
Artifacts are immutable/versioned and preferably content-addressed. Metadata includes content hash, producer agent, provider/model, task ID, specification version, context hash, parent artifacts, normalization, tests, evidence and timestamps.

## Semantic Candidate Assembly
Candidate assembly validates API↔frontend, API↔QA, DB↔models, models↔frontend, requirements↔implementation, entrypoint↔startup, routes↔browser and dependencies↔locks. Textual merge success is not enough.

## Durable Job / Workflow Runtime
Persistent state, checkpoints, heartbeat, progress evidence, idempotency, retries, bounded retries, timeout, cancel, pause/resume per its Canonical Requirement Register applicability rule, approvals/signals, crash recovery, dead-letter/error states. Target Temporal-grade durability without requiring Temporal as a mandatory local dependency.

## Visual Workflow Studio
Real executable n8n-like workflow system. Nodes include triggers, AI, agents, engineering, logic, data, integrations, approvals, release and notifications. Supports IF/ELSE/SWITCH/LOOP/PARALLEL/MERGE/WAIT/RETRY/ERROR HANDLER/HUMAN APPROVAL. UI graph and backend execution must be the same workflow.

The persisted versioned canonical workflow graph is the sole canonical authority. UI rendering and backend execution are two views of the same graph revision. Derived compiled or cached representations are permitted only when they are deterministically derived from the canonical graph revision, hash-bound to it, and invalidated by any change to it. A derived representation is never an independent authority and is never executed when its bound hash does not match the current canonical revision.

## Code Intelligence and Digital Twin
AST/symbol/import/dependency/route/model analysis for Python, with adapters such as Tree-sitter for other languages. Maintain symbol/dependency/API/DB/frontend-contract graphs and a digital engineering twin containing specification, architecture, code/data/runtime/deployment graphs, tests, versions and failures.

## Independent Acceptance
Evidence → Acceptance Engine → Release Authority, under the human acceptance authority. Evidence Graph links Requirement→Contract→Artifact→Test→Evidence→Result. Machine verdicts never supersede a mandatory HUMAN GATE.

Independence is structural: the acceptance contracts an actor is measured against are Protected Core and cannot be modified by that actor. Independence does not require human approval of routine machine verdicts.

## Real Program Generation Verification
Software-factory capabilities must be verified by generating real products through the actual production pipeline. Minimum Golden Product families:
1. Task/Work Management
2. Student/Fee Management
3. Property/Facility/Document Workflow
4. Inventory/Stock/Transactions
5. AI-Native Self-Evolving Product
Then an unseen-domain generalization test. Golden domain logic must not enter ARKALI core.

## Real Execution Levels
L1 Simulation: controlled failures.
L2 Real Execution: actual source/build/process/DB/browser/runtime.
L3 Clean Environment: actual release artifact installed on the canonical Windows clean-test baseline defined below.
Simulation alone cannot produce production PASS.

L3 executes against the canonical Windows clean-test baseline: a named Windows edition and build, restored from a snapshot immediately before each canonical run, with no developer tooling present. Absent before installation, at minimum: Python, Node.js, Rust/Cargo, Git, MSVC build tools, and any ARKALI runtime or data from a prior run. The baseline identity and snapshot revision are recorded in the L3 evidence artifact. This is an acceptance-test environment requirement and is not imposed on end users.

## Test Intelligence
Applicable tests may include static, compile, unit, contract, integration, API, DB, behavioral, browser/E2E, accessibility, security, persistence, migration, backup/restore, performance, upgrade and regression. Applicability is determined by the Canonical Requirement Register, not by implementing actors. Do not impose irrelevant universal gates.

## Mutation / Property / Fuzz / Chaos
Tests themselves must be tested. Controlled mutations should be caught. Critical invariants receive property testing. Fuzzing is mandatory for parsers, security boundaries and AI-output deserializers, and applies elsewhere per Canonical Requirement Register applicability rule. Chaos/failure injection includes worker kill, backend restart, provider timeout, invalid AI output, corrupt artifact, DB lock, network loss, plugin/browser crash, disk pressure, migration failure, upgrade failure and resource exhaustion.

## Root-Cause and Convergence Engine
Reproduce→Observe→Evidence→Hypotheses→Experiment→Root Cause→Minimal Repair→Targeted Acceptance→Regression.
Repair fingerprints record failure signature, root-cause class, files, strategy, provider/model and outcome. Repeated failed strategy escalates instead of looping. Budgets cap attempts, AI calls, time, cost, touched files and regression delta.

## Golden Repair Benchmark
Golden Repair is the deterministic acceptance benchmark for the Root-Cause and Convergence Engine. It is executed against a Golden Product revision that has already passed acceptance.

Defect corpus: a versioned, content-hashed set of injected defects covering at minimum contract violation, state-machine invalid transition, permission-check removal, persistence-not-committed, API/frontend contract drift, dependency/lock mismatch, migration/model mismatch, and boundary/off-by-one. The corpus includes at least one defect deliberately unrepairable within budget.

Each run declares budgets before execution using the six repair-budget dimensions above.

PASS requires all of:
- every repairable corpus defect resolved within its declared budget;
- zero regressions in the pre-existing accepted test suite;
- no acceptance test weakened, deleted or rewritten during repair;
- every repair evidence-backed with a root-cause record and repair fingerprint;
- the unrepairable defect escalated to a terminal ESCALATED state within budget rather than retried indefinitely;
- the corpus content hash recorded in the evidence artifact.

Repair success without bounded-escalation evidence is FAIL. The corpus is never modified to obtain PASS.

## Security / Governance
Central Identity, RBAC, Secret Vault, Permission Broker, Policy Decision Point, Policy Enforcement Points, Audit, Privacy, Sandbox Policy and Protected Core. Decisions: AUTO / ASK_USER / DENY. Secrets never enter source, logs, prompts, exports or release artifacts.

### Secret Vault boundary
Secrets enter the vault only through an explicit human-initiated provisioning path. No agent, workflow, plugin, generated product or computer-use worker may write a secret into the vault, read a raw secret value, or export one. Consumers receive scoped, brokered, revocable references through the Permission Broker; raw values never cross a trust boundary and never appear in a context package. Vault storage is protected by an OS-provided key-protection facility (Windows DPAPI or equivalent); where none is available, secret-dependent capabilities are UNSUPPORTED rather than stored unprotected.

### Local-Only mode
Local-Only is a canonical policy mode. When enabled, the Policy Decision Point returns DENY for all outbound network egress from every trust tier, including cloud provider calls, research, plugin/connector network access and external browser navigation. Loopback remains permitted so local build, test and browser verification continue. Local AI, local execution and all local capabilities remain available. Enabling or disabling Local-Only is a security-boundary change and is HUMAN GATE 4. No actor may bypass it, and no capability may silently degrade to a cloud path while it is enabled.

### Protected Core
Protected Core is the explicit, machine-readable set of paths and components whose compromise could invalidate ARKALI's own safety or evidence. Membership is declared in `docs/canonical/AUTHORITY_MAP.yaml` in Phase 0B and includes at minimum: Policy Authority / PDP / PEP; Acceptance Engine; evidence integrity mechanisms; Release Authority; Recovery Supervisor; Secret Vault; sandbox/isolation enforcement and the Isolation Backend registry; canonical authority definitions; stable-promotion machinery.

Protected Core is modified only through the Stable Core candidate lifecycle, under a stronger verification profile requiring security review, adversarial review and full regression, and requires HUMAN GATE 2. No implementing actor may add to, remove from or reinterpret Protected Core membership.

## Trust-Tiered Isolation
Trust tiers declare REQUIRED SECURITY PROPERTIES. Isolation Backends provide them. Tiers never name a specific technology.

Security properties:
- `FS_CONFINEMENT` — execution cannot read or write outside its assigned workspace
- `NET_EGRESS_CONTROL` — outbound network is policy-controlled, default loopback-only
- `PROCESS_CONTAINMENT` — child processes cannot outlive or escape the boundary
- `CREDENTIAL_ISOLATION` — the Secret Vault is unreachable from the boundary
- `RESOURCE_LIMITS` — CPU, memory, process count and disk are capped
- `KERNEL_ISOLATION` — a host kernel compromise is not reachable from the boundary
- `DISPOSABILITY` — the environment is destroyed and recreated per execution

Required properties and approval per tier:

| Tier | Content | Required properties | Human approval |
|---|---|---|---|
| TRUST-0 | deterministic internal code | none (in-process) | no |
| TRUST-1 | ARKALI-maintained extensions | FS_CONFINEMENT, PROCESS_CONTAINMENT, RESOURCE_LIMITS | no |
| TRUST-2 | generated candidate code | TRUST-1 set + NET_EGRESS_CONTROL + CREDENTIAL_ISOLATION | no; external egress is ASK_USER |
| TRUST-3 | imported/untrusted projects | TRUST-2 set + KERNEL_ISOLATION; static inspection before any execution | yes, before first execution |
| TRUST-4 | internet-sourced executable content | TRUST-3 set + DISPOSABILITY | yes, per execution |

## Isolation Backends
An Isolation Backend declares which security properties it provides. Windows-first backends may include Win32 Job Objects, restricted/low-integrity tokens, per-workspace ACLs, Windows Firewall/WFP controls, Windows Sandbox, Hyper-V isolation, and future compatible backends. Backends may compose.

An execution capability runs only if an available backend, or composition of backends, satisfies ALL properties required by its trust tier. If none does, that capability is UNSUPPORTED, and any attempted execution is DENY.

ARKALI remains fully operational for every capability whose isolation requirements can still be satisfied. A trust tier is never silently downgraded, and a missing property is never substituted, defaulted or waived by an implementing actor. Backend availability is probed at Phase 4 and recorded in the Capability Graph.

## Supply-Chain Security
Deterministic dependency manifests/locks, provenance, SBOM, hashes, attestations/signing-ready release workflow, suspicious-package review.

## Knowledge / Verified Components / Local AI
Only evidence-backed successful outcomes can become authoritative knowledge. Knowledge states: fresh, aging, revalidation_required, deprecated, invalid. Reusable components require isolated tests/security/compatibility metadata. Local AI is hardware-aware and adapter-based. Fine-tuning/distillation can use only verified datasets.

## AI-Native Child Products
Modes:
1. Standard
2. AI-Assisted
3. AI-Native Self-Evolving
Level 3 uses a lightweight independent Product Evolution SDK:
Admin Request→Impact→Working Copy→Candidate→Tests→Approval→Promotion/Rollback.

Product Evolution SDK improvement cycles use the same bounded campaign model, budgets and terminal states as ARKALI Self-Evolution.

## ARKALI Self-Evolution
Stable Core→Snapshot→Isolated Candidate→Improvement→Architecture Tests→Regression→Security→Compatibility→User Approval→Promotion. Live stable core is never directly rewritten by AI.

Self-Evolution is DENY until the Recovery Supervisor has passed its canonical rollback verification (Phase 22B). The precondition is enforced by the Policy Decision Point, not by convention, and cannot be satisfied by a Recovery Supervisor that exists but is unverified. Every core candidate promotion requires a restorable known-good stable core snapshot recorded before promotion, and requires HUMAN GATE 2.

Self-evolution occurs only within an evolution campaign. Every campaign declares before execution: an explicit objective, baseline metrics, candidate budget, AI-call budget, time budget, cost budget where measurable by the provider, a regression ceiling, and a no-progress threshold.

A campaign terminates in exactly one state: PROMOTED (following HUMAN GATE 2), COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN, ESCALATED, or BLOCKED.

A rejected candidate does not automatically generate a successor candidate. Successors are produced only while campaign budget remains and the no-progress threshold has not been reached. Campaigns are never restarted to obtain a different terminal state.

## Pre-Delivery Four-Round Hardening
After first full acceptance PASS:
Round 1 Architecture & Maintainability
Round 2 Reliability & Security
Round 3 Performance/Cost/Resource/UX
Round 4 Adversarial Future-Proofing & Generalization
Each round uses baseline→review→candidate→benchmark→regression→keep/reject. No change is kept merely because AI suggested it.

Each round declares before execution: maximum candidate attempts, maximum AI calls, maximum elapsed time, maximum provider cost where measurable by the provider, maximum touched-file scope, and a no-progress threshold expressed as N consecutive candidates producing no measured improvement.

Each round terminates in exactly one state: PASS, COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN, ESCALATED, or BLOCKED.

No round may run indefinitely. Budget exhaustion terminates the round as COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN when the baseline is intact, otherwise ESCALATED. Rounds are never restarted to obtain a different terminal state.

## Proof-of-Engineering Passport
Every critical capability tracks required evidence: specification, architecture, implementation, security, unit, contract, integration, real product, browser/E2E, persistence, mutation, chaos, restart, adversarial review, provenance, regression. Required evidence per capability is recorded against its Canonical Requirement Register entries. Completion percentage means verified-capability coverage measured against the register, not files written.

## Database / Backup / Recovery
Data is more valuable than generated code. Schema change requires impact→backup→dry run→integrity→candidate migration→tests→apply→verify→rollback point. APPLY of a migration to real or stable data is HUMAN GATE 6. Backup must be proven by restore. Independent deterministic Recovery Supervisor rolls back failed ARKALI upgrades to known-good stable.

### ROLLBACK_STABLE
Recovery Supervisor rollback is the sole permitted direct mutation of a Stable revision. It is not general stable-write permission. Only the deterministic Recovery Supervisor may invoke it.

It may restore only a previously verified, immutable stable revision or snapshot, and prefers atomic revision/pointer switching over file-level rewriting. It permits no novel content, no arbitrary Stable editing, no transformation of content during restore, no unverified target, no evidence bypass and no direct AI invocation. Every rollback emits an auditable rollback evidence artifact.

## Import / Rescue / Research / Plugins
External projects are statically inspected before execution. Rescue modes: Repair in Place, Controlled Modernization, Clean Rebuild with Migration. Research uses official sources first and never directly mutates production. Plugins/connectors/domain packs are manifest/permission/version governed and must not crash core. MCP-compatible adapters may exist without making ARKALI internally dependent on MCP.

Plugin manifests declare permissions using the canonical Computer-Use operation classes below. There is no separate plugin permission vocabulary. A plugin action that cannot be mapped to a declared operation class is DENY.

## Operations / Computer Use / Source Export
Real-time jobs, workflows, agents, providers, models, CPU/RAM/GPU/VRAM/disk/network/workers/queues/DB/storage/cost/ETA/stuck detection. Permission-aware terminal/browser/files/process/installer interaction with human takeover. Full Source Intelligence Export and AI Review Bundle include architecture/tree/contracts/issues/evidence/source with secrets redacted.

Computer-Use Workers execute exclusively through the Policy Authority / PDP / PEP path used by every other execution surface. Every action resolves to a declared operation class, and every class resolves to AUTO, ASK_USER or DENY according to trust tier, target boundary and policy.

Operation classes: `READ_FILE`, `WRITE_WORKSPACE_FILE`, `WRITE_STABLE_FILE`, `ROLLBACK_STABLE`, `RUN_PROCESS`, `TERMINATE_PROCESS`, `BROWSER_LOCAL`, `BROWSER_EXTERNAL`, `NETWORK_EXTERNAL`, `INSTALL_DEPENDENCY`, `INSTALL_SYSTEM_SOFTWARE`, `CHANGE_SYSTEM_CONFIGURATION`, `ACCESS_SECRET`, `APPLY_MIGRATION`.

Fixed resolutions, never overridable:
- `WRITE_STABLE_FILE` — DENY for every actor; stable changes use the candidate lifecycle.
- `ROLLBACK_STABLE` — permitted only to the deterministic Recovery Supervisor under the ROLLBACK_STABLE rules above.
- `INSTALL_SYSTEM_SOFTWARE` — never AUTO.
- `CHANGE_SYSTEM_CONFIGURATION` — never AUTO.
- `APPLY_MIGRATION` to real or stable data — HUMAN GATE 6.
- `ACCESS_SECRET` outside pre-authorized scoped use — never AUTO.

An action that cannot be mapped to a declared operation class is DENY.

## Professional Command Center
Beginner / Professional / Expert modes. Major areas: Command Center, AI Software Factory, Managed Products, Workflow Studio, AI Team, Providers & Models, Operations, Knowledge, Code Intelligence, Evolution, Extensions, Security, Release/Deployment, Diagnostics. Every production-visible state comes from real backend state.

Capability phases deliver their own frontend increment wherever the capability has a production-visible state. Phase 27 consolidates navigation, cross-area coherence and the Beginner/Professional/Expert modes; it is not the first integration of backend capabilities with the UI.

## Desktop / Offline
Windows-first Tauri desktop with ARKALI_Setup.exe, first-run diagnostics and bundled runtime. Local capabilities continue offline per their Canonical Requirement Register applicability rule. Air-gapped mode may use signed offline update bundles.

## Canonical Implementation Phases
0A Canonical Architecture
0B Governance & Executable Contracts
1 Repository Bootstrap
2 Foundation + Contracts + Phase Gate Checker
3 Formal State Machines + Capability Graph Schema
4 Security + Governance + Isolation Backends
5 Persistence + Project Registry + Minimal Backup/Restore
6 Evidence Plane + Provenance + Artifact Store
7 Durable Job + Workflow Core
8 Resource Scheduler + Worker Contracts
9 Provider + Model Runtime
9B Capability Graph Activation
10 Agent Runtime + Harness Engineering
11 Code Intelligence + Digital Twin
12 Candidate Workspace + Semantic Assembly
13 Acceptance Infrastructure + Evidence Graph
14 Repair / Root Cause / Convergence
15 Requirement + Architecture Intelligence
16 AI Software Factory
17 Visual Workflow Studio
18 Knowledge + Verified Components
19 Import / Reverse Engineering / Rescue
20 Database Migration Safety + Full Backup/Recovery
21 Plugins + Integrations + Research
22 Local AI + Model Laboratory
22B Recovery Supervisor + Core Rollback Verification
23 Self-Evolution
24 Generated Product Evolution SDK
25 Operations + Hardware Intelligence
26 Release / Supply Chain / Deployment
27 Command Center Consolidation + Beginner/Professional/Expert Modes
28 Tauri Desktop
29 Installer + Recovery Supervisor Integration
30 Golden Product + Golden Repair Verification
31 Chaos / Mutation / Generalization Verification
32 Hardening Round 1
33 Hardening Round 2
34 Hardening Round 3
35 Hardening Round 4
36 Clean Environment Full Acceptance
37 Production Release

Phase 0A and Phase 0B form one Phase 0 acceptance package under a single HUMAN GATE 1.

## Final Success Rule
ARKALI FUNCTION IMPLEMENTED ≠ VERIFIED.
For program-generation capabilities, VERIFIED requires all applicable, as determined by the Canonical Requirement Register:
Unit/Contract Tests + Real Generated Product + Real Build + Real Runtime + Real User Journey + Real Persistence + Real Acceptance + Provenance Evidence.
