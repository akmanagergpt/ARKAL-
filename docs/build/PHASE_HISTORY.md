# PHASE HISTORY — ARKALI GENESIS v2

| # | Phase | Outcome | Commit | Notes |
|---|---|---|---|---|
| 1 | Repository bootstrap (pre-phase) | COMPLETE | `d8572dd` | canonical greenfield baseline: `.gitignore` + 4 canonical documents |
| 2 | Deterministic line endings (pre-phase) | COMPLETE | `4f9213f` | `.gitattributes`; LF stability proven by simulated fresh checkout |
| 3 | Canonical architecture repair (pre-phase) | COMPLETE | `079c925` | 9 BLOCKER + 16 HIGH findings repaired in the canonical set |
| 4 | **PHASE 0A — Canonical Architecture** | **CANDIDATE** | N/A — combined Phase 0 package | architecture package produced; no implementation. No Phase-0A-only commit exists: 0A and 0B were produced, reviewed and accepted as one package under HUMAN GATE 1. Package-level history is rows 6–9 |
| 5 | **PHASE 0B — Governance & Executable Contracts** | **CANDIDATE** | N/A — combined Phase 0 package | register, authority map, checker spec, ADRs. No Phase-0B-only commit exists — see row 4; package-level history is rows 6–9 |
| 6 | PHASE 0 acceptance package (candidate rev 1) | REJECTED by review | `85f3c1c` | HG1-01…HG1-04 |
| 7 | PHASE 0 acceptance package (candidate rev 2) | REJECTED by review | `5c6a28d` | HG1-05…HG1-09 |
| 8 | PHASE 0 acceptance package (candidate rev 3) | REJECTED by review | `63ab9a8` | HG1-10…HG1-12 |
| 9 | **PHASE 0 acceptance package (candidate rev 4)** | **ACCEPTED — HUMAN GATE 1** | `007ebf6` | record `HGR-001`; Phase 0A + 0B accepted as one package; 9 ADRs PROPOSED → ACCEPTED; Phase 1 unlocked |
| 10 | PHASE 1 — Repository Bootstrap (candidate rev 1) | NOT ACCEPTED | `0ad45a7` | F-0015 HIGH open; preserved unamended as the record of the defect |
| 11 | ERR-001 governance erratum + PHASE 1 repair | MACHINE-ACCEPTED | `1ae0835` | validator 12/12, backend suite 7/7, negative control 6/6. 5/5 Phase 1 ARK-REQs PASS. BLOCKER 0, HIGH 0. Phase 2 unlocked |
| 12 | **PHASE 2 — Foundation + Contracts + Executable Phase Gates** | **MACHINE-ACCEPTED** | `76edd26` | Verdict `PHASE_ACCEPTED_BY_MACHINE` from the real checker. 66 tests, 8 architecture gates (16 real edges), 19 negative/drift controls, mypy strict clean. 23/23 Phase 2 ARK-REQs PASS. Prior-phase reconciliation clean. **Phase 3 unlocked** |
| 16 | **Pre-Phase-5 acceptance integrity check** | **DEFECT FOUND — F-0024 HIGH** | pending | ARK-REQ-0111 was reported as discharged by Phase 4 without any implementation. C2 passed on the assertion. Phase 5 blocked; Phase 4 requires remediation and re-submission. Phase 4's verdict at `1ea79f3` preserved unamended |
| 15 | **PHASE 4 — Security + Governance + Isolation Backends** | **MACHINE-ACCEPTED — later found DEFECTIVE (F-0024)** | pending | Verdict `PHASE_ACCEPTED_BY_MACHINE`. C-07/08/09/10. One PDP, PEP contract, 14 operation classes, 5 TRUST tiers, 7 isolation properties, 7 backends really probed, Protected Core boundary, Secret Vault boundary, Local-Only. 242 new tests (785 total), 8 gates over 41 edges, mypy strict clean. 33/33 Phase 4 ARK-REQs accounted for. DEF-003 closed. F-0022 opened and closed. **Phase 5 unlocked** |
| 14 | **ERR-002 + ERR-003 — pre-Phase-4 human rulings** | GOVERNANCE REPAIR | pending | Both Phase 3 human-ruling items closed. ERR-002: Plugin `REMOVED` is terminal. ERR-003: architecture-budget measurement contract ratified; re-measurement exposed 3 real complexity violations including one in accepted Phase 2 code, all repaired by decomposition with no behavioural change and no GATE 8 request. All 9 numeric budgets now evaluated. 578 tests pass. Phase 3 remains MACHINE-ACCEPTED; Phase 4 remains UNLOCKED |
| 13 | **PHASE 3 — Formal State Machines + Capability Graph Schema** | **MACHINE-ACCEPTED** | `4321611` | Verdict `PHASE_ACCEPTED_BY_MACHINE`. 12 state machines across 10 owning contexts, C-13 schema, 444 new tests (532 total), 294 rejection-asserting controls, 8 gates over 32 real edges, mypy strict clean. 4/4 Phase 3 ARK-REQs PASS. Findings F-0018/F-0019/F-0020 opened at MEDIUM. **Phase 4 unlocked** |

