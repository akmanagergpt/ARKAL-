# ARKALI GENESIS v2 — CONTRACT INVENTORY (PHASE 0A)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1
**Scope:** architecture-level inventory of the canonical contract families Phase 2 will implement.
**This document implements no runtime contract.** No schema file, no code, no serialisation format is produced here.

## Governing rules

1. Every contract has exactly one **owning bounded context**. The owner is the sole authority for its shape.
2. A consumer never redefines a contract it consumes.
3. Versioning is semantic per contract family: MAJOR = breaking, MINOR = additive-compatible, PATCH = non-structural.
4. Compatibility class is declared per contract and enforced by contract tests from Phase 2.
5. Contracts owned by a Protected Core context are themselves Protected Core; changing them requires HUMAN GATE 2.
6. `docs/contracts/` holds the authoritative schema files from Phase 2. Paths below are **planned locations**, not existing files.

Category key: `INT` internal service interface · `HTTP` external HTTP API · `DB` persistence schema · `EVT` event/message · `ART` artifact format · `POL` policy decision · `EVD` evidence record · `GRAPH` graph document · `MANIFEST` third-party manifest.

Compatibility key: `STRICT` no breaking change without MAJOR + migration · `ADDITIVE` additive-only within MAJOR · `PINNED` version pinned per consumer, no implicit upgrade.

---

## Inventory

