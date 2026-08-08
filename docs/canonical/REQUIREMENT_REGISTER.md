# ARKALI GENESIS v2 — CANONICAL REQUIREMENT REGISTER

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1
**Canonical source commit:** `079c925996034017855fb9d1f1fa532077d7e86d`

## Governing rules

1. IDs are immutable `ARK-REQ-####`. Never reused, renumbered or retired. Superseded entries are marked `SUPERSEDED_BY` and retained.
2. Classification is `MANDATORY` | `CONDITIONAL` | `OPTIONAL`.
3. Any normative statement in the canonical set not classified here **defaults to MANDATORY**.
4. This register is the **sole denominator** for requirement and evidence coverage. Coverage computed against any other set is invalid.
5. Implementing agents may **evaluate** applicability rules. They may not author, amend, broaden or reinterpret them, and may not classify any requirement.
6. No convenience-based `NOT_APPLICABLE` rule exists. Every `CONDITIONAL` rule in Appendix A is objective and machine-evaluable from recorded system state.
7. Unwaived, unevaluable rules resolve to **APPLICABLE**.
8. Exceptional waivers require HUMAN GATE 5, written justification, a waiver evidence artifact and an expiry condition.

Source keys: **MS** = Master Specification · **BP** = Build Protocol · **VDC** = Verification & Delivery Contract.
Evidence keys: `arch`=architecture test · `unit` · `contract` · `integ`=integration · `sec`=security test · `e2e`=browser · `persist`=persistence · `chaos` · `mut`=mutation · `prop`=property · `prov`=provenance · `doc`=canonical document · `run`=real runtime · `human`=human gate record.

---

## Block 1 — Master Specification (ARK-REQ-0001 … 0098)

