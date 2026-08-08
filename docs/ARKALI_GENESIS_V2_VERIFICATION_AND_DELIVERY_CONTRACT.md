# ARKALI GENESIS v2 — VERIFICATION AND DELIVERY CONTRACT

**Status:** FROZEN / AUTHORITATIVE
**Revision:** canonical architecture repair applied before Phase 0

This document defines what must be PROVEN before ARKALI GENESIS v2 can be delivered as production-ready.

## Final states
Only:
PRODUCTION READY
or
RELEASE CANDIDATE — NOT PRODUCTION READY.

## Acceptance authority
The human operator is the ultimate canonical acceptance authority and holds the canonical HUMAN GATES defined in the Build Protocol. Machine acceptance verdicts are authoritative for all other phase gates and require no human approval. The final PRODUCTION READY determination requires an explicit recorded human acceptance decision referencing the evidence set.

## Fundamental rule
Implementation does not equal verification. Files, compile PASS, HTTP 200, visible button, smoke PASS, AI PASS or simulation-only PASS are insufficient.

Canonical VERIFIED means applicable:
Implementation + Real Binding + Security + Persistence + Executable Tests + Runtime Evidence + Real Program Generation + Acceptance + Documentation.

## Applicability authority
Every occurrence of "applicable" in this contract resolves against the Canonical Requirement Register. No verdict may rest on an applicability judgment made by an implementing agent. Unregistered applicability claims are FAIL, not NOT_APPLICABLE.

## Conditional language
This contract contains no convenience-based exceptions. Every conditional requirement resolves through an objective applicability rule recorded in the Canonical Requirement Register. The phrases "where practical", "where valuable", "where available", "where supported" and "where possible" carry no meaning beyond their registered rule, and an implementing actor may not resolve them by judgment.

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
At least one specification is generated at least twice from clean state, and the number of generation runs is bounded by a declared run budget recorded before execution. Byte-identical code is unnecessary; all runs must satisfy the same mandatory behavioral contracts.

## Real provider/model
Mocks are allowed for low-level unit tests. Golden Factory Acceptance requires at least one real cloud provider or working local model generating real artifacts. If absent: BLOCKED/NOT_CONFIGURED, never PASS. Never fabricate or simulate an external-provider result.

## Verification levels
L1 Simulation: controlled failures.
L2 Real Execution: actual source/build/process/DB/browser/runtime.
L3 Clean Environment: actual packaged release installed on the canonical Windows clean-test baseline, restored from snapshot before the run.
Production PASS requires applicable L2/L3 evidence.

## Real user journeys
Generated apps must be genuinely used: launch, authenticate if needed, create/search/edit/domain action/refresh/restart/persistence. Browser automation checks console errors, network failures, dead controls, navigation and frontend/backend drift.

## Mutation / Property / Fuzz
Controlled code mutations must be caught by critical tests. Critical invariants include:
- stable revision comes from accepted candidate,
- no actor or mechanism directly mutates stable except Recovery Supervisor ROLLBACK_STABLE to a previously verified immutable revision,
- mandatory accepted candidate has evidence,
- DENY cannot be bypassed by UI/API/agent/workflow/plugin/computer-use,
- restore preserves integrity,
- candidate cannot directly mutate stable,
- invalid state transition is rejected.
Fuzz malformed AI outputs, parsers and security boundaries per their Canonical Requirement Register applicability rule; fuzzing is mandatory for parsers, security boundaries and AI-output deserializers.

## Chaos / Failure injection
Applicable scenarios:
provider timeout/failure; invalid AI artifact; worker kill; backend restart; browser/plugin crash; DB lock; network loss; disk pressure/full; corrupt artifact; migration failure; upgrade failure; resource exhaustion.
Containment/recovery must be evidenced.

## Durable restart
Interrupt real durable work. Expected: RESUMED or explicit RECOVERABLE state. Silent disappearance = FAIL.

## Workflow Studio execution identity
Prove that the executor consumes the persisted canonical graph revision and no other authority. For every canonical node type — trigger, AI, agent, engineering, logic, data, integration, approval, release, notification — and every control construct — IF, ELSE, SWITCH, LOOP, PARALLEL, MERGE, WAIT, RETRY, ERROR HANDLER, HUMAN APPROVAL — provide execution evidence bound to the graph revision hash. HUMAN APPROVAL must be evidenced as an enforced policy stop, not a visual element. A node type present in the UI without execution evidence is FAIL.