| # | Contract | Owner context | Producer | Consumer(s) | Cat | Planned schema location | Versioning | Compatibility | Acceptance / evidence responsibility | Impl. phase |
|---|---|---|---|---|---|---|---|---|---|---|
| C-01 | Error taxonomy | `kernel.contracts` | kernel | all contexts | INT | `docs/contracts/errors.md` + `kernel/contracts/errors.py` | semver | STRICT | `acceptance.engine` — contract tests | 2 |
| C-02 | Correlation/causation envelope | `kernel.observability` | all emitters | `surfaces.operations`, `evidence.audit` | EVT | `docs/contracts/telemetry_envelope.md` | semver | ADDITIVE | `kernel.observability` — integration | 2 |
| C-03 | Persistence base schema + migration contract | `kernel.persistence` | kernel | all persisting contexts | DB | `backend/alembic/` + `docs/contracts/persistence.md` | migration-numbered | STRICT | `lifecycle.recovery` — migration + restore evidence | 5 |
| C-04 | Requirement register record (`ARK-REQ`) | `control.specification` | Phase 0B / human | `acceptance.engine`, all phase reports | INT | `docs/contracts/requirement_record.md` | semver | STRICT | `acceptance.engine` — coverage computation | 2 |
| C-05 | Canonical authority map document | `control.architecture` | Phase 0B / human | architecture gates, `control.policy` | GRAPH | `docs/canonical/AUTHORITY_MAP.yaml` (exists) | schema_version | STRICT | `control.architecture` — 8 architecture gates | 2 |
| C-06 | Architecture budget record | `control.architecture` | Phase 0B / human | architecture gates | INT | within `AUTHORITY_MAP.yaml` | schema_version | STRICT | `control.architecture` — budget gate | 2 |
| C-07 | Policy decision request/response | `control.policy` | every PEP call site | PDP | POL | `docs/contracts/policy_decision.md` | semver | STRICT | `control.policy` — policy-bypass suite | 4 |
| C-08 | Computer-Use operation class | `control.policy` | `surfaces.operations`, `engineering.plugin` | PDP | POL | within policy contract | semver | STRICT | `control.policy` — 14-class matrix tests | 4 |
| C-09 | Secret reference (brokered handle) | `control.policy` | Permission Broker | scoped consumers | INT | `docs/contracts/secret_reference.md` | semver | STRICT | `control.policy` — vault boundary tests | 4 |
| C-10 | Isolation property / backend descriptor | `control.isolation` | backend adapters | `execution.sandbox`, `control.capability` | INT | `docs/contracts/isolation.md` | semver | STRICT | `control.isolation` — escape + negative-control tests | 4 |
| C-11 | Provider/model record | `control.registry.provider` | registry | capability, scheduler, agent, operations | INT | `docs/contracts/provider_record.md` | semver | STRICT | `control.registry.provider` — shadow-registry gate | 9 |
| C-12 | Project / revision record | `control.registry.project` | registry | factory, candidate, release | DB+INT | `docs/contracts/project_record.md` | semver | STRICT | `control.registry.project` — state-machine tests | 5 |
| C-13 | Capability node + query result | `control.capability` | capability graph | scheduler, agent, factory, operations | INT | `docs/contracts/capability_node.md` | semver | STRICT | `control.capability` — reference-not-copy arch test | 3 (schema) / 9B |
| C-14 | Artifact descriptor + provenance record | `evidence.artifact` | every artifact producer | acceptance, release, export | ART | `docs/contracts/artifact.md` | content-addressed + semver | STRICT | `evidence.artifact` — provenance evidence | 6 |
| C-15 | Audit record | `evidence.audit` | every auditable action | audit chain, security review | EVD | `docs/contracts/audit_record.md` | append-only, semver | STRICT | `evidence.audit` — integrity tests | 6 |
| C-16 | Evidence graph edge (`REQ→…→Result`) | `acceptance.engine` | all evidence producers | acceptance, coverage | GRAPH | `docs/contracts/evidence_graph.md` | semver | STRICT | `acceptance.engine` — traceability tests | 13 |
| C-17 | Phase report | `acceptance.engine` | implementing actor | Phase Gate Checker, human authority | INT | `docs/contracts/phase_report.md` | semver | STRICT | `acceptance.engine` — Checker C1/C2 | 2 |
| C-18 | Phase gate verdict | `acceptance.engine` | Phase Gate Checker | build state, human authority | EVD | `docs/contracts/gate_verdict.md` | semver | STRICT | `acceptance.engine` — determinism tests | 2 |
| C-19 | Durable job record + checkpoint | `execution.durable` | job runtime | scheduler, workflow, operations | DB+INT | `docs/contracts/job.md` | semver | STRICT | `execution.durable` — durable restart evidence | 7 |
| C-20 | Canonical workflow graph document | `execution.workflow` | Studio UI / API | executor, UI renderer | GRAPH | `docs/contracts/workflow_graph.md` | revision-hashed + semver | STRICT | `execution.workflow` — execution-identity evidence | 17 |
| C-21 | Worker contract (class, limits, tier) | `execution.scheduler` | worker implementations | scheduler | INT | `docs/contracts/worker.md` | semver | ADDITIVE | `execution.scheduler` — admission tests | 8 |
| C-22 | Harness task specification | `engineering.agent` | factory, repair | agent runtime, providers | INT | `docs/contracts/harness_task.md` | semver | STRICT | `engineering.agent` — bounded-task tests | 10 |
| C-23 | Context package + provenance | `engineering.agent` | Context Compiler | providers | INT | `docs/contracts/context_package.md` | semver | STRICT | `engineering.agent` — no-secret assertion | 10 |
| C-24 | Code graph / Digital Twin view | `engineering.codeintel` | code intelligence | assembly, repair, operations | GRAPH | `docs/contracts/code_graph.md` | semver | ADDITIVE | `engineering.codeintel` — rebuild determinism | 11 |
| C-25 | Candidate manifest + assembly report | `engineering.candidate` | candidate workspace | acceptance, release | ART | `docs/contracts/candidate.md` | semver | STRICT | `engineering.candidate` — 8 assembly checks | 12 |
| C-26 | Repair fingerprint + budget ledger | `engineering.repair` | repair engine | acceptance, knowledge | EVD | `docs/contracts/repair.md` | semver | STRICT | `engineering.repair` — anti-loop property tests | 14 |
| C-27 | Golden Repair corpus entry | `engineering.repair` | corpus definition (0B) | repair benchmark | ART | `docs/canonical/GOLDEN_REPAIR_CORPUS_DEFINITION.md` | versioned + content-hashed | STRICT | `acceptance.engine` — benchmark evidence | 0B (def) / 30 (instances) |
| C-28 | Knowledge record + validity state | `engineering.knowledge` | knowledge authority | agents, factory | INT | `docs/contracts/knowledge.md` | semver | ADDITIVE | `engineering.knowledge` — lifecycle tests | 18 |
| C-29 | Imported project descriptor + tier assignment | `engineering.import` | import pipeline | isolation, candidate | INT | `docs/contracts/import.md` | semver | STRICT | `engineering.import` — 7 rescue conditions | 19 |
| C-30 | Plugin manifest | `engineering.plugin` | third-party plugin | plugin lifecycle, PDP | MANIFEST | `docs/contracts/plugin_manifest.md` | semver | PINNED | `engineering.plugin` — permission mapping tests | 21 |
| C-31 | Release manifest + SBOM | `lifecycle.release` | release pipeline | installer, verification, delivery | ART | `docs/contracts/release_manifest.md` | semver | STRICT | `lifecycle.release` — hash + provenance | 26 |
| C-32 | Stable revision pointer + rollback record | `lifecycle.recovery` | Recovery Supervisor | release, build state | EVD | `docs/contracts/rollback.md` | revision-hashed | STRICT | `lifecycle.recovery` — rollback evidence | 22B |
| C-33 | Evolution campaign declaration + terminal record | `lifecycle.evolution` | evolution engine | acceptance, human gate 2 | EVD | `docs/contracts/campaign.md` | semver | STRICT | `lifecycle.evolution` — bounded-loop property tests | 23 |
| C-34 | Operations telemetry projection | `surfaces.operations` | owning authorities (read-only) | Command Center | HTTP | `docs/contracts/operations_api.md` | semver | ADDITIVE | `surfaces.operations` — no-fake-telemetry tests | 25 |
| C-35 | Command Center HTTP API | `surfaces.command` | backend surfaces | React frontend, Tauri shell | HTTP | `docs/contracts/command_api.md` | semver | ADDITIVE | `surfaces.command` — E2E + drift tests | 5 onward |
| C-36 | Product Evolution SDK contract | `lifecycle.evolution` | SDK | AI-native child products | INT | `docs/contracts/product_sdk.md` | semver | PINNED | `lifecycle.evolution` — child independence tests | 24 |

**36 contract families. 0 contracts with more than one owning context.**

## Protected Core contracts

C-05, C-06, C-07, C-08, C-09, C-10, C-15, C-16, C-17, C-18, C-31, C-32 are owned by Protected Core contexts. Changing any of them runs the Stable Core candidate lifecycle and requires HUMAN GATE 2.

## Contracts required before Phase 2 implementation begins

C-01, C-03, C-04, C-05, C-06, C-17, C-18 — the foundation set. Phase 2 cannot deliver the Phase Gate Checker without C-17 and C-18.