| ID | Requirement | Source | Class | Phase | Owner | Evidence |
|---|---|---|---|---|---|---|
| ARK-REQ-0001 | System is a local-first Engineering Control Fabric | MS §intro | MANDATORY | 0A | control.architecture | doc, arch |
| ARK-REQ-0002 | Control Plane components exist as specified | MS §Control Plane | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0003 | Execution Plane components exist as specified | MS §Execution Plane | MANDATORY | 7 | execution.durable | arch, integ |
| ARK-REQ-0004 | Evidence Plane components exist as specified | MS §Evidence Plane | MANDATORY | 6 | evidence.artifact | arch, prov |
| ARK-REQ-0005 | Product Plane components exist as specified | MS §Product Plane | MANDATORY | 12 | engineering.candidate | arch |
| ARK-REQ-0006 | Stable Product / Stable Core revisions are distinctly defined | MS §Product Plane | MANDATORY | 0A | control.architecture | doc, prop |
| ARK-REQ-0007 | Stable definitions take effect from first Release-Authority designation | MS §Product Plane | MANDATORY | 26 | lifecycle.release | doc |
| ARK-REQ-0008 | Backend stack: Python 3.13, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic | MS §Frozen tech | MANDATORY | 2 | kernel.persistence | arch |
| ARK-REQ-0009 | Frontend stack: React, TypeScript, Vite, Tailwind | MS §Frozen tech | MANDATORY | 5 | surfaces.command | arch |
| ARK-REQ-0010 | Desktop: Tauri 2.x | MS §Frozen tech | MANDATORY | 28 | surfaces.command | arch, run |
| ARK-REQ-0011 | Persistence: SQLite+WAL local-first | MS §Frozen tech | MANDATORY | 5 | kernel.persistence | arch, persist |
| ARK-REQ-0012 | PostgreSQL-ready abstractions | MS §Frozen tech | CONDITIONAL | 5 | kernel.persistence | arch |
| ARK-REQ-0013 | Test stack incl. contract/architecture/property/mutation/chaos + Playwright | MS §Frozen tech | MANDATORY | 2 | acceptance.engine | unit, arch |
| ARK-REQ-0014 | Observability OpenTelemetry-compatible | MS §Frozen tech | MANDATORY | 2 | kernel.observability | integ |
| ARK-REQ-0015 | Git-linked revisions, content hashes, SBOM/signing-ready design | MS §Frozen tech | MANDATORY | 26 | evidence.artifact | prov |
| ARK-REQ-0016 | Local AI adapter-based, no single-runtime dependency | MS §Frozen tech | MANDATORY | 22 | engineering.localai | arch |
| ARK-REQ-0017 | Isolation Backend abstraction in frozen tech direction | MS §Frozen tech | MANDATORY | 4 | control.isolation | arch, sec |
| ARK-REQ-0018 | One canonical authority per concern | MS §Constitution 1 | MANDATORY | 0B | control.architecture | arch |
| ARK-REQ-0019 | Duplicate/shadow active definitions are CI failures | MS §Constitution 2 | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0020 | No giant factory/orchestration module | MS §Constitution 3 | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0021 | No patch-stack architecture as normal development method | MS §Constitution 4 | MANDATORY | 0A | control.architecture | doc, arch |
| ARK-REQ-0022 | Deterministic Core / Probabilistic Edge separation | MS §Constitution 5 | MANDATORY | 0A | control.architecture | arch |
| ARK-REQ-0023 | No actor or mechanism directly mutates Stable Core/Product revisions | MS §Constitution 6 | MANDATORY | 12 | lifecycle.release | prop, mut, sec |
| ARK-REQ-0024 | Prohibition covers AI, transformers, workflows, plugins, computer-use, human tools | MS §Constitution 6 | MANDATORY | 12 | control.policy | sec, prop |
| ARK-REQ-0025 | Required path stable→candidate→verification→acceptance→promotion | MS §Constitution 6 | MANDATORY | 12 | lifecycle.release | prop, integ |
| ARK-REQ-0026 | No fake success, metrics, providers, dead UI, TODO-as-implementation | MS §Constitution 7 | MANDATORY | 2 | acceptance.engine | arch, integ |
| ARK-REQ-0027 | No long AI work inside HTTP requests | MS §Constitution 8 | MANDATORY | 7 | execution.durable | arch, integ |
| ARK-REQ-0028 | Evidence is authoritative; AI opinion is not | MS §Constitution 9 | MANDATORY | 13 | acceptance.engine | doc, integ |
| ARK-REQ-0029 | Repair loops formally budgeted and bounded | MS §Constitution 10 | MANDATORY | 14 | engineering.repair | prop, integ |
| ARK-REQ-0030 | Constitution 2/3 enforced against numeric architecture budgets | MS §Constitution | MANDATORY | 0B | control.architecture | arch |
| ARK-REQ-0031 | Budget exception requires ADR + HUMAN GATE 8 | MS §Constitution | MANDATORY | 0B | control.architecture | human, arch |
| ARK-REQ-0032 | Budget exception may not rest on implementing-actor justification | MS §Constitution | MANDATORY | 0B | control.policy | arch, sec |
| ARK-REQ-0033 | Every normative requirement carries an immutable ARK-REQ-#### ID | MS §Register | MANDATORY | 0B | control.specification | doc, arch |
| ARK-REQ-0034 | Register records all eight required fields per entry | MS §Register | MANDATORY | 0B | control.specification | doc |
| ARK-REQ-0035 | IDs never reused, renumbered or retired | MS §Register | MANDATORY | 0B | control.specification | arch |
| ARK-REQ-0036 | Unclassified normative statements default to MANDATORY | MS §Register | MANDATORY | 0B | control.specification | arch |
| ARK-REQ-0037 | Register is sole coverage denominator | MS §Register | MANDATORY | 13 | acceptance.engine | arch, integ |
| ARK-REQ-0038 | MANDATORY entries can never be waived by an automated actor | MS §Applicability | MANDATORY | 13 | control.policy | sec, prop |
| ARK-REQ-0039 | CONDITIONAL entries carry objective machine-evaluable rules | MS §Applicability | MANDATORY | 0B | control.specification | doc, arch |
| ARK-REQ-0040 | Agents may evaluate but never author/amend applicability | MS §Applicability | MANDATORY | 13 | control.policy | sec, prop |
| ARK-REQ-0041 | Waiver requires HUMAN GATE 5 + evidence + expiry | MS §Applicability | MANDATORY | 13 | acceptance.engine | human |
| ARK-REQ-0042 | Unevaluable rules resolve to APPLICABLE | MS §Applicability | MANDATORY | 13 | acceptance.engine | unit |
| ARK-REQ-0043 | Twelve critical entities use validated state machines | MS §State machines | MANDATORY | 3 | control.architecture | unit, prop |
| ARK-REQ-0044 | Invalid transitions structurally impossible | MS §State machines | MANDATORY | 3 | control.architecture | prop, mut |
| ARK-REQ-0045 | Capability Graph nodes carry the specified attribute set | MS §Capability Graph | MANDATORY | 3 | control.capability | contract |
| ARK-REQ-0046 | Graph answers "Can I perform this?" deterministically | MS §Capability Graph | MANDATORY | 9B | control.capability | unit, integ |
| ARK-REQ-0047 | External attributes stored as references, never copies | MS §Capability Graph | MANDATORY | 9B | control.capability | arch |
| ARK-REQ-0048 | Schema at Phase 3, activation at Phase 9B | MS §Capability Graph | MANDATORY | 9B | control.capability | arch |
| ARK-REQ-0049 | Pre-activation queries return NOT_CONFIGURED, never stubs | MS §Capability Graph | MANDATORY | 3 | control.capability | unit |
| ARK-REQ-0050 | Agents are roles; providers are backends; separation maintained | MS §Provider/Agent | MANDATORY | 10 | engineering.agent | arch |
| ARK-REQ-0051 | Agents cannot mutate canonical requirements or self-accept output | MS §Provider/Agent | MANDATORY | 10 | control.policy | sec, prop |
| ARK-REQ-0052 | Provider/Model Registry is sole authority for 7 provider concerns | MS §Provider/Agent | MANDATORY | 9 | control.registry.provider | arch |
| ARK-REQ-0053 | No component may store/cache/mirror/default/re-derive provider values | MS §Provider/Agent | MANDATORY | 9 | control.registry.provider | arch |
| ARK-REQ-0054 | Every engineering task executes as a bounded harness task | MS §Harness | MANDATORY | 10 | engineering.agent | contract, integ |
| ARK-REQ-0055 | Context Compiler sends only relevant context, provenance recorded | MS §Context Compiler | MANDATORY | 10 | engineering.agent | prov, integ |
| ARK-REQ-0056 | Ephemeral workspace pipeline; agents cannot overwrite each other | MS §Workspaces | MANDATORY | 12 | engineering.candidate | integ, prop |
| ARK-REQ-0057 | Artifacts immutable, versioned, content-addressed with full metadata | MS §Artifact Fabric | MANDATORY | 6 | evidence.artifact | prov, unit |
| ARK-REQ-0058 | Semantic assembly validates all eight consistency pairs | MS §Semantic Assembly | MANDATORY | 12 | engineering.candidate | integ, contract |
| ARK-REQ-0059 | Durable runtime provides the full durability feature set | MS §Durable Runtime | MANDATORY | 7 | execution.durable | integ, chaos |
| ARK-REQ-0060 | Pause/resume support | MS §Durable Runtime | CONDITIONAL | 7 | execution.durable | integ |
| ARK-REQ-0061 | Temporal-grade durability without mandatory Temporal dependency | MS §Durable Runtime | MANDATORY | 7 | execution.durable | arch, chaos |
| ARK-REQ-0062 | Workflow Studio supports all node types and control constructs | MS §Workflow Studio | MANDATORY | 17 | execution.workflow | integ, e2e |
| ARK-REQ-0063 | Persisted versioned canonical graph is the sole authority | MS §Workflow Studio | MANDATORY | 17 | execution.workflow | arch, integ |
| ARK-REQ-0064 | Derived caches deterministically derived, hash-bound, invalidated | MS §Workflow Studio | MANDATORY | 17 | execution.workflow | unit, integ |
| ARK-REQ-0065 | Stale-hash derived representation never executed | MS §Workflow Studio | MANDATORY | 17 | execution.workflow | prop, integ |
| ARK-REQ-0066 | Code Intelligence maintains the specified graph set | MS §Code Intelligence | MANDATORY | 11 | engineering.codeintel | unit, integ |
| ARK-REQ-0067 | Digital Twin composes the nine specified views | MS §Code Intelligence | MANDATORY | 11 | engineering.codeintel | integ |
| ARK-REQ-0068 | Acceptance chain Evidence→Acceptance Engine→Release Authority | MS §Independent Acceptance | MANDATORY | 13 | acceptance.engine | arch |
| ARK-REQ-0069 | Evidence Graph links Requirement→…→Result | MS §Independent Acceptance | MANDATORY | 13 | acceptance.engine | integ, prov |
| ARK-REQ-0070 | Machine verdicts never supersede a mandatory HUMAN GATE | MS §Independent Acceptance | MANDATORY | 13 | control.policy | sec, prop |
| ARK-REQ-0071 | Independence is structural: acceptance contracts are Protected Core | MS §Independent Acceptance | MANDATORY | 4 | control.policy | sec, mut |
| ARK-REQ-0072 | Five Golden Product families generated through the real pipeline | MS §Real Program Gen | MANDATORY | 30 | engineering.factory | run, e2e, persist |
| ARK-REQ-0073 | Unseen-domain generalization test | MS §Real Program Gen | MANDATORY | 31 | engineering.factory | run, e2e |
| ARK-REQ-0074 | Golden domain logic must not enter ARKALI core | MS §Real Program Gen | MANDATORY | 30 | control.architecture | arch |
| ARK-REQ-0075 | L1/L2/L3 execution levels defined and used | MS §Execution Levels | MANDATORY | 30 | acceptance.engine | run |
| ARK-REQ-0076 | Simulation alone cannot produce production PASS | MS §Execution Levels | MANDATORY | 30 | acceptance.engine | arch, prop |
| ARK-REQ-0077 | L3 runs on the canonical Windows clean-test baseline from snapshot | MS §Execution Levels | MANDATORY | 36 | lifecycle.release | run |
| ARK-REQ-0078 | Named absent-tooling list enforced before install | MS §Execution Levels | MANDATORY | 36 | lifecycle.release | run |
| ARK-REQ-0079 | Baseline identity + snapshot revision recorded in L3 evidence | MS §Execution Levels | MANDATORY | 36 | evidence.artifact | prov |
| ARK-REQ-0080 | Test applicability determined by register, not implementing actors | MS §Test Intelligence | MANDATORY | 13 | acceptance.engine | arch |
| ARK-REQ-0081 | Controlled mutations must be caught by critical tests | MS §Mutation | MANDATORY | 31 | acceptance.engine | mut |
| ARK-REQ-0082 | Critical invariants receive property testing | MS §Mutation | MANDATORY | 31 | acceptance.engine | prop |
| ARK-REQ-0083 | Fuzzing mandatory for parsers, security boundaries, AI-output deserializers | MS §Mutation | MANDATORY | 31 | acceptance.engine | sec |
| ARK-REQ-0084 | Fuzzing elsewhere | MS §Mutation | CONDITIONAL | 31 | acceptance.engine | sec |
| ARK-REQ-0085 | Chaos injection covers the twelve named scenarios | MS §Mutation | MANDATORY | 31 | acceptance.engine | chaos |
| ARK-REQ-0086 | Root-cause pipeline followed end to end | MS §Root-Cause | MANDATORY | 14 | engineering.repair | integ |
| ARK-REQ-0087 | Repair fingerprints recorded; repeated failed strategy escalates | MS §Root-Cause | MANDATORY | 14 | engineering.repair | integ, prop |
| ARK-REQ-0088 | Six repair budget dimensions enforced | MS §Root-Cause | MANDATORY | 14 | engineering.repair | prop, integ |
| ARK-REQ-0089 | Golden Repair executes against an accepted Golden Product revision | MS §Golden Repair | MANDATORY | 30 | engineering.repair | run |
| ARK-REQ-0090 | Versioned content-hashed defect corpus covering eight classes | MS §Golden Repair | MANDATORY | 0B | engineering.repair | doc, prov |
| ARK-REQ-0091 | Corpus includes at least one deliberately unrepairable defect | MS §Golden Repair | MANDATORY | 0B | engineering.repair | doc |
| ARK-REQ-0092 | Budgets declared before each Golden Repair run | MS §Golden Repair | MANDATORY | 30 | engineering.repair | prov |
| ARK-REQ-0093 | Golden Repair PASS requires all six listed conditions | MS §Golden Repair | MANDATORY | 30 | acceptance.engine | run, prov |
| ARK-REQ-0094 | Unrepairable defect reaches terminal ESCALATED within budget | MS §Golden Repair | MANDATORY | 30 | engineering.repair | prop, run |
| ARK-REQ-0095 | Corpus never modified to obtain PASS | MS §Golden Repair | MANDATORY | 30 | acceptance.engine | prov, sec |
| ARK-REQ-0096 | Security stack: identity, RBAC, vault, broker, PDP, PEP, audit, privacy | MS §Security | MANDATORY | 4 | control.policy | sec, arch |
| ARK-REQ-0097 | Decisions resolve to AUTO / ASK_USER / DENY | MS §Security | MANDATORY | 4 | control.policy | unit, sec |
| ARK-REQ-0098 | Secrets never enter source, logs, prompts, exports, release artifacts | MS §Security | MANDATORY | 4 | control.policy | sec |