Derived compiled or cached representations are permitted only when deterministically derived from, hash-bound to, and invalidated by the canonical graph revision. Evidence must show that a canonical graph change invalidates every derived representation and that a stale-hash derived representation is never executed.

## Golden Repair
Execute the Golden Repair Benchmark against an accepted Golden Product revision. Evidence must record corpus hash, declared budgets, per-defect outcome, budget consumption, regression delta and terminal state of the unrepairable defect. Corpus modification to obtain PASS is a release blocker.

## Backup / restore
State A→Backup→State B→Restore A→Verify A. File copy alone = FAIL.

## Migration safety
Impact→Backup→Dry Run→Integrity→Candidate Migration→Application Tests→Apply→Verify→Rollback Point. APPLY to real or stable data requires HUMAN GATE 6. Known data-loss risk blocks release.

## Recovery Supervisor
Bad ARKALI upgrade candidate→launch→health failure→known-good rollback→failure record→stable available. Mandatory. Rollback must restore a previously verified immutable revision, perform no transformation during restore, and emit rollback evidence.

## Security verification
Secret leakage scan; permission/policy enforcement; sandbox enforcement; path/file/input security per register rule; dependency/supply-chain review; release secret scan; Local-Only enforcement; audit coverage. Critical finding blocks release.

Sandbox enforcement — per trust tier, evidenced escape tests covering filesystem escape, network egress, process escape, credential access and resource exhaustion; plus a negative-control test proving execution is DENIED when a required security property cannot be provided by any available Isolation Backend, and that ARKALI remains operational for capabilities whose requirements are still satisfied.

Secret Vault boundary — evidence that no agent, workflow, plugin, generated product or computer-use worker can write, read or export a raw secret value, and that raw values never appear in context packages, logs, prompts or exports.

Local-Only enforcement — with the mode enabled, evidence that outbound egress is DENIED on every path (provider, research, plugin/connector, browser, agent, workflow) while loopback-dependent local verification continues to pass.

## Policy bypass
AUTO/ASK_USER/DENY must be enforced consistently through API, UI, agent, workflow, plugin/connector and computer-use paths, per declared operation class. WRITE_STABLE_FILE must be DENY for every actor; ROLLBACK_STABLE must be permitted only to the deterministic Recovery Supervisor. An action that cannot be mapped to a declared operation class must be DENY.

## Import / Reverse Engineering / Rescue
Verify for every rescue mode — Repair in Place, Controlled Modernization, Clean Rebuild with Migration:
- static inspection completes before any untrusted execution;
- imported code is assigned its correct TRUST tier and cannot be reassigned by an implementing actor;
- the original source is preserved unmodified and independently restorable;
- all generated modifications occur in a candidate or working copy;
- provenance from original artifact to candidate artifact remains traceable;
- rescue cannot overwrite the source project, silently or otherwise;
- execution is DENY where the tier's required security properties cannot be established.

## Provenance
Critical generated/release artifacts record hash, producer/task, provider/model, spec version, context hash, parents, normalization, tests and evidence. Release manifest includes cryptographic hashes.

## Architecture verification
Required automated gates, evaluated against docs/canonical/AUTHORITY_MAP.yaml:
duplicate canonical authority = 0
shadow registry (a second store of a concern owned elsewhere) = 0
duplicate state-machine authority = 0
duplicate lifecycle authority = 0
forbidden dependency direction = 0
forbidden cycles = 0
protected-core boundary violation = 0
architecture budget violation = 0 except where recorded as an approved ADR exception under HUMAN GATE 8

A checker that detects only duplicate identifiers or class names does not satisfy these gates. Each gate must demonstrate detection on a deliberately violating fixture.

## Failure-domain verification
Failure of provider/plugin/worker/browser executor/optional local model must not unnecessarily crash unrelated capabilities.

## Operations truthfulness
Operations Center shows real jobs, workflow states, provider/model state, CPU/RAM/GPU/VRAM, disk, workers/queues, cost/token and stuck detection, each per its Canonical Requirement Register applicability rule derived from the Phase 4 hardware/provider capability probe. No fake telemetry.