## Pre-Phase-5 acceptance integrity check — F-0024

Instructed to derive the requirement Phase 4 recorded as DEFERRED from the register and its canonical source rather than from the phase report, and to determine whether the deferral was canonical (case A) or a MANDATORY requirement counted as satisfied without being met (case B).

**Result: case B.** The determination rests on four facts, none of which comes from the Phase 4 report:

1. `REQUIREMENT_REGISTER.md` assigns `ARK-REQ-0111` to Phase **4**, owner `acceptance.engine`, evidence `sec, integ`. The register is the sole denominator (governing rule 4); nothing in it defers the requirement.
2. `MS §Protected Core` states the obligation concretely — security review, adversarial review and full regression — and defers nothing.
3. The owner exists and is implemented: `acceptance.engine` has shipped since Phase 2. The requirement was implementable.
4. `backend/arkali/` contains **no** verification-profile mechanism. The work was not done.

The Phase 4 report's own justification — "DEFERRED … which depends on the candidate lifecycle" — contradicts the register's Phase column. That justification was authored by the implementing actor and had no canonical basis.

**How it passed.** C2 asks whether every mandatory requirement id appears in the report's discharged list. `ARK-REQ-0111` appeared, so C2 passed. C2 cannot ask whether the work happened; that is what the requirement's evidence keys are for, and no evidence record was produced for `sec` or `integ` against this id. The traceability map written in the same commit recorded the truth (`DEFERRED`) and its control asserted only that the deferred set had one member — never that a deferred requirement must be absent from the discharged list. The honest record and the false claim shipped together and no check compared them.

**Action taken.** F-0024 opened at HIGH in `OPEN_BLOCKERS.md`. Progression is now mechanically stopped: `run_phase_gate.py 4 5` returns `PHASE_BLOCKED`, failing condition `FINDINGS`. Phase 5 was **not** begun. Phase 4's machine verdict at `1ea79f3` is preserved unamended — re-scoring an accepted phase is the acceptance authority's decision, not the implementing actor's.

**Second defect found while recording the first.** F-0025: `_parse_open_findings` skips any row containing the substring `CLOSED`, so F-0024 initially failed to register because its text quoted a field name ending in `_closed`. A governance parser that hides a finding fails open. Worked around by rewording; the fix belongs with the F-0024 remediation because `acceptance.engine` is Protected Core.

**Cumulative count corrected.** The published figure of 65 verified requirements includes ARK-REQ-0111 and is overstated by one. The defensible figure is 64 pending remediation.

## Phase 4 report

**Phase ID / objective.** Phase 4 — the deterministic security and governance foundation: Policy Authority, the single PDP, the PEP enforcement contract, the fourteen operation classes, the TRUST tier and Isolation Backend property model with real host probes, the Protected Core boundary, the Secret Vault boundary and Local-Only policy.

**ARK-REQ IDs accounted for (33).** All Phase 4 MANDATORY entries, derived from the register's Phase column. Claim levels are explicit and machine-asserted in `test_requirement_traceability.py`: **CONTRACT** for 30, **PROBED** for 2 (0102, 0123), **DEFERRED** for 1 (0111). Nothing claims REAL EXECUTION, because no execution surface exists.