## Block 2 — Master Specification continued (ARK-REQ-0099 … 0142)

| ID | Requirement | Source | Class | Phase | Owner | Evidence |
|---|---|---|---|---|---|---|
| ARK-REQ-0099 | Secrets enter vault only via explicit human-initiated provisioning | MS §Secret Vault | MANDATORY | 4 | control.policy | sec, human |
| ARK-REQ-0100 | No automated actor may write/read/export a raw secret | MS §Secret Vault | MANDATORY | 4 | control.policy | sec, prop |
| ARK-REQ-0101 | Consumers receive scoped, brokered, revocable references only | MS §Secret Vault | MANDATORY | 4 | control.policy | sec, unit |
| ARK-REQ-0102 | Vault protected by OS key-protection facility | MS §Secret Vault | MANDATORY | 4 | control.policy | sec |
| ARK-REQ-0103 | No OS key protection ⇒ secret-dependent capabilities UNSUPPORTED | MS §Secret Vault | MANDATORY | 4 | control.isolation | sec, unit |
| ARK-REQ-0104 | Local-Only mode DENYs all outbound egress on every path | MS §Local-Only | MANDATORY | 4 | control.policy | sec, integ |
| ARK-REQ-0105 | Loopback permitted under Local-Only | MS §Local-Only | MANDATORY | 4 | control.policy | integ |
| ARK-REQ-0106 | Local-Only toggle is HUMAN GATE 4 | MS §Local-Only | MANDATORY | 4 | control.policy | human |
| ARK-REQ-0107 | No silent cloud-path degradation under Local-Only | MS §Local-Only | MANDATORY | 4 | control.policy | sec, prop |
| ARK-REQ-0108 | Protected Core is explicit and machine-readable | MS §Protected Core | MANDATORY | 0B | control.architecture | doc, arch |
| ARK-REQ-0109 | Protected Core minimum membership present | MS §Protected Core | MANDATORY | 0B | control.architecture | arch |
| ARK-REQ-0110 | Protected Core modified only via Stable Core lifecycle + GATE 2 | MS §Protected Core | MANDATORY | 4 | control.policy | sec, human |
| ARK-REQ-0111 | Stronger verification profile for Protected Core changes | MS §Protected Core | MANDATORY | 4 | acceptance.engine | sec, integ |
| ARK-REQ-0112 | No implementing actor may alter Protected Core membership | MS §Protected Core | MANDATORY | 4 | control.policy | sec, prop |
| ARK-REQ-0113 | Seven security properties defined and used by tiers | MS §Trust Isolation | MANDATORY | 4 | control.isolation | sec, arch |
| ARK-REQ-0114 | TRUST-0..4 required property sets enforced | MS §Trust Isolation | MANDATORY | 4 | control.isolation | sec |
| ARK-REQ-0115 | TRUST-3 requires static inspection before any execution | MS §Trust Isolation | MANDATORY | 19 | engineering.import | sec, prop |
| ARK-REQ-0116 | TRUST-3 human approval before first execution | MS §Trust Isolation | MANDATORY | 19 | control.policy | human |
| ARK-REQ-0117 | TRUST-4 human approval per execution | MS §Trust Isolation | MANDATORY | 21 | control.policy | human |
| ARK-REQ-0118 | Isolation Backends declare provided properties; composition permitted | MS §Isolation Backends | MANDATORY | 4 | control.isolation | unit, sec |
| ARK-REQ-0119 | Capability runs only if a composition satisfies ALL tier properties | MS §Isolation Backends | MANDATORY | 4 | control.isolation | sec, prop |
| ARK-REQ-0120 | Unsatisfiable ⇒ capability UNSUPPORTED and execution DENY | MS §Isolation Backends | MANDATORY | 4 | control.isolation | sec, unit |
| ARK-REQ-0121 | ARKALI remains operational for satisfiable capabilities | MS §Isolation Backends | MANDATORY | 4 | control.isolation | integ, chaos |
| ARK-REQ-0122 | Tier never silently downgraded; property never substituted or defaulted | MS §Isolation Backends | MANDATORY | 4 | control.isolation | sec, prop |
| ARK-REQ-0123 | Backend availability probed at Phase 4 and recorded in Capability Graph | MS §Isolation Backends | MANDATORY | 4 | control.isolation | integ |
| ARK-REQ-0124 | Deterministic manifests/locks, provenance, SBOM, hashes, attestations | MS §Supply Chain | MANDATORY | 26 | lifecycle.release | prov |
| ARK-REQ-0125 | Suspicious-package review | MS §Supply Chain | MANDATORY | 26 | lifecycle.release | sec |
| ARK-REQ-0126 | Only evidence-backed outcomes become authoritative knowledge | MS §Knowledge | MANDATORY | 18 | engineering.knowledge | integ, prov |
| ARK-REQ-0127 | Knowledge lifecycle states implemented | MS §Knowledge | MANDATORY | 18 | engineering.knowledge | unit |
| ARK-REQ-0128 | Reusable components carry test/security/compatibility metadata | MS §Knowledge | MANDATORY | 18 | engineering.knowledge | contract |
| ARK-REQ-0129 | Local AI hardware-aware and adapter-based | MS §Knowledge | CONDITIONAL | 22 | engineering.localai | integ |
| ARK-REQ-0130 | Fine-tuning/distillation uses only verified datasets | MS §Knowledge | CONDITIONAL | 22 | engineering.localai | prov |
| ARK-REQ-0131 | Three child-product modes supported | MS §Child Products | MANDATORY | 24 | lifecycle.evolution | integ |
| ARK-REQ-0132 | Product Evolution SDK lifecycle implemented | MS §Child Products | MANDATORY | 24 | lifecycle.evolution | integ, run |
| ARK-REQ-0133 | SDK cycles use the bounded campaign model | MS §Child Products | MANDATORY | 24 | lifecycle.evolution | prop |
| ARK-REQ-0134 | Self-evolution pipeline followed; live core never directly rewritten | MS §Self-Evolution | MANDATORY | 23 | lifecycle.evolution | prop, sec |
| ARK-REQ-0135 | Self-Evolution DENY until Recovery Supervisor verified (Phase 22B) | MS §Self-Evolution | MANDATORY | 22B | control.policy | sec, prop |
| ARK-REQ-0136 | Precondition enforced by PDP, not convention | MS §Self-Evolution | MANDATORY | 22B | control.policy | sec |
| ARK-REQ-0137 | Restorable known-good snapshot recorded before every core promotion | MS §Self-Evolution | MANDATORY | 23 | lifecycle.recovery | prov, integ |
| ARK-REQ-0138 | Core promotion requires HUMAN GATE 2 | MS §Self-Evolution | MANDATORY | 23 | control.policy | human |
| ARK-REQ-0139 | Campaign declares objective, baseline and six budgets before execution | MS §Self-Evolution | MANDATORY | 23 | lifecycle.evolution | prov, prop |
| ARK-REQ-0140 | Campaign terminates in exactly one of four terminal states | MS §Self-Evolution | MANDATORY | 23 | lifecycle.evolution | prop |
| ARK-REQ-0141 | Rejected candidate never auto-generates a successor | MS §Self-Evolution | MANDATORY | 23 | lifecycle.evolution | prop |
| ARK-REQ-0142 | Campaigns never restarted to obtain a different terminal state | MS §Self-Evolution | MANDATORY | 23 | lifecycle.evolution | prop |

