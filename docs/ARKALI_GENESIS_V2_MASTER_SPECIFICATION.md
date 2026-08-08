# ARKALI GENESIS v2 — MASTER SPECIFICATION

**Status:** FROZEN / AUTHORITATIVE

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

## Frozen technology direction
Backend: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic.
Frontend: React, TypeScript, Vite, Tailwind CSS.
Desktop: Tauri 2.x.
Persistence: SQLite+WAL local-first, PostgreSQL-ready abstractions.
Testing: pytest, contract/integration/architecture/property/mutation/chaos tests, Playwright E2E.
Observability: OpenTelemetry-compatible.
Source control/provenance: Git-linked revisions, content hashes, SBOM/signing-ready release design.
Local AI: adapter-based; no hard dependency on one runtime.

## Engineering constitution
1. One canonical authority per concern.
2. Duplicate/shadow active definitions are CI failures.
3. No giant factory/orchestration module.
4. No patch-stack architecture as the normal development method.
5. Deterministic Core / Probabilistic Edge.
6. No direct AI write to stable.
7. No fake success, fake metrics, fake providers, dead UI, TODO-as-implementation.
8. No long AI work in HTTP requests.
9. Evidence is authoritative; AI opinion is not.
10. Repair loops are formally budgeted and bounded.

## Formal state machines
Critical entities use explicit validated state machines: Project, Candidate, Job, Workflow Execution, Provider Health, Plugin Lifecycle, Release, Core Upgrade, Backup/Restore. Invalid transitions such as DRAFT→STABLE must be structurally impossible.

## Capability Graph
Every significant capability is represented as a versioned node with prerequisites, permissions, runtime requirements, health, cost profile, evidence requirements, dependencies, fallbacks, platform support and configured state. ARKALI must answer “Can I perform this?” deterministically from the graph.

## Provider and Agent separation
Agents are engineering roles. Providers are execution backends. A Backend Engineer role may use Claude, GPT, Gemini or a local model. Agents operate under bounded task/context/permissions and cannot mutate canonical requirements or declare their own output accepted.

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
Persistent state, checkpoints, heartbeat, progress evidence, idempotency, retries, bounded retries, timeout, cancel, pause/resume where supported, approvals/signals, crash recovery, dead-letter/error states. Target Temporal-grade durability without requiring Temporal as a mandatory local dependency.

## Visual Workflow Studio
Real executable n8n-like workflow system. Nodes include triggers, AI, agents, engineering, logic, data, integrations, approvals, release and notifications. Supports IF/ELSE/SWITCH/LOOP/PARALLEL/MERGE/WAIT/RETRY/ERROR HANDLER/HUMAN APPROVAL. UI graph and backend execution must be the same workflow.

## Code Intelligence and Digital Twin
AST/symbol/import/dependency/route/model analysis for Python, with adapters such as Tree-sitter for other languages. Maintain symbol/dependency/API/DB/frontend-contract graphs and a digital engineering twin containing specification, architecture, code/data/runtime/deployment graphs, tests, versions and failures.

## Independent Acceptance
Evidence → Acceptance Engine → Canonical Quality Authority → Release Authority. Evidence Graph links Requirement→Contract→Artifact→Test→Evidence→Result.

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
L3 Clean Environment: actual release artifact installed in clean Windows.
Simulation alone cannot produce production PASS.

## Test Intelligence
Applicable tests may include static, compile, unit, contract, integration, API, DB, behavioral, browser/E2E, accessibility, security, persistence, migration, backup/restore, performance, upgrade and regression. Do not impose irrelevant universal gates.

## Mutation / Property / Fuzz / Chaos
Tests themselves must be tested. Controlled mutations should be caught. Critical invariants receive property testing. Parsers/security boundaries may be fuzzed. Chaos/failure injection includes worker kill, backend restart, provider timeout, invalid AI output, corrupt artifact, DB lock, network loss, plugin/browser crash, disk pressure, migration failure, upgrade failure and resource exhaustion.

## Root-Cause and Convergence Engine
Reproduce→Observe→Evidence→Hypotheses→Experiment→Root Cause→Minimal Repair→Targeted Acceptance→Regression.
Repair fingerprints record failure signature, root-cause class, files, strategy, provider/model and outcome. Repeated failed strategy escalates instead of looping. Budgets cap attempts, AI calls, time, cost, touched files and regression delta.