**Contracts.** C-07 policy decision request/response · C-08 operation class · C-09 secret reference · C-10 isolation property/backend descriptor. Derived from `CONTRACT_INVENTORY.md`, which agreed with the handoff's hint.

**One architectural constraint had to be resolved.** `SECURITY_ARCHITECTURE.md` §1 shows the PDP reading `control.isolation`. Both contexts are layer rank 1 and the authority map sets `allow_same_layer: false` with no sibling edge between them, so a direct import would be an architecture violation. The isolation posture is therefore resolved by `control.isolation` and **injected** as a fact on the request. The PDP stays pure; the layering rule is respected rather than quietly broken. Recorded in `DECISION_LOG.md`.

**Real host probes, truthfully reported.** Read-only, non-destructive; nothing was installed, elevated or enabled.

| Backend | State | Evidence |
|---|---|---|
| `job_object` | **PASS** | `kernel32!CreateJobObjectW` present |
| `restricted_token` | **PASS** | `advapi32!CreateRestrictedToken` present |
| `workspace_acl` | **PASS** | volume is NTFS |
| `vault_detach` | **PASS** | `crypt32!CryptProtectData` (DPAPI) present |
| `wfp_egress` | NOT_CONFIGURED | `fwpuclnt.dll` present, process not elevated |
| `windows_sandbox` | NOT_CONFIGURED | optional feature not enabled |
| `hyperv_container` | NOT_CONFIGURED | Hyper-V platform not enabled |

Consequently TRUST-0 and TRUST-1 are satisfiable here; **TRUST-2, TRUST-3 and TRUST-4 are UNSUPPORTED with execution DENY**, missing `NET_EGRESS_CONTROL` and `KERNEL_ISOLATION`. That is the canonical outcome, not a failure: a tier is never silently downgraded, and ARKALI stays operational for what remains satisfiable.

**What Phase 4 does not claim.** A probe proves a primitive is *obtainable*, not that a workload was confined — confinement evidence belongs to `execution.sandbox` in a later phase. No execution surface exists, so bypass resistance is verified at contract level only and `test_pep_and_bypass.py` asserts the absence of those surfaces so the claim cannot quietly become false.

**Two of the phase's own defects were caught by its own tests.** `ROLLBACK_STABLE` briefly resolved to ASK_USER for the canonical invoker; it is now DENY at every tier for every actor, because the Recovery Supervisor is Phase 22B and its canonical preconditions cannot be checked. `ACCESS_SECRET` was over-restricted to ASK_USER inside a pre-authorized scope where the canonical matrix grants AUTO at TRUST-0/1 — stricter than canonical is still a misreading of canonical.

**The budget gate caught two real violations during the phase.** `kernel.contracts` public surface reached 45>40 and `kernel.contracts.errors` fan-in reached 16>15. Both were repaired by decomposition, not waived: the security taxonomy moved to the contexts that raise it, and four copies of authority-map loading collapsed into one reader.

**Tests actually executed.** 774 passed, 11 skipped (785 collected; 242 added by Phase 4). 184 security tests. mypy strict clean over 88 source files. Structure validator 12/12 and negative control PASS. Phase graph 10/10 and negative control PASS. Phase 0 deliverables 16/16 and 11/11. Handoff validator PASS.

**Evidence created.** EV-0031 … EV-0036.

**Blockers.** None.

**Next exact action.** Begin Phase 5 — Persistence Foundation.

**Status.** **MACHINE-ACCEPTED.** Verdict `PHASE_ACCEPTED_BY_MACHINE` from `scripts/run_phase_gate.py 4 5`, exit 0.

## Pre-Phase-4 governance repair (ERR-002, ERR-003)

Applied after Phase 3 acceptance, on human ruling. Phase 3 was **not** reopened, redesigned or re-accepted, and `docs/acceptance/phase_3_report.json` is left unamended as the historical record of what was true at acceptance — including its then-accurate statement that F-0020 was unresolved. This section supersedes that statement; the report is evidence, not current state.