## Block 3 — Master Specification continued (ARK-REQ-0143 … 0180)

| ID | Requirement | Source | Class | Phase | Owner | Evidence |
|---|---|---|---|---|---|---|
| ARK-REQ-0143 | Four hardening rounds executed in order after first acceptance PASS | MS §Hardening | MANDATORY | 32 | acceptance.engine | integ |
| ARK-REQ-0144 | No change kept merely because AI suggested it | MS §Hardening | MANDATORY | 32 | acceptance.engine | prov |
| ARK-REQ-0145 | Round declares six budgets + no-progress threshold before execution | MS §Hardening | MANDATORY | 32 | acceptance.engine | prov, prop |
| ARK-REQ-0146 | Round terminates in exactly one of four terminal states | MS §Hardening | MANDATORY | 32 | acceptance.engine | prop |
| ARK-REQ-0147 | No round runs indefinitely; budget exhaustion terminates it | MS §Hardening | MANDATORY | 32 | acceptance.engine | prop |
| ARK-REQ-0148 | Rounds never restarted to obtain a different terminal state | MS §Hardening | MANDATORY | 32 | acceptance.engine | prop |
| ARK-REQ-0149 | Passport tracks required evidence per critical capability | MS §Passport | MANDATORY | 13 | acceptance.engine | prov |
| ARK-REQ-0150 | Completion percentage = verified-capability coverage vs register | MS §Passport | MANDATORY | 13 | acceptance.engine | integ |
| ARK-REQ-0151 | Schema change follows the nine-step migration sequence | MS §Database | MANDATORY | 20 | lifecycle.recovery | integ, persist |
| ARK-REQ-0152 | Migration APPLY to real/stable data is HUMAN GATE 6 | MS §Database | MANDATORY | 20 | control.policy | human |
| ARK-REQ-0153 | Backup proven by restore | MS §Database | MANDATORY | 5 | lifecycle.recovery | persist, integ |
| ARK-REQ-0154 | Independent deterministic Recovery Supervisor exists | MS §Database | MANDATORY | 22B | lifecycle.recovery | integ, chaos |
| ARK-REQ-0155 | ROLLBACK_STABLE is the sole direct stable mutation | MS §ROLLBACK_STABLE | MANDATORY | 22B | control.policy | prop, sec |
| ARK-REQ-0156 | Only Recovery Supervisor may invoke ROLLBACK_STABLE | MS §ROLLBACK_STABLE | MANDATORY | 22B | control.policy | sec, prop |
| ARK-REQ-0157 | Target must be a previously verified immutable revision | MS §ROLLBACK_STABLE | MANDATORY | 22B | lifecycle.recovery | prop, prov |
| ARK-REQ-0158 | Atomic revision/pointer switching preferred | MS §ROLLBACK_STABLE | MANDATORY | 22B | lifecycle.recovery | integ |
| ARK-REQ-0159 | No novel content, arbitrary edit, transformation, unverified target, evidence bypass, or AI invocation | MS §ROLLBACK_STABLE | MANDATORY | 22B | control.policy | sec, prop |
| ARK-REQ-0160 | Every rollback emits an auditable evidence artifact | MS §ROLLBACK_STABLE | MANDATORY | 22B | evidence.audit | prov |
| ARK-REQ-0161 | External projects statically inspected before execution | MS §Import | MANDATORY | 19 | engineering.import | sec, prop |
| ARK-REQ-0162 | Three rescue modes supported | MS §Import | MANDATORY | 19 | engineering.import | integ |
| ARK-REQ-0163 | Research uses official sources and never mutates production | MS §Import | MANDATORY | 21 | engineering.plugin | sec, prop |
| ARK-REQ-0164 | Plugins manifest/permission/version governed and cannot crash core | MS §Import | MANDATORY | 21 | engineering.plugin | chaos, sec |
| ARK-REQ-0165 | Plugin permissions use the 14 canonical operation classes | MS §Import | MANDATORY | 21 | control.policy | sec, arch |
| ARK-REQ-0166 | Unmappable plugin action is DENY | MS §Import | MANDATORY | 21 | control.policy | sec, unit |
| ARK-REQ-0167 | MCP-compatible adapters without internal MCP dependency | MS §Import | OPTIONAL | 21 | engineering.plugin | arch |
| ARK-REQ-0168 | Operations surfaces real-time state across the named dimensions | MS §Operations | MANDATORY | 25 | surfaces.operations | integ |
| ARK-REQ-0169 | Source Intelligence Export + AI Review Bundle with secret redaction | MS §Operations | MANDATORY | 25 | surfaces.operations | sec, integ |
| ARK-REQ-0170 | Computer-Use executes exclusively through Policy Authority/PDP/PEP | MS §Computer Use | MANDATORY | 25 | control.policy | sec, prop |
| ARK-REQ-0171 | Fourteen operation classes declared and resolved | MS §Computer Use | MANDATORY | 4 | control.policy | unit, sec |
| ARK-REQ-0172 | WRITE_STABLE_FILE is DENY for every actor | MS §Computer Use | MANDATORY | 4 | control.policy | prop, sec |
| ARK-REQ-0173 | INSTALL_SYSTEM_SOFTWARE and CHANGE_SYSTEM_CONFIGURATION never AUTO | MS §Computer Use | MANDATORY | 4 | control.policy | sec, unit |
| ARK-REQ-0174 | ACCESS_SECRET never AUTO outside pre-authorized scope | MS §Computer Use | MANDATORY | 4 | control.policy | sec |
| ARK-REQ-0175 | Unmapped action is DENY | MS §Computer Use | MANDATORY | 4 | control.policy | sec, prop |
| ARK-REQ-0176 | Command Center provides three skill modes and named areas | MS §Command Center | MANDATORY | 27 | surfaces.command | e2e |
| ARK-REQ-0177 | Every production-visible state comes from real backend state | MS §Command Center | MANDATORY | 27 | surfaces.command | e2e, integ |
| ARK-REQ-0178 | Capability phases deliver their own frontend increment | MS §Command Center | MANDATORY | 5 | surfaces.command | arch, e2e |
| ARK-REQ-0179 | Windows-first Tauri desktop with installer, diagnostics, bundled runtime | MS §Desktop | MANDATORY | 28 | surfaces.command | run |
| ARK-REQ-0180 | Offline continuation of local capabilities | MS §Desktop | CONDITIONAL | 28 | surfaces.command | integ |