## Source Intelligence Export
Generate full system TXT and AI Review Bundle. Verify architecture, tree, contracts, issues, acceptance, full selected source, clear boundaries and secret redaction.

## Child Product Evolution
AI-Native child product must run independently of main ARKALI, accept admin improvement request, create impact/candidate/tests/approval/promotion/rollback. Full ARKALI core cannot be copied as child runtime. Improvement cycles use the bounded campaign model.

## ARKALI Self-Evolution
Stable snapshot→isolated core candidate→improvement→tests→architecture→security→compatibility→approval→promotion/rejection. Direct uncontrolled live-core mutation = FAIL.

Campaign evidence must record objective, baseline metrics, declared budgets, per-candidate outcome, budget consumption, regression delta and terminal state. An evolution run without a bounded campaign record is FAIL. Promotion requires HUMAN GATE 2 and a verified Recovery Supervisor.

## Four pre-delivery hardening rounds
After first full acceptance PASS:
1. Architecture & Maintainability
2. Reliability & Security
3. Performance/Cost/Resource/UX
4. Adversarial Future-Proofing/Generalization
Each compares candidate against baseline and keeps only measured improvement without unacceptable regression, under the declared budgets and terminal states defined in the Master Specification. Run full regression again after Round 4.

If the post-Round-4 full regression fails, the outcome is ESCALATED to the human acceptance authority. It does not re-enter Round 4 and does not start a new round.

## Direct-AI benchmark
Compare Direct primary AI vs ARKALI+same AI vs ARKALI multi-agent using comparable requirements, per its Canonical Requirement Register applicability rule (applicable when at least one real provider is configured and the Golden Product suite has passed). Measure build success, correctness, test quality, security, architecture, UX, maintainability, repairs, human intervention, time and cost. ARKALI should demonstrate measurable engineering value, not only orchestration overhead.

Benchmark states: PASS, FAIL, NOT_CONFIGURED, EXTERNAL_UNAVAILABLE. NOT_CONFIGURED and verified EXTERNAL_UNAVAILABLE do not by themselves block Production Release. Never fabricate or simulate an external-provider PASS.

## Clean installation
Test actual packaged release on the canonical Windows clean-test baseline:
install→first run→diagnostics→setup→configure provider/local model→create project→generate product→observe→acceptance→use product→restart/persistence→backup/restore.

The baseline is a named Windows edition and build restored from a snapshot immediately before each canonical run, with Python, Node.js, Rust/Cargo, Git, MSVC build tools and any prior ARKALI runtime or data absent. Baseline identity and snapshot revision are recorded in the L3 evidence artifact. This requirement applies to the acceptance environment only and is not imposed on end users.

## Final delivery
Complete repo; Windows installer; dependency/build locks; migrations; architecture/ADR/API/security docs; admin/developer/backup guides; workflow/plugin/provider docs; test/security/acceptance reports; Golden Product reports; Golden Repair report; chaos/mutation reports; four hardening reports; source export; AI Review Bundle; SBOM/dependency inventory per register rule; checksums; release manifest; ARKALI_RELEASE_QUALITY_REPORT.md.

## Release blockers
Critical security vulnerability; known data-loss defect; mandatory acceptance/evidence missing; fake mandatory capability; fabricated or simulated external-provider result; secret leakage; infinite repair behavior; unbounded hardening round or evolution campaign; failed restore; failed Recovery Supervisor; uncontrolled live-core modification; unresolved authority conflict; clean installer failure; Golden Factory failure; Golden Repair failure.

## Production Ready
Requires:
mandatory requirements coverage = 100% of MANDATORY entries in the Canonical Requirement Register, plus 100% of CONDITIONAL entries whose applicability rule evaluates true
mandatory evidence coverage = 100% of the required acceptance evidence recorded against those entries
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
four hardening rounds each terminated in PASS or COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN, and final regression PASS; a round terminating in ESCALATED or BLOCKED is a release blocker until resolved
required delivery artifacts present
explicit human acceptance decision recorded under HUMAN GATE 7.

The Direct-AI benchmark in state NOT_CONFIGURED or verified EXTERNAL_UNAVAILABLE does not block Production Release.

Otherwise: RELEASE CANDIDATE — NOT PRODUCTION READY.