**ERR-002 — Plugin `REMOVED` is terminal.** `STATE_MACHINES.md` §6 now reads `any pre-REMOVED→QUARANTINED` with `Forbidden: REMOVED→any`, reusing §7's existing `any pre-X` idiom. 24 permanent controls assert both directions: the six legal quarantine paths survived, and no path out of `REMOVED` exists — including by direct attribute mutation. Reintroduction starts a new lifecycle instance.

**ERR-003 — budget measurement contract.** Ratified as data in `AUTHORITY_MAP.yaml` v1.0.0. The gate reads it; no validator holds a private formula. All **nine** declared numeric budgets are now evaluated, so `AWAITING_CANONICAL_FORMULA` is empty.

**What re-measurement cost.** Three functions exceeded the zero-threshold complexity budget under the newly ratified formula:

| Function | Measured | Budget | Outcome |
|---|---|---|---|
| `acceptance/checker.py:evaluate` | 17 | 12 | decomposed into `_run_checks`, `_blocking_human_gate`, `_is_blocked`, `_blocking_reason`, `_decide` |
| `gates/structure_gates.py:_per_module` | 18 | 12 | decomposed into `_module_size`, `_module_coupling`, `_function_shape` |
| `state_machine_spec.py:_pairs` | 13 | 12 | decomposed into `_split_chain`, `_link` |

One of these sat in **accepted Phase 2 code**. It was not grandfathered and no HUMAN GATE 8 exception was requested, because decomposition was straightforward — the ruling's stated condition for a Gate 8 request was not met. No behaviour changed: the full suite and every negative control pass unchanged, and the Phase Gate Checker still returns `PHASE_ACCEPTED_BY_MACHINE` for Phase 3. Max complexity is now 12 of 12; max orchestration depth 3 of 4 via `acceptance.engine → control.architecture → kernel.contracts`.

That an accepted phase carried an unapproved budget violation for the whole of Phase 3 is the point worth keeping: the budget was declared with a number and no way to measure it, so nothing could have caught it. A threshold without a formula is not a control.

## Phase 3 report

**Phase ID / objective.** Phase 3 — formal state machines for the twelve canonical entities with structurally impossible invalid transitions, and the C-13 Capability Graph schema with pre-activation `NOT_CONFIGURED` resolution.

**ARK-REQ IDs closed (4).** ARK-REQ-0043 (twelve entities use validated state machines), 0044 (invalid transitions structurally impossible), 0045 (capability nodes carry the specified attribute set), 0049 (pre-activation queries return `NOT_CONFIGURED`). The scope was derived from the register's Phase column mechanically, not from the handoff's hint; both agreed.

**ARK-REQ IDs explicitly NOT closed.** ARK-REQ-0046, 0047 and 0048 are owned by Phase 9B and are **not** claimed. Phase 3 delivers no capability resolution; claiming 0046 would require answering "Can I perform this?" from authorities that do not exist until Phases 4, 6 and 9.

**Where the twelve machines live.** Each machine is implemented inside the module root of the context `AUTHORITY_MAP.yaml` names as its authority — ten contexts across layer ranks 1 to 5. The shared primitive lives in `kernel.contracts` because `allow_same_layer: false` means a primitive in `control.architecture` could not be imported by `control.registry.project` or `control.registry.provider`; only rank 0 is reachable from every authority. There is no universal state-machine object.

**Structural impossibility (0044).** `StateMachineInstance` exposes no setter: `state` is a read-only property, `__setattr__` and `__delattr__` refuse every external write including to the private attribute, and `apply` validates before mutating via `object.__setattr__`. A rejected transition leaves state untouched. Rejections are typed — `UnknownState`, `ForbiddenTransition`, `TerminalStateEscape`, `GuardRejected`, `StateMutationBypass` — so a control asserts the reason, not merely that something raised.

**No shadow model.** The executable definitions are the implementation authority for their machines; `STATE_MACHINES.md` remains the canonical specification. They are reconciled on every run by a parser holding no machine data of its own (101 assertions across states, transitions, forbidden pairs, terminal sets, authority and physical location). The capability activation phase is derived from ARK-REQ-0048's Phase column. The plugin permission vocabulary and the provider-owned field list are injected from `AUTHORITY_MAP.yaml`.