## Block 4 — Master Specification tail (ARK-REQ-0181 … 0186)

| ID | Requirement | Source | Class | Phase | Owner | Evidence |
|---|---|---|---|---|---|---|
| ARK-REQ-0181 | Air-gapped signed offline update bundles | MS §Desktop | OPTIONAL | 29 | lifecycle.release | prov |
| ARK-REQ-0182 | Canonical phase order 0A…37 followed | MS §Phases | MANDATORY | 0A | control.architecture | doc, arch |
| ARK-REQ-0183 | Phase 0A + 0B form one acceptance package under HUMAN GATE 1 | MS §Phases | MANDATORY | 0B | acceptance.engine | human |
| ARK-REQ-0184 | IMPLEMENTED ≠ VERIFIED | MS §Final Success | MANDATORY | 13 | acceptance.engine | doc |
| ARK-REQ-0185 | Program-generation VERIFIED requires all eight applicable proofs | MS §Final Success | MANDATORY | 30 | acceptance.engine | run, persist, prov |
| ARK-REQ-0186 | Applicability of the eight proofs determined by register | MS §Final Success | MANDATORY | 13 | acceptance.engine | arch |

---

## Block 5 — Build Protocol (ARK-REQ-0200 … 0243)

| ID | Requirement | Source | Class | Phase | Owner | Evidence |
|---|---|---|---|---|---|---|
| ARK-REQ-0200 | Implementing actor is not the acceptance authority | BP §intro | MANDATORY | 0B | acceptance.engine | doc, human |
| ARK-REQ-0201 | Human operator is ultimate canonical acceptance authority | BP §intro | MANDATORY | 0B | acceptance.engine | human |
| ARK-REQ-0202 | Eight canonical HUMAN GATES defined and enforced | BP §Gates | MANDATORY | 4 | control.policy | sec, human |
| ARK-REQ-0203 | Normal phase reports/verdicts require no human approval | BP §Gates | MANDATORY | 2 | acceptance.engine | integ |
| ARK-REQ-0204 | Failed machine gate stops progression until repaired or escalated | BP §Gates | MANDATORY | 2 | acceptance.engine | prop, integ |
| ARK-REQ-0205 | Failed gate never bypassed, downgraded or re-scored by implementing actor | BP §Gates | MANDATORY | 2 | control.policy | sec, prop |
| ARK-REQ-0206 | Greenfield repository; no historical ARKALI source as foundation | BP §intro | MANDATORY | 1 | control.architecture | doc |
| ARK-REQ-0207 | Read all authoritative documents before implementation | BP §Mandatory | MANDATORY | 0A | control.specification | doc |
| ARK-REQ-0208 | Write actual files when filesystem access exists | BP §Mandatory | MANDATORY | 1 | control.architecture | doc |
| ARK-REQ-0209 | Run actual tests whenever execution is available | BP §Mandatory | MANDATORY | 2 | acceptance.engine | unit |
| ARK-REQ-0210 | Never claim execution that did not occur | BP §Mandatory | MANDATORY | 2 | acceptance.engine | prov |
| ARK-REQ-0211 | Never weaken requirements or acceptance to obtain PASS | BP §Mandatory | MANDATORY | 13 | control.policy | sec, mut |
| ARK-REQ-0212 | Never let AI-generated work directly overwrite stable | BP §Mandatory | MANDATORY | 12 | control.policy | prop, sec |
| ARK-REQ-0213 | Never create giant central factory/orchestration modules | BP §Mandatory | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0214 | Never create duplicate/shadow active definitions | BP §Mandatory | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0215 | Never make patch installers the normal development architecture | BP §Mandatory | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0216 | Never turn honest non-PASS states into PASS | BP §Mandatory | MANDATORY | 2 | acceptance.engine | prop, mut |
| ARK-REQ-0217 | Never originate a NOT_APPLICABLE classification | BP §Mandatory | MANDATORY | 13 | control.policy | sec, prop |
| ARK-REQ-0218 | Never use fake providers/metrics/health/jobs for production acceptance | BP §Mandatory | MANDATORY | 25 | acceptance.engine | integ, sec |
| ARK-REQ-0219 | Never fabricate or simulate an external-provider result | BP §Mandatory | MANDATORY | 9 | acceptance.engine | prov, sec |
| ARK-REQ-0220 | Repository evidence, not chat memory, is development state | BP §Mandatory | MANDATORY | 1 | control.architecture | doc |
| ARK-REQ-0221 | Six canonical docs subtrees maintained | BP §Repo state | MANDATORY | 0B | control.architecture | doc |
| ARK-REQ-0222 | Nine named canonical state files maintained | BP §Repo state | MANDATORY | 0B | control.architecture | doc |
| ARK-REQ-0223 | After context reset, continue from last proven checkpoint | BP §Repo state | MANDATORY | 1 | control.architecture | doc |
| ARK-REQ-0224 | Phase 0A produces the fifteen named architecture artifacts | BP §Phase 0A | MANDATORY | 0A | control.architecture | doc |
| ARK-REQ-0225 | Phase 0B produces the eleven named governance artifacts | BP §Phase 0B | MANDATORY | 0B | control.architecture | doc |
| ARK-REQ-0226 | Phase 0 submitted to human authority; never self-accepted | BP §Phase 0 | MANDATORY | 0B | acceptance.engine | human |
| ARK-REQ-0227 | Phase report contains all seventeen named fields | BP §Phase report | MANDATORY | 2 | acceptance.engine | doc, integ |
| ARK-REQ-0228 | Phase report cites ARK-REQ IDs closed | BP §Phase report | MANDATORY | 2 | acceptance.engine | integ |
| ARK-REQ-0229 | Vertical slice end-to-end for every production-visible capability | BP §Vertical slices | MANDATORY | 5 | control.architecture | arch, e2e |
| ARK-REQ-0230 | Contract-first definition before complex implementation | BP §Contract-first | MANDATORY | 2 | kernel.contracts | contract |
| ARK-REQ-0231 | Every AI engineering task bounded by the eight harness elements | BP §Harness | MANDATORY | 10 | engineering.agent | contract |
| ARK-REQ-0232 | Independent reviewer roles used; reviewer opinion advisory only | BP §Review | MANDATORY | 13 | acceptance.engine | prov |
| ARK-REQ-0233 | Progressively harder real products generated during build | BP §Real program | MANDATORY | 16 | engineering.factory | run |
| ARK-REQ-0234 | Golden Factory Acceptance requires real provider or local model | BP §Real program | MANDATORY | 30 | acceptance.engine | run, prov |
| ARK-REQ-0235 | Absent provider ⇒ BLOCKED/NOT_CONFIGURED, never PASS | BP §Real program | MANDATORY | 30 | acceptance.engine | prop |
| ARK-REQ-0236 | Acceptance contracts/authority defs/budgets/security gates are Protected Core | BP §Test integrity | MANDATORY | 4 | control.architecture | arch, sec |
| ARK-REQ-0237 | Machine verification runs autonomously without approval | BP §Test integrity | MANDATORY | 13 | acceptance.engine | integ |
| ARK-REQ-0238 | Failure protocol followed; no large regeneration without evidence | BP §Failure | MANDATORY | 14 | engineering.repair | integ, prov |
| ARK-REQ-0239 | Anti-loop fingerprinting and budget enforcement | BP §Anti-loop | MANDATORY | 14 | engineering.repair | prop |
| ARK-REQ-0240 | Deterministic transformers execute inside candidate lifecycle only | BP §Deterministic repair | MANDATORY | 14 | control.policy | prop, sec |
| ARK-REQ-0241 | Security never relaxed to make tests pass | BP §Security | MANDATORY | 4 | control.policy | sec, mut |
| ARK-REQ-0242 | Observability emits correlation IDs and evidence links | BP §Observability | MANDATORY | 2 | kernel.observability | integ |
| ARK-REQ-0243 | Continuity state updated before context becomes limiting | BP §Continuity | MANDATORY | 1 | control.architecture | doc |