## Security / Governance
Central Identity, RBAC, Secret Vault, Permission Broker, Policy Decision Point, Policy Enforcement Points, Audit, Privacy, Sandbox Policy and Protected Core. Decisions: AUTO / ASK_USER / DENY. Secrets never enter source, logs, prompts, exports or release artifacts.

## Trust-Tiered Isolation
TRUST-0 deterministic internal code
TRUST-1 ARKALI-maintained extensions
TRUST-2 generated candidate code
TRUST-3 imported/untrusted projects
TRUST-4 internet-sourced executable content
Higher-risk code receives stronger sandbox restrictions.

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

## ARKALI Self-Evolution
Stable Core→Snapshot→Isolated Candidate→Improvement→Architecture Tests→Regression→Security→Compatibility→User Approval→Promotion. Live stable core is never directly rewritten by AI.

## Pre-Delivery Four-Round Hardening
After first full acceptance PASS:
Round 1 Architecture & Maintainability
Round 2 Reliability & Security
Round 3 Performance/Cost/Resource/UX
Round 4 Adversarial Future-Proofing & Generalization
Each round uses baseline→review→candidate→benchmark→regression→keep/reject. No change is kept merely because AI suggested it.

## Proof-of-Engineering Passport
Every critical capability tracks required evidence: specification, architecture, implementation, security, unit, contract, integration, real product, browser/E2E, persistence, mutation, chaos, restart, adversarial review, provenance, regression. Completion percentage means verified-capability coverage, not files written.

## Database / Backup / Recovery
Data is more valuable than generated code. Schema change requires impact→backup→dry run→integrity→candidate migration→tests→apply→verify→rollback point. Backup must be proven by restore. Independent deterministic Recovery Supervisor rolls back failed ARKALI upgrades to known-good stable.

## Import / Rescue / Research / Plugins
External projects are statically inspected before execution. Rescue modes: Repair in Place, Controlled Modernization, Clean Rebuild with Migration. Research uses official sources first and never directly mutates production. Plugins/connectors/domain packs are manifest/permission/version governed and must not crash core. MCP-compatible adapters may exist without making ARKALI internally dependent on MCP.

## Operations / Computer Use / Source Export
Real-time jobs, workflows, agents, providers, models, CPU/RAM/GPU/VRAM/disk/network/workers/queues/DB/storage/cost/ETA/stuck detection. Permission-aware terminal/browser/files/process/installer interaction with human takeover. Full Source Intelligence Export and AI Review Bundle include architecture/tree/contracts/issues/evidence/source with secrets redacted.

## Professional Command Center
Beginner / Professional / Expert modes. Major areas: Command Center, AI Software Factory, Managed Products, Workflow Studio, AI Team, Providers & Models, Operations, Knowledge, Code Intelligence, Evolution, Extensions, Security, Release/Deployment, Diagnostics. Every production-visible state comes from real backend state.

## Desktop / Offline
Windows-first Tauri desktop with ARKALI_Setup.exe, first-run diagnostics and bundled runtime. Local capabilities continue offline where possible. Air-gapped mode may use signed offline update bundles.

## Canonical Implementation Phases
0 Architecture Freeze
1 Repository Bootstrap
2 Foundation + Contracts
3 Formal State Machines + Capability Graph
4 Security + Governance
5 Persistence + Project Registry
6 Evidence Plane + Provenance + Artifact Store
7 Durable Job + Workflow Core
8 Resource Scheduler + Worker Contracts
9 Provider + Model Runtime
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
20 Database / Backup / Recovery
21 Plugins + Integrations + Research
22 Local AI + Model Laboratory
23 Self-Evolution
24 Generated Product Evolution SDK
25 Operations + Hardware Intelligence
26 Release / Supply Chain / Deployment
27 React Command Center
28 Tauri Desktop
29 Installer + Recovery Supervisor
30 Golden Product Verification
31 Chaos / Mutation / Generalization Verification
32 Hardening Round 1
33 Hardening Round 2
34 Hardening Round 3
35 Hardening Round 4
36 Clean Environment Full Acceptance
37 Production Release

## Final Success Rule
ARKALI FUNCTION IMPLEMENTED ≠ VERIFIED.
For program-generation capabilities, VERIFIED requires all applicable:
Unit/Contract Tests + Real Generated Product + Real Build + Real Runtime + Real User Journey + Real Persistence + Real Acceptance + Provenance Evidence.