**Public contracts.** C-13 (schema only). The node carries exactly the twelve fields of the canonical `capability_node` block, verified by parsing that block rather than by transcription. It has no `health`, `availability`, `cost` or `fallback_configuration` field, so provider state cannot be mirrored even by a willing caller; `runtime_requirements` is the one free-form field and is validated against the provider-owned vocabulary.

**Migrations.** None.

**Tests actually executed.** `python -m pytest -q` → 518 passed, 14 skipped, exit 0 (532 collected; 444 added by Phase 3). `mypy --strict` clean over 74 source files. Structure validator 12/12 and its negative control PASS. Phase graph 10/10 and its negative control PASS. Phase 0 deliverables 16/16 and 11/11. Handoff validator PASS. Full commands and exit codes are recorded in `docs/acceptance/phase_3_report.json`.

**Architecture checks.** 8 gates, all non-failing, over 32 real cross-context edges. The `architecture_budget_violation` gate was extended this phase from 3 to 7 of the 9 declared numeric budgets (finding F-0019).

**Duplicate / shadow check.** PASS at both declaration and code level.

**Security findings.** None. No executable surface, network, clock, randomness or secret handling.

**Fake-success scan.** PASS. No unimplemented capability is claimed. Pre-activation queries return `NOT_CONFIGURED`; activation raises `PrematureActivation` even when the current phase equals the activation phase, because Phase 9B owns resolution.

**Evidence created.** EV-0023 … EV-0027.

**Limitations.** Python 3.13 NOT_CONFIGURED (3.12.10 present); Rust/Cargo UNSUPPORTED; TypeScript/Vite, ruff and Python lockfile tooling NOT_CONFIGURED. Re-detected this phase, not copied. `max_cyclomatic_complexity_per_function` and `max_orchestration_depth` remain unevaluated pending a canonical measurement formula (F-0020).

**Blockers.** None.

**Next exact action.** Begin Phase 4 — Security + Governance + Isolation Backends.

**Status.** **MACHINE-ACCEPTED.** Verdict `PHASE_ACCEPTED_BY_MACHINE` from `scripts/run_phase_gate.py 3 4`, exit 0.

Four defects were opened during this phase, all MEDIUM and none blocking. F-0021 (negative controls that expire) was opened and closed within the phase: Phase 3 acceptance made a control's expected-wrong value correct, and the fix derives every mutation from live truth so no control can silently expire again. The other three: F-0018 (a canonical transition reading that leaves a machine with no terminal state), F-0019 (the budget gate claimed a wider scope than it evaluated), F-0020 (two budgets declared without a measurement formula). F-0019 was found by the implementing actor while designing against the budgets — the same "check narrower than its claim" family as F-0008, F-0013 and F-0016, now on its fourth recurrence.

## Phase 0 report

**Phase ID / objective.** Phase 0A+0B — produce the canonical architecture and governance contracts required before any implementation, resolving architectural ownership so no concern has two authorities.

**ARK-REQ IDs closed (18).** Register mechanism: 0033, 0034, 0035, 0036, 0039. Authority map / budgets / protected core: 0018, 0030, 0108, 0109. Golden Repair corpus **definition**: 0090, 0091. Phase model and single acceptance package: 0182, 0183. Repository state and Phase 0 deliverables: 0221, 0222, 0224, 0225. Contract inventory: 0230 (definition-level only — schemas are Phase 2).

**ARK-REQ IDs explicitly NOT closed, with state.** ARK-REQ-0187 and ARK-REQ-0188 (instantiated, content-hashed corpus) = **NOT_APPLICABLE at Phase 0B** — no accepted Golden Product exists as an injection target until Phase 30. All remaining 295 entries are open and owned by later phases.

**Correction record.** An earlier draft of this report claimed ARK-REQ-0090 and 0091 closed while `BUILD_STATE`, `OPEN_BLOCKERS` and `PHASE_0_AUDIT` recorded the corpus as unpopulated and deferred. That was a false closure of a mandatory requirement and an internal contradiction between Phase 0 artifacts. It is corrected here: the canonical Phase 0B obligation is the corpus *definition* (Build Protocol §Phase 0B), now delivered as `docs/canonical/GOLDEN_REPAIR_CORPUS_DEFINITION.md`; the instantiation obligation is separately registered as 0187/0188 against Phase 30. Logged as F-0005.