---

## Block 6 — Verification & Delivery Contract (ARK-REQ-0300 … 0362)

| ID | Requirement | Source | Class | Phase | Owner | Evidence |
|---|---|---|---|---|---|---|
| ARK-REQ-0300 | Only two final states exist | VDC §Final states | MANDATORY | 37 | acceptance.engine | doc |
| ARK-REQ-0301 | Final PRODUCTION READY requires recorded human decision (GATE 7) | VDC §Acceptance authority | MANDATORY | 37 | acceptance.engine | human |
| ARK-REQ-0302 | Machine verdicts authoritative for non-gate phases | VDC §Acceptance authority | MANDATORY | 13 | acceptance.engine | integ |
| ARK-REQ-0303 | Listed weak signals are insufficient for VERIFIED | VDC §Fundamental rule | MANDATORY | 13 | acceptance.engine | doc |
| ARK-REQ-0304 | Canonical VERIFIED requires the nine listed elements | VDC §Fundamental rule | MANDATORY | 13 | acceptance.engine | integ, run |
| ARK-REQ-0305 | Every "applicable" resolves against the register | VDC §Applicability | MANDATORY | 13 | acceptance.engine | arch |
| ARK-REQ-0306 | No verdict rests on agent applicability judgment | VDC §Applicability | MANDATORY | 13 | control.policy | sec, prop |
| ARK-REQ-0307 | Unregistered applicability claims are FAIL, not NOT_APPLICABLE | VDC §Applicability | MANDATORY | 13 | acceptance.engine | unit |
| ARK-REQ-0308 | No convenience-based exceptions; five phrases carry no independent meaning | VDC §Conditional | MANDATORY | 13 | acceptance.engine | arch |
| ARK-REQ-0309 | Passport records the nineteen evidence kinds where applicable | VDC §Passport | MANDATORY | 13 | acceptance.engine | prov |
| ARK-REQ-0310 | Mandatory evidence missing ⇒ not VERIFIED | VDC §Passport | MANDATORY | 13 | acceptance.engine | prop |
| ARK-REQ-0311 | Five Golden products generated through the normal pipeline | VDC §Golden Suite | MANDATORY | 30 | engineering.factory | run |
| ARK-REQ-0312 | Full intent→release flow is real | VDC §Golden Suite | MANDATORY | 30 | engineering.factory | run, prov |
| ARK-REQ-0313 | Manual build registered as generated is prohibited | VDC §Golden Suite | MANDATORY | 30 | acceptance.engine | prov, sec |
| ARK-REQ-0314 | Hidden generalization domain introduced after factory exists | VDC §Generalization | MANDATORY | 31 | engineering.factory | run |
| ARK-REQ-0315 | No domain hard-coding in derivation | VDC §Generalization | MANDATORY | 31 | control.architecture | arch |
| ARK-REQ-0316 | At least two clean-state generations of one specification | VDC §Cross-generation | MANDATORY | 31 | engineering.factory | run |
| ARK-REQ-0317 | Generation runs bounded by a declared run budget | VDC §Cross-generation | MANDATORY | 31 | engineering.factory | prov, prop |
| ARK-REQ-0318 | All runs satisfy the same mandatory behavioral contracts | VDC §Cross-generation | MANDATORY | 31 | acceptance.engine | contract |
| ARK-REQ-0319 | Mocks permitted for low-level unit tests only | VDC §Real provider | MANDATORY | 30 | acceptance.engine | arch |
| ARK-REQ-0320 | L2 real execution evidence | VDC §Levels | MANDATORY | 30 | acceptance.engine | run |
| ARK-REQ-0321 | L3 clean-environment evidence from snapshot baseline | VDC §Levels | MANDATORY | 36 | lifecycle.release | run |
| ARK-REQ-0322 | Generated apps genuinely used across the named journey steps | VDC §User journeys | MANDATORY | 30 | acceptance.engine | e2e, persist |
| ARK-REQ-0323 | Browser automation checks console/network/dead controls/drift | VDC §User journeys | MANDATORY | 30 | acceptance.engine | e2e |
| ARK-REQ-0324 | Seven critical invariants property-tested | VDC §Mutation | MANDATORY | 31 | acceptance.engine | prop, mut |
| ARK-REQ-0325 | DENY not bypassable via six named paths | VDC §Mutation | MANDATORY | 31 | control.policy | sec, prop |
| ARK-REQ-0326 | Twelve chaos scenarios evidenced with containment/recovery | VDC §Chaos | MANDATORY | 31 | acceptance.engine | chaos |
| ARK-REQ-0327 | Durable restart yields RESUMED or RECOVERABLE; silent loss = FAIL | VDC §Durable restart | MANDATORY | 31 | execution.durable | chaos, prop |
| ARK-REQ-0328 | Executor proven to consume the canonical graph revision only | VDC §Workflow identity | MANDATORY | 17 | execution.workflow | integ, arch |
| ARK-REQ-0329 | Execution evidence for every node type and control construct | VDC §Workflow identity | MANDATORY | 17 | execution.workflow | integ |
| ARK-REQ-0330 | HUMAN APPROVAL evidenced as enforced policy stop | VDC §Workflow identity | MANDATORY | 17 | control.policy | sec, integ |
| ARK-REQ-0331 | UI node type without execution evidence is FAIL | VDC §Workflow identity | MANDATORY | 17 | acceptance.engine | integ |
| ARK-REQ-0332 | Derived-cache invalidation and stale-hash non-execution evidenced | VDC §Workflow identity | MANDATORY | 17 | execution.workflow | prop, integ |
| ARK-REQ-0333 | Golden Repair evidence records the six named items | VDC §Golden Repair | MANDATORY | 30 | engineering.repair | prov |
| ARK-REQ-0334 | Corpus modification to obtain PASS is a release blocker | VDC §Golden Repair | MANDATORY | 30 | acceptance.engine | sec, prov |
| ARK-REQ-0335 | Backup/restore proven by A→B→restore→verify; file copy = FAIL | VDC §Backup | MANDATORY | 5 | lifecycle.recovery | persist |
| ARK-REQ-0336 | Migration safety sequence evidenced | VDC §Migration | MANDATORY | 20 | lifecycle.recovery | integ, persist |
| ARK-REQ-0337 | Known data-loss risk blocks release | VDC §Migration | MANDATORY | 20 | acceptance.engine | prop |
| ARK-REQ-0338 | Recovery Supervisor end-to-end rollback evidenced | VDC §Recovery | MANDATORY | 22B | lifecycle.recovery | chaos, run |
| ARK-REQ-0339 | Rollback restores verified immutable revision without transformation | VDC §Recovery | MANDATORY | 22B | lifecycle.recovery | prop, prov |
| ARK-REQ-0340 | Security verification covers the eight named areas | VDC §Security | MANDATORY | 31 | acceptance.engine | sec |
| ARK-REQ-0341 | Per-tier escape tests: filesystem, network, process, credential, resource | VDC §Security | MANDATORY | 31 | control.isolation | sec |
| ARK-REQ-0342 | Negative-control test proves DENY when a property is unavailable | VDC §Security | MANDATORY | 31 | control.isolation | sec |
| ARK-REQ-0343 | ARKALI remains operational for still-satisfiable capabilities | VDC §Security | MANDATORY | 31 | control.isolation | chaos |
| ARK-REQ-0344 | Secret Vault boundary evidenced against all automated actors | VDC §Security | MANDATORY | 31 | control.policy | sec |
| ARK-REQ-0345 | Local-Only egress DENY evidenced on all six paths | VDC §Security | MANDATORY | 31 | control.policy | sec |
| ARK-REQ-0346 | Critical security finding blocks release | VDC §Security | MANDATORY | 37 | acceptance.engine | sec |
| ARK-REQ-0347 | Policy enforcement consistent across six paths incl. computer-use | VDC §Policy bypass | MANDATORY | 31 | control.policy | sec, prop |
| ARK-REQ-0348 | Import/Rescue seven acceptance conditions evidenced | VDC §Import | MANDATORY | 19 | engineering.import | sec, integ |
| ARK-REQ-0349 | Provenance recorded for critical generated/release artifacts | VDC §Provenance | MANDATORY | 6 | evidence.artifact | prov |
| ARK-REQ-0350 | Release manifest includes cryptographic hashes | VDC §Provenance | MANDATORY | 26 | lifecycle.release | prov |
| ARK-REQ-0351 | Eight architecture gates evaluate 0 against AUTHORITY_MAP.yaml | VDC §Architecture | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0352 | Identifier-only checker is insufficient | VDC §Architecture | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0353 | Each gate demonstrates detection on a violating fixture | VDC §Architecture | MANDATORY | 2 | control.architecture | arch |
| ARK-REQ-0354 | Failure domains isolated; one failure does not crash unrelated capabilities | VDC §Failure domain | MANDATORY | 31 | execution.scheduler | chaos |
| ARK-REQ-0355 | Operations shows real state; no fake telemetry | VDC §Operations | MANDATORY | 25 | surfaces.operations | integ, sec |
| ARK-REQ-0356 | Hardware/cost telemetry dimensions | VDC §Operations | CONDITIONAL | 25 | surfaces.operations | integ |
| ARK-REQ-0357 | Source export + AI Review Bundle verified incl. secret redaction | VDC §Source export | MANDATORY | 25 | surfaces.operations | sec, integ |
| ARK-REQ-0358 | Child product runs independently; full core not copied as runtime | VDC §Child evolution | MANDATORY | 24 | lifecycle.evolution | run, arch |
| ARK-REQ-0359 | Direct uncontrolled live-core mutation = FAIL | VDC §Self-Evolution | MANDATORY | 23 | control.policy | prop, sec |
| ARK-REQ-0360 | Evolution run without bounded campaign record = FAIL | VDC §Self-Evolution | MANDATORY | 23 | acceptance.engine | prop, prov |
| ARK-REQ-0361 | Post-Round-4 regression failure ⇒ ESCALATED, no new round | VDC §Hardening | MANDATORY | 35 | acceptance.engine | prop |
| ARK-REQ-0362 | Direct-AI benchmark comparison executed | VDC §Direct-AI | CONDITIONAL | 35 | acceptance.engine | run, prov |

