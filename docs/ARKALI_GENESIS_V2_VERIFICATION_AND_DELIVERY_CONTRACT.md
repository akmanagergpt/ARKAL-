# ARKALI GENESIS v2 — VERIFICATION AND DELIVERY CONTRACT

**Status:** FROZEN / AUTHORITATIVE

This document defines what must be PROVEN before ARKALI GENESIS v2 can be delivered as production-ready.

## Final states
Only:
PRODUCTION READY
or
RELEASE CANDIDATE — NOT PRODUCTION READY.

## Fundamental rule
Implementation does not equal verification. Files, compile PASS, HTTP 200, visible button, smoke PASS, AI PASS or simulation-only PASS are insufficient.

Canonical VERIFIED means applicable:
Implementation + Real Binding + Security + Persistence + Executable Tests + Runtime Evidence + Real Program Generation + Acceptance + Documentation.

## Proof-of-Engineering Passport
Every critical capability records applicable:
requirement/specification, architecture/contract, implementation, security, unit, contract, integration, real runtime, real generated product, browser/E2E, persistence, mutation, property/fuzz, chaos, restart/recovery, adversarial review, provenance, regression, final acceptance.
Mandatory evidence missing => not VERIFIED.

## Golden Product Suite
Generate real products THROUGH ARKALI’s normal pipeline:
1. Task/Work Management
2. Student/Fee Management
3. Property/Facility/Document Workflow
4. Inventory/Stock/Transaction
5. AI-Native Self-Evolving Product

Flow must be real:
intent→requirements→specification→architecture→tasks→providers/agents→artifacts→assembly→build→runtime→acceptance→release.

Do not manually build and register them as generated.

## Hidden generalization
At least one unseen product domain is introduced only after the factory architecture exists. ARKALI must derive requirements, architecture, data model, API, frontend, tests and acceptance without domain hard-coding.

## Cross-generation reliability
At least one specification is generated more than once from clean state. Byte-identical code is unnecessary; all runs must satisfy the same mandatory behavioral contracts.

## Real provider/model
Mocks are allowed for low-level unit tests. Golden Factory Acceptance requires at least one real cloud provider or working local model generating real artifacts. If absent: BLOCKED/NOT_CONFIGURED, never PASS.

## Verification levels
L1 Simulation: controlled failures.
L2 Real Execution: actual source/build/process/DB/browser/runtime.
L3 Clean Environment: actual packaged release installed on clean Windows.
Production PASS requires applicable L2/L3 evidence.

## Real user journeys
Generated apps must be genuinely used: launch, authenticate if needed, create/search/edit/domain action/refresh/restart/persistence. Browser automation checks console errors, network failures, dead controls, navigation and frontend/backend drift.

## Mutation / Property / Fuzz
Controlled code mutations must be caught by critical tests. Critical invariants include:
- stable revision comes from accepted candidate,
- mandatory accepted candidate has evidence,
- DENY cannot be bypassed by UI/API/agent/workflow,
- restore preserves integrity,
- candidate cannot directly mutate stable,
- invalid state transition is rejected.
Fuzz malformed AI outputs/parsers/security boundaries where valuable.

## Chaos / Failure injection
Applicable scenarios:
provider timeout/failure; invalid AI artifact; worker kill; backend restart; browser/plugin crash; DB lock; network loss; disk pressure/full; corrupt artifact; migration failure; upgrade failure; resource exhaustion.
Containment/recovery must be evidenced.

## Durable restart
Interrupt real durable work. Expected: RESUMED or explicit RECOVERABLE state. Silent disappearance = FAIL.

## Backup / restore
State A→Backup→State B→Restore A→Verify A. File copy alone = FAIL.

## Migration safety
Impact→Backup→Dry Run→Integrity→Candidate Migration→Application Tests→Apply→Verify→Rollback Point. Known data-loss risk blocks release.

## Recovery Supervisor
Bad ARKALI upgrade candidate→launch→health failure→known-good rollback→failure record→stable available. Mandatory.