**Files created.** 20 Phase 0 artifacts (listed in `EVIDENCE_INDEX.md`). **Canonical source documents modified.** 0.

**Public contracts.** None implemented. 36 canonical contract families are **inventoried** in `docs/canonical/CONTRACT_INVENTORY.md` with owner, producer, consumers, category, planned schema location, versioning rule, compatibility class, evidence responsibility and implementation phase. Schema files are Phase 2 work; the inventory is Phase 0A work and is delivered.

**Migrations.** None.

**State-machine / capability changes.** Twelve state machines inventoried with states, transitions, forbidden transitions and authorities. Capability Graph schema defined; not populated.

**Tests actually executed.** Two mechanical validations, both run and recorded:
- `AUTHORITY_MAP.yaml` YAML parse + invariant check — exit 0. 31 contexts, 39 concerns, 14 operation classes, 8 gates, 0 duplicate concern authorities, all budgets numeric, `stable_mutation.direct_mutation_permitted_by == []`.
- `REQUIREMENT_REGISTER.md` structural count — exit 0. 313 entries, 313 unique, 0 duplicate IDs, 303 MANDATORY / 8 CONDITIONAL / 2 OPTIONAL, 0 CONDITIONAL entries missing an applicability rule, 0 orphan applicability rules.

No application test suite was executed: NOT_APPLICABLE — Phase 0 produces no implementation.

**Architecture checks.** NOT_TESTED. The eight gates require source code to analyse; they become executable in Phase 2.

**Duplicate / shadow check.** PASS at the declaration level — 0 duplicate concern authorities in `AUTHORITY_MAP.yaml`. Code-level detection is NOT_TESTED until Phase 2.

**Security findings.** None. Phase 0 introduces no executable surface.

**Fake-success scan.** PASS — no capability is claimed as implemented. Every unimplemented item is recorded as NOT_TESTED, NOT_CONFIGURED or NOT_APPLICABLE with a reason.

**Evidence created.** `EVIDENCE_INDEX.md` with two mechanical validation records.

**Second correction (HUMAN GATE 1, review 2).** Five further defects were found by independent review of the corrected package and are closed: F-0009 (phase-order deadlock 22B↔26 masked by a false-negative cycle check), F-0010 (impossible forward prerequisite C-03 + Phase 0B deliverable miscount 12 vs 11), F-0011 (stale denominators presented as current PASS basis in three artifacts). Two deterministic validators were added — `scripts/check_phase_graph.py` (9/9 PASS, with a negative control that reproduces the deadlock cycle) and `scripts/check_phase0_deliverables.py` (0A 16/16, 0B 11/11, counts parsed from the canonical lists).

**Limitations.** Phase 0 is documentation only. The architecture is unproven until code exists. Seven self-introduced defects are recorded in `KNOWN_FAILURES.md`: four caught by internal self-audit (F-0001…F-0004) and **three caught only by independent review** (F-0005 false closure of ARK-REQ-0090/0091, F-0006 five missing Phase 0A deliverables, F-0007 ARK-REQ-0012 misclassification). That the internal audit passed while three canonical traceability defects remained is itself the most significant limitation of this phase.

**Blockers.** None internal. External: HUMAN GATE 1.

**Next exact action.** Submit Phase 0A+0B as one package for HUMAN GATE 1. Do not begin Phase 1.

**Status.** **ACCEPTED.** HUMAN GATE 1 granted by the human acceptance authority on candidate `007ebf6e9275fa99d932022004440b1b869701d4`, following independent inspection of the actual artifacts and independent execution of the validation scripts. Recorded as `HGR-001` in `docs/acceptance/HUMAN_GATE_RECORDS.md`.

Phase 0 required four candidate revisions. Fourteen defects were recorded, ten of them found by independent review rather than self-audit — the record of that is retained in full and is not superseded by acceptance.