## Block 7 — Verification & Delivery Contract tail (ARK-REQ-0363 … 0380)

| ID | Requirement | Source | Class | Phase | Owner | Evidence |
|---|---|---|---|---|---|---|
| ARK-REQ-0363 | Benchmark uses four states; NOT_CONFIGURED/EXTERNAL_UNAVAILABLE do not block release | VDC §Direct-AI | MANDATORY | 35 | acceptance.engine | prov |
| ARK-REQ-0364 | Never fabricate or simulate an external-provider PASS | VDC §Direct-AI | MANDATORY | 35 | acceptance.engine | sec, prov |
| ARK-REQ-0365 | Clean installation journey executed on the baseline | VDC §Clean install | MANDATORY | 36 | lifecycle.release | run |
| ARK-REQ-0366 | Baseline absent-tooling list enforced and recorded | VDC §Clean install | MANDATORY | 36 | lifecycle.release | run, prov |
| ARK-REQ-0367 | Baseline requirement applies to acceptance environment only | VDC §Clean install | MANDATORY | 36 | acceptance.engine | doc |
| ARK-REQ-0368 | Final delivery artifact set present | VDC §Final delivery | MANDATORY | 37 | lifecycle.release | prov |
| ARK-REQ-0369 | SBOM/dependency inventory | VDC §Final delivery | CONDITIONAL | 26 | lifecycle.release | prov |
| ARK-REQ-0370 | ARKALI_RELEASE_QUALITY_REPORT.md present | VDC §Final delivery | MANDATORY | 37 | lifecycle.release | doc |
| ARK-REQ-0371 | Fifteen release blockers enforced | VDC §Release blockers | MANDATORY | 37 | acceptance.engine | prop |
| ARK-REQ-0372 | Unbounded hardening round or evolution campaign blocks release | VDC §Release blockers | MANDATORY | 37 | acceptance.engine | prop |
| ARK-REQ-0373 | Mandatory requirement coverage = 100% of register MANDATORY entries | VDC §Production Ready | MANDATORY | 37 | acceptance.engine | integ |
| ARK-REQ-0374 | Mandatory evidence coverage = 100% | VDC §Production Ready | MANDATORY | 37 | acceptance.engine | integ |
| ARK-REQ-0375 | Architecture violations = 0 and authority conflicts = 0 | VDC §Production Ready | MANDATORY | 37 | control.architecture | arch |
| ARK-REQ-0376 | Critical security findings = 0; data-loss defects = 0 | VDC §Production Ready | MANDATORY | 37 | acceptance.engine | sec |
| ARK-REQ-0377 | Fake mandatory implementations = 0 | VDC §Production Ready | MANDATORY | 37 | acceptance.engine | sec, mut |
| ARK-REQ-0378 | Golden suite, generalization, Golden Repair, restart, backup, recovery, clean install all PASS | VDC §Production Ready | MANDATORY | 37 | acceptance.engine | run |
| ARK-REQ-0379 | Four rounds terminated in PASS or COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN | VDC §Production Ready | MANDATORY | 37 | acceptance.engine | prov |
| ARK-REQ-0380 | Otherwise state is RELEASE CANDIDATE — NOT PRODUCTION READY | VDC §Production Ready | MANDATORY | 37 | acceptance.engine | doc |