## Security verification
Secret leakage scan; permission/policy enforcement; sandbox enforcement; path/file/input security where applicable; dependency/supply-chain review; release secret scan; Local-Only enforcement; audit coverage. Critical finding blocks release.

## Policy bypass
AUTO/ASK_USER/DENY must be enforced consistently through API, UI, agent, workflow and plugin/connector paths.

## Provenance
Critical generated/release artifacts record hash, producer/task, provider/model, spec version, context hash, parents, normalization, tests and evidence. Release manifest includes cryptographic hashes.

## Architecture verification
Required automated gates:
duplicate/shadow active definitions = 0
canonical authority conflicts = 0
forbidden bounded-context imports = 0
forbidden cycles = 0
giant central module violations = 0 unless explicitly justified within budget
protected-core policy violations = 0.

## Failure-domain verification
Failure of provider/plugin/worker/browser executor/optional local model must not unnecessarily crash unrelated capabilities.

## Operations truthfulness
Operations Center shows real jobs, workflow states, provider/model state, CPU/RAM/GPU/VRAM where available, disk, workers/queues, cost/token where available and stuck detection. No fake telemetry.

## Source Intelligence Export
Generate full system TXT and AI Review Bundle. Verify architecture, tree, contracts, issues, acceptance, full selected source, clear boundaries and secret redaction.

## Child Product Evolution
AI-Native child product must run independently of main ARKALI, accept admin improvement request, create impact/candidate/tests/approval/promotion/rollback. Full ARKALI core cannot be copied as child runtime.

## ARKALI Self-Evolution
Stable snapshot→isolated core candidate→improvement→tests→architecture→security→compatibility→approval→promotion/rejection. Direct uncontrolled live-core mutation = FAIL.

## Four pre-delivery hardening rounds
After first full acceptance PASS:
1. Architecture & Maintainability
2. Reliability & Security
3. Performance/Cost/Resource/UX
4. Adversarial Future-Proofing/Generalization
Each compares candidate against baseline and keeps only measured improvement without unacceptable regression. Run full regression again after Round 4.

## Direct-AI benchmark
Where practical compare Direct primary AI vs ARKALI+same AI vs ARKALI multi-agent using comparable requirements. Measure build success, correctness, test quality, security, architecture, UX, maintainability, repairs, human intervention, time and cost. ARKALI should demonstrate measurable engineering value, not only orchestration overhead.

## Clean installation
Test actual packaged release on clean Windows:
install→first run→diagnostics→setup→configure provider/local model→create project→generate product→observe→acceptance→use product→restart/persistence→backup/restore.

## Final delivery
Complete repo; Windows installer; dependency/build locks; migrations; architecture/ADR/API/security docs; admin/developer/backup guides; workflow/plugin/provider docs; test/security/acceptance reports; Golden Product reports; chaos/mutation reports; four hardening reports; source export; AI Review Bundle; SBOM/dependency inventory where supported; checksums; release manifest; ARKALI_RELEASE_QUALITY_REPORT.md.

## Release blockers
Critical security vulnerability; known data-loss defect; mandatory acceptance/evidence missing; fake mandatory capability; secret leakage; infinite repair behavior; failed restore; failed Recovery Supervisor; uncontrolled live-core modification; unresolved authority conflict; clean installer failure; Golden Factory failure; Golden Repair failure.

## Production Ready
Requires:
mandatory requirements coverage = 100%
mandatory evidence coverage = 100%
architecture violations = 0
authority conflicts = 0
critical security findings = 0
known data-loss defects = 0
fake mandatory implementations = 0
mandatory tests = PASS
Golden Product suite = PASS
hidden generalization = PASS
Golden Repair = PASS
durable restart = PASS
backup/restore = PASS
Recovery Supervisor = PASS
clean installation = PASS
four hardening rounds complete and final regression PASS
required delivery artifacts present.
Otherwise: RELEASE CANDIDATE — NOT PRODUCTION READY.