---

## Appendix A — CONDITIONAL applicability rules

Every rule is objective and machine-evaluable from recorded system state. No rule may be authored, amended or reinterpreted by an implementing actor.

| ID | Applicability rule (APPLICABLE when true) |
|---|---|
| ARK-REQ-0012 | `deployment.database_engine == "postgresql"` in any declared target profile |
| ARK-REQ-0060 | `job_type.supports_pause == true` in the job-type contract registry |
| ARK-REQ-0084 | `component.kind in {parser, security_boundary, ai_output_deserializer}` — outside this set, applicable only when the component is declared `fuzz_target: true` in its contract |
| ARK-REQ-0129 | `isolation.probe.local_ai_runtime_available == true` AND `hardware.probe.accelerator_present == true` |
| ARK-REQ-0130 | ARK-REQ-0129 applicable AND `dataset.verified_count > 0` |
| ARK-REQ-0180 | `capability.local_executable == true` in the Capability Graph for the capability under test |
| ARK-REQ-0356 | Per dimension: `hardware.probe.<dimension>_available == true` (GPU/VRAM) or `provider.registry.<id>.cost_reporting == true` (cost/token). Absence of a dimension is NOT_APPLICABLE only for that dimension |
| ARK-REQ-0362 | `provider.registry.configured_real_count >= 1` AND `acceptance.golden_product_suite == PASS` |
| ARK-REQ-0369 | `ecosystem.sbom_supported == true` for the target ecosystem (Python, Node and Rust all evaluate true) |

**OPTIONAL entries:** ARK-REQ-0167 (MCP adapters), ARK-REQ-0181 (air-gapped signed bundles). Optional entries do not contribute to mandatory coverage and never block release.

---

## Appendix B — Coverage summary

| Metric | Value |
|---|---|
| Total registered requirements | **311 entries** (highest ID allocated: ARK-REQ-0380) |
| MANDATORY | 300 |
| CONDITIONAL | 9 |
| OPTIONAL | 2 |
| Duplicate IDs | 0 |
| Entries with owner assigned | 311 (100%) |
| Entries with evidence definition | 311 (100%) |
| CONDITIONAL entries with objective rule in Appendix A | 9 (100%) |
| Requirements pending Phase 1+ implementation | 311 (100%) — Phase 0 produces no implementation |

Counts above were mechanically verified against this file, not asserted.

ID allocation is intentionally sparse (gaps at 0187–0199, 0244–0299) so future requirements can be added within their source block without renumbering. Gaps are not missing requirements.
