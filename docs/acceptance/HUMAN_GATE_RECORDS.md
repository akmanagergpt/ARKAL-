# HUMAN GATE RECORDS — ARKALI GENESIS v2

Authoritative ledger of human acceptance decisions. The human operator is the ultimate canonical acceptance authority (Build Protocol §Canonical HUMAN GATES). Machine verdicts never appear in this ledger — only recorded human decisions do.

Records are **append-only**. A decision is never edited or deleted; a superseding decision is added as a new record referencing the earlier one.

---

## HGR-001 — HUMAN GATE 1: PHASE 0 canonical architecture acceptance

| Field | Value |
|---|---|
| **Gate** | HUMAN_GATE_1 — PHASE 0 canonical architecture acceptance (0A + 0B as one package) |
| **Decision** | **ACCEPTED** |
| **Accepted candidate commit** | `007ebf6e9275fa99d932022004440b1b869701d4` |
| **Canonical source set at acceptance** | `079c925996034017855fb9d1f1fa532077d7e86d` (unmodified by Phase 0) |
| **Deciding authority** | human operator (canonical acceptance authority) |
| **Basis of decision** | independent inspection of the actual Phase 0A + 0B artifacts and validation scripts, with the validators independently executed by the reviewer |
| **Scope accepted** | Phase 0A (16/16 canonical deliverables) and Phase 0B (11/11 canonical deliverables) as one acceptance package |
| **Effect** | Phase 0A = ACCEPTED · Phase 0B = ACCEPTED · 9 Phase 0 ADRs PROPOSED → ACCEPTED · Phase 1 unlocked |
| **Not granted by this record** | no other gate. Gates 2–8 remain outstanding and are unaffected |

### Evidence set referenced by this decision

| Ref | Evidence | Result at acceptance |
|---|---|---|
| EV-0001 | `AUTHORITY_MAP.yaml` machine-readable and internally consistent | exit 0 · 0 duplicate concern authorities |
| EV-0002 | `REQUIREMENT_REGISTER.md` structural integrity | exit 0 · 313 entries · 303/8/2 · 0 duplicates |
| EV-0004 | Phase dependency graph executable, parsed from authoritative documents | exit 0 · 10/10 PASS |
| EV-0004N | Drift negative control | exit 0 · defective input rejected, cycle reported, repo unmodified |
| EV-0005 | Phase 0A/0B deliverable reconciliation, counts derived from canonical lists | exit 0 · 0A 16/16 · 0B 11/11 |

### Review history preserved

This candidate was accepted at the fourth revision. Three prior candidates were rejected by independent review and are preserved unamended:

| Commit | Outcome |
|---|---|
| `85f3c1c` | rejected — HG1-01…HG1-04 (missing contract inventory, false closure of ARK-REQ-0090/0091, ARK-REQ-0012 misclassification, four absent 0A deliverables) |
| `5c6a28d` | rejected — HG1-05…HG1-09 (phase-order deadlock, forward prerequisite, stale counts, deliverable miscount, stale denominator) |
| `63ab9a8` | rejected — HG1-10…HG1-12 (residual stale values, shadow-model validator, inexact edge-class terminology) |
| `007ebf6` | **ACCEPTED** |

Fourteen defects are recorded in `docs/build/KNOWN_FAILURES.md`; ten were found by independent review and four by self-audit. That evidence is retained in full and is not superseded by this acceptance.

### Standing conditions carried past this gate

Acceptance of Phase 0 does not close the following, which remain open and tracked:

- 14 MEDIUM and 9 LOW findings (`OPEN_BLOCKERS.md`).
- M-P0-1 — requirement-register exhaustiveness is by construction, not mechanical extraction; a normative-statement extractor reconciles it in Phase 2.
- M-P0-2 — the architecture is a declaration until the Phase 2 gates execute against real code.
- 0 of 303 MANDATORY requirements are verified. Phase 0 established the denominator; it verified no capability.

---

## HGR-002 — HUMAN GATE 4: Phase 19 candidate (Import / Reverse Engineering / Rescue, C-29)

| Field | Value |
|---|---|
| **Gate** | HUMAN_GATE_4 — weakening or change of a security boundary, sandbox tier or protected-core policy |
| **Decision** | **ACCEPTED** |
| **Scope of this decision** | Narrow — the Phase 19 candidate identified below only. See the two "Scope" rows near the bottom of this record before treating this as satisfying any other phase's `HUMAN_GATE_4` obligation |
| **Deciding authority** | human operator (canonical acceptance authority) |
| **Candidate identity bound by this decision** | HEAD `ef5cb3bea46a994609e729a40570f048021c5841` (branch `main`); evidence package digest `sha256:6e41dd0dbb84df2403d6ebea98b6d2875871cd0806c5c6bb699d4cd0a457a727` over `docs/acceptance/phase_19_report.json` + `phase_19_traceability.json` (`acceptance.rescoring_authorization.evidence_package_digest`, the identical binding mechanism GOV-001's RSA rows use — computed here for audit precision even though `checker.check_human_gate` does not itself consult it) |
| **Basis of decision** | Independent mechanical re-verification, run fresh against this exact HEAD immediately before this record was written, all confirmed true: (1) HEAD/branch as stated; (2) working tree clean; (3) `check_handoff.py` → PASS, 0 drift; (4) `GovernanceState.current_work_phase()` → `19`; (5) candidate identity unchanged since the gate ran — `git diff 09430a2..HEAD` touches only `ARKALI_HANDOFF.md` and `docs/build/BUILD_STATE.md`, zero diff on either evidence file; (6) `python scripts/run_phase_gate.py 19 20`, re-run fresh, returns verdict `AWAITING_HUMAN_GATE` with `HUMAN_GATE: HUMAN_GATE_4 required and not recorded` as the **only** non-PASS/non-NOT_APPLICABLE check — C1–C6, EXTERNAL_RESULT, PROTECTED_CORE (normal profile), RESCORING (NOT_APPLICABLE), FINDINGS and PREREQ (3/3) all PASS; (7) `open_stopping_findings` is empty; (8) all 8 architecture gates PASS over 169 edges, all 9 budgets; (9) `git diff --stat 63cdaa6..HEAD -- backend/arkali/control/` and `-- backend/arkali/acceptance/` are both empty — neither Protected Core directory was touched anywhere in this candidate; (10) the only `AUTHORITY_MAP.yaml` change in the whole candidate is one new `allowed_sibling_edges` entry (`engineering.import → engineering.codeintel`) — `isolation:`, `stable_mutation:`, `human_gates:` and every operation-class rule are byte-identical to Phase 18's accepted state; (11) `TierAssignment.tier`/`.assigned_by` are single-member `Literal` types (re-verified: `TestTierAssignmentIsFixedByType`, all pass) — imported/untrusted projects are fixed at TRUST-3 and cannot be assigned any other tier or assigner; (12) the TRUST-3 execution gate checks isolation before approval and denies with no available backend, a real un-doubled probe of this host returns DENY, an automated actor cannot record its own approval, and a rejected or stale-hash-bound approval never permits (re-verified: the full `test_import_execution_gate.py` suite, all pass); no execution capability exists anywhere in the shipping source (re-verified: `test_step_0_no_execution_capability_exists_in_the_shipping_source`) |
| **Rationale** | The reviewed Phase 19 C-29 Import / Reverse Engineering / Rescue implementation is authorized because it preserves, rather than weakens, ARKALI's existing security and authority boundaries. Imported projects remain untrusted; source preservation and working-copy confinement remain enforced; direct Stable mutation is not granted; Protected Core authority is not granted; imported content cannot self-verify, self-promote, or become canonical merely by import; execution remains subject to the existing isolation and human-approval authorities (both authorities reused unmodified — `control.isolation.IsolationAuthority`, `control.policy.WorkflowApprovalGate` — no file under `backend/arkali/control/` was created or modified); unsupported isolation continues to fail closed (DENY), proven against this real host rather than assumed |
| **Scope — this grant authorizes** | Acceptance evaluation of the Phase 19 candidate at the exact HEAD and evidence-package digest named above, and nothing beyond that |
| **Scope — this grant explicitly does NOT authorize** | Weakening TRUST semantics; reducing sandbox/isolation strength; weakening `control.policy`; weakening Protected Core rules; bypassing HUMAN APPROVAL; adding direct Stable mutation rights; granting imported projects canonical authority; any future Phase 19 revision (a changed candidate has a different evidence-package digest and is not covered); Phase 20 work; any unrelated security-policy change |
| **KNOWN MECHANISM GAP — READ BEFORE TREATING PHASE 21 AS GATED** | `docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md` maps **both** Phase 19 and Phase 21 to `HUMAN_GATE_4`. `GovernanceState.accepted_human_gates` (`backend/arkali/acceptance/governance_state.py`) is a flat `frozenset[str]` keyed only by gate ID — there is **no per-phase binding** for a `HUMAN_GATE` record the way `RESCORING` authorizations bind to an evidence-package digest. Recording this decision in the canonical `**Decision** | **ACCEPTED**` format that `GovernanceState._parse_human_gates` reads will, as a mechanical side effect neither this record nor the checker can prevent, also satisfy Phase 21's own future `HUMAN_GATE_4` check the moment a session reaches it — with **no fresh human review at that time** unless a human deliberately provides one. **This record's own scope section above states plainly that no such authorization is intended.** A session that reaches Phase 21 MUST treat this gap as still requiring an independent human decision on Phase 21's own merits, MUST NOT cite this record (HGR-002) as satisfying Phase 21's gate, and SHOULD surface this exact gap to the human acceptance authority again before proceeding, regardless of what the mechanical `check_human_gate` result says. Closing this gap properly (a per-phase-scoped human-gate binding, mirroring `rescoring_authorization.py`'s digest binding) is a canonical-governance change this record does not make and is not authorized to make |

---

## HGR-003 — HUMAN GATE 6: Phase 20 candidate (Database Migration Safety + Full Backup/Recovery)

| Field | Value |
|---|---|
| **Gate** | HUMAN_GATE_6 — APPLY of a migration to real or stable data |
| **Decision** | **ACCEPTED** |
| **Scope of this decision** | Narrow — `PHASE_ACCEPTANCE` of the frozen Phase 20 candidate identified below only. This is **not** a `RUNTIME_OPERATION` grant; it does not by itself authorize any future `APPLY_MIGRATION` call. See the "Scope" rows below |
| **Deciding authority** | human operator (canonical acceptance authority) |
| **Candidate identity bound by this decision** | Candidate evidence commit `73a968f58215dcc35abe04aa9f2e0515b612b1e5`; evidence package digest `sha256:b94d28bb86e515e36f0106f3620d72ddcb672771f9e1ab7ee1ba8f2f1e202c2c` over `docs/acceptance/phase_20_report.json` + `phase_20_traceability.json` (`acceptance.rescoring_authorization.evidence_package_digest`, the identical binding mechanism GOV-001's RSA rows and HGR-002-SCOPED already use) |
| **Basis of decision** | Independent mechanical re-verification, run fresh against HEAD `a6cb3f51eb5faf2f2e04c7676ab510ba6a26bf09` immediately before this record was written, all confirmed true: (1) HEAD/branch/clean tree as stated; (2) `check_handoff.py` → PASS, 0 drift; (3) `GovernanceState.current_work_phase()` → `20`; (4) `git diff 73a968f..HEAD -- docs/acceptance/phase_20_report.json docs/acceptance/phase_20_traceability.json` is empty — the frozen candidate's evidence is byte-identical to the commit named above; (5) `acceptance.rescoring_authorization.evidence_package_digest(repo, "20")` recomputes to the exact digest named above; (6) the complete governance suite (`pytest backend/tests/governance -q --ignore=test_local_automation.py`) returns 399 passed, 0 failed; (7) all 8 architecture gates PASS, 0 findings/violations, over 183 cross-context edges; (8) `GovernanceState.open_stopping_findings` is empty (0 open BLOCKER/HIGH); (9) `python scripts/run_phase_gate.py 20 21`, re-run fresh immediately before this record, returns verdict `AWAITING_HUMAN_GATE` with `HUMAN_GATE: HUMAN_GATE_6 required and not recorded for this exact evidence package` as the **only** non-PASS/non-NOT_APPLICABLE check — C1–C6, EXTERNAL_RESULT, PROTECTED_CORE (COMPLETE profile, all three categories satisfied), RESCORING (NOT_APPLICABLE, first submission), DATA_LOSS_RISK, FINDINGS and PREREQ (2/2) all PASS |
| **Rationale** | The human acceptance authority reviewed the Phase 20 Database Migration Safety + Full Backup/Recovery candidate and its evidence package (`phase_20_report.json`, `phase_20_traceability.json`, `docs/contracts/migration_safety.md`) and grants `HUMAN_GATE_6` for phase acceptance of this exact, frozen candidate. The nine-step sequence (Impact, Backup, Dry Run, Integrity, Candidate Migration, Application Tests, Apply, Verify, Rollback Point) composes Phase 5's `RecoveryService`/`BackupRestore`, Phase 4's PDP and Phase 19's `WorkflowApprovalGate` unmodified; the data-loss-risk analyser is re-derived independently on every gate evaluation rather than trusted from a prior claim; `HUMAN_GATE_SCOPE_GAP` remediation (HGR's scoped tables below) is confirmed active, so this grant cannot leak to any other phase or to any runtime `APPLY_MIGRATION` operation |
| **Scope — this grant authorizes** | `PHASE_ACCEPTANCE` evaluation of the Phase 20 candidate at the exact candidate commit and evidence-package digest named above, and nothing beyond that |
| **Scope — this grant explicitly does NOT authorize** | A global `HUMAN_GATE_6` grant; authorization for Phase 21, Phase 22B or any other phase; authorization for a modified Phase 20 candidate (a changed evidence package has a different digest and is not covered); authorization for any real `APPLY_MIGRATION` operation against any migration target/revision — that requires its own `RUNTIME_OPERATION`-scoped grant bound to the exact target identity and revision identity, which this record does not create; standing permission to apply future migrations to real or Stable data; weakening, bypassing, broadening or reinterpreting any security boundary, PDP rule, or Protected Core policy |
| **No runtime-operation grant created** | The operation-scope authorization table below (`gate + operation + target + revision`) is left exactly as it was — empty. This record adds only a `PHASE_ACCEPTANCE`-scope row |

---

## HGR-004 — HUMAN GATE 4: Phase 21 candidate (Plugins + Integrations + Research, C-30)

| Field | Value |
|---|---|
| **Gate** | HUMAN_GATE_4 — weakening or change of a security boundary, sandbox tier or protected-core policy |
| **Decision** | **ACCEPTED** |
| **Scope of this decision** | Narrow — `PHASE_ACCEPTANCE` of the frozen Phase 21 candidate identified below only. This is **not** a global `HUMAN_GATE_4` grant, does **not** reuse or extend HGR-002 (Phase 19's own, separate `HUMAN_GATE_4` decision), and creates no `RUNTIME_OPERATION`-scope grant of any kind. See the "Scope" rows below |
| **Deciding authority** | human operator (canonical acceptance authority) |
| **Candidate identity bound by this decision** | Candidate evidence commit `34b841b0612742e94420e04b6ee8207238ff416c`; evidence package digest `sha256:ca469acfc99fa53d85e6389158371ef3c55e5308d437a2b33132e1405468f0f7` over `docs/acceptance/phase_21_report.json` + `phase_21_traceability.json` (`acceptance.rescoring_authorization.evidence_package_digest`, the identical binding mechanism GOV-001's RSA rows, HGR-002-SCOPED and HGR-003-SCOPED already use) |
| **Basis of decision** | Independent mechanical re-verification, run fresh against HEAD `baf23eebc29e22650b0528b9e1d85bfb2958cc0c` immediately before this record was written, all confirmed true: (1) HEAD/branch `main`/clean tree as stated; (2) `check_handoff.py` → PASS, 0 drift; (3) `GovernanceState.current_work_phase()` → `21`; (4) `git diff 34b841b..HEAD -- docs/acceptance/phase_21_report.json docs/acceptance/phase_21_traceability.json` is empty — the frozen candidate's evidence is byte-identical to the commit named above (only `ARKALI_HANDOFF.md` changed afterward, via the §12 refresh + marker-advance commits, adding no production code and no cross-context edge); (5) `acceptance.rescoring_authorization.evidence_package_digest(repo, "21")` recomputes to the exact digest named above; (6) `RequirementRegister.for_phase("21")` returns the same six entries (five MANDATORY, one OPTIONAL) as the frozen candidate's own denominator; (7) `python scripts/run_phase_gate.py 21 22`, re-run fresh immediately before this record, returns verdict `AWAITING_HUMAN_GATE` with `HUMAN_GATE: HUMAN_GATE_4 required and not recorded for this exact evidence package` as the **only** non-PASS/non-NOT_APPLICABLE check — C1–C6, EXTERNAL_RESULT (11 recorded runs), **PROTECTED_CORE COMPLETE** (`control.policy` touched by `pdp.py`'s two new additive methods; security review 251, adversarial review 802, full regression 2903, all exit 0), RESCORING (NOT_APPLICABLE, first submission), DATA_LOSS_RISK, FINDINGS and PREREQ (2/2, Phases 4 and 9) all PASS; (8) `GovernanceState.open_stopping_findings` is empty (0 open BLOCKER/HIGH); (9) all 8 architecture gates PASS, 0 violations, over 188 cross-context edges, all 9 budgets; (10) mechanically proven against the live `HUMAN_GATE_RECORDS.md` (this document, before this record was appended): `human_gate_authorization._find_phase_gate_grant("HUMAN_GATE_4", "19", <phase-19-digest>)` resolves to HGR-002-SCOPED, the identical lookup for `("HUMAN_GATE_4", "21", <phase-19-digest>)` resolves to `None`, an arbitrary wrong digest for phase 21 resolves to `None`, the real phase-21 digest itself had no grant before this record, and `HUMAN_GATE_4` is not in `SINGLETON_GATES` (`{HUMAN_GATE_1, HUMAN_GATE_7}`) so no flat `accepted_human_gates` path can satisfy it — HGR-002 does not, and structurally cannot, leak into this decision |
| **Rationale** | The reviewed Phase 21 candidate implements the canonically-scoped Plugins + Integrations + Research capability (C-30) while preserving the existing security architecture. It reuses, unmodified, the canonical `PluginLifecycle` state machine, the existing `OperationClassVocabulary`, the sole PDP/PEP, `WorkflowApprovalGate` and `IsolationAuthority` — no second policy authority, operation-class vocabulary, isolation authority, approval mechanism or state machine is introduced (`STATE_MACHINES.md` stays at 12). The change does not authorize a standing weakening of any security boundary: TRUST-4 remains fail-closed on this real, unconfigured host (`KERNEL_ISOLATION`/`DISPOSABILITY` `UNSUPPORTED`, proven by a real, un-doubled backend probe) and requires a fresh, non-reusable human approval bound to each individual execution attempt rather than once per assignment; an unmappable plugin action resolves to a real, audited `DENY`, never a silent pass-through or an uncaught crash; Research's own network egress is proven, against the real PDP, to honestly DENY under Local-Only. `control.policy`'s two new methods (`decide_or_deny_unmapped`, `decide_network_egress`) are strictly additive — `decide()`'s own raising behaviour for every existing caller is unchanged, re-verified by the full pre-existing PDP test suite |
| **Scope — this grant authorizes** | `PHASE_ACCEPTANCE` evaluation of the Phase 21 candidate at the exact candidate commit and evidence-package digest named above, and nothing beyond that |
| **Scope — this grant explicitly does NOT authorize** | A global `HUMAN_GATE_4` grant; authorization for Phase 19 (HGR-002 remains the sole, separate authority for that decision), Phase 20, Phase 22, Phase 22B or any other phase; authorization for a modified Phase 21 candidate (a changed evidence package has a different digest and is not covered); any `RUNTIME_OPERATION`-scope grant of any kind — none is created by this record; any future plugin execution against real content; any future security-boundary, sandbox-tier or Protected Core policy change beyond what this exact candidate already contains; any Stable mutation; any architecture-budget exception (`HUMAN_GATE_8`); any provider or network privilege; standing authorization for any future `HUMAN_GATE_4` subject |
| **No runtime-operation grant created** | The operation-scope authorization table below (`gate + operation + target + revision`) is left exactly as it was — empty. This record adds only a `PHASE_ACCEPTANCE`-scope row |

---

## HGR-005 — HUMAN GATE 2: Phase 23 candidate (Self-Evolution / ARKALI Stable Core promotion, C-33)

| Field | Value |
|---|---|
| **Gate** | HUMAN_GATE_2 — ARKALI Stable Core promotion |
| **Decision** | **ACCEPTED** |
| **Scope of this decision** | Narrow — `PHASE_ACCEPTANCE` of the frozen Phase 23 candidate identified below only. This is **not** a global `HUMAN_GATE_2` grant, is **not** a `RUNTIME_OPERATION`-scope grant, does not authorize any future self-evolution campaign, any future Stable promotion, Phase 24 or any other phase, any changed Phase 23 evidence package, the runtime `CORE_PROMOTION` operation, or any other Protected Core change. See the "Scope" rows below |
| **Deciding authority** | human operator (canonical acceptance authority) |
| **Candidate identity bound by this decision** | Candidate freeze commit `54f9e8b0272deb1a1efd58267b2f4a54c2d02cf6`; evidence package digest `sha256:3ad6f5fe20c8279ce62d2f15951a108099bb196b0fc4f53c8ae10e1f1eb5c00e` over `docs/acceptance/phase_23_report.json` + `phase_23_traceability.json` (`acceptance.rescoring_authorization.evidence_package_digest`, the identical binding mechanism GOV-001's RSA rows and HGR-002-SCOPED/HGR-003-SCOPED/HGR-004-SCOPED already use) |
| **Basis of decision** | Independent mechanical re-verification, run fresh against HEAD `b87a0d48427fde5dc28d07b6f2df63084796dba1` immediately before this record was written, all confirmed true: (1) HEAD/branch `main`/clean working tree as stated; (2) `check_handoff.py` → PASS, 0 drift, on the full check set; (3) `GovernanceState.current_work_phase()` → `23`; (4) `git diff 54f9e8b..HEAD -- docs/acceptance/phase_23_report.json docs/acceptance/phase_23_traceability.json` is empty — the frozen candidate's evidence is byte-identical to the freeze commit named above; only `ARKALI_HANDOFF.md` and `docs/build/BUILD_STATE.md` changed afterward, via the §12 refresh + marker-advance commits, adding no production code and no cross-context edge; (5) `acceptance.rescoring_authorization.evidence_package_digest(repo, "23")` recomputes, independently, to the exact digest named above; (6) `RequirementRegister.for_phase("23")` returns 9 MANDATORY requirements (ARK-REQ-0134, 0137, 0138, 0139, 0140, 0141, 0142, 0359, 0360), matching the frozen candidate's own denominator; (7) `python scripts/run_phase_gate.py 23 24`, re-run fresh immediately before this record, returns verdict `AWAITING_HUMAN_GATE` with `HUMAN_GATE: HUMAN_GATE_2 required and not recorded for this exact evidence package (digest=sha256:3ad6f5fe...)` as the **only** non-PASS/non-NOT_APPLICABLE check — C1–C6, EXTERNAL_RESULT (9 recorded runs), **PROTECTED_CORE COMPLETE** (`acceptance.engine` touched via `campaign_record_shape.py`; security review 254, adversarial review 807, full regression 3078, all exit 0), RESCORING (NOT_APPLICABLE, first submission), DATA_LOSS_RISK, FINDINGS and PREREQ (3/3, Phases 13, 16, 22B) all PASS; all 8 architecture gates PASS, 0 violations, over 202 cross-context edges, all 9 numeric budgets; (8) `GovernanceState.open_stopping_findings` is empty (0 open BLOCKER/HIGH); (9) mechanically proven against the live `HUMAN_GATE_RECORDS.md` (this document, before this record was appended): `human_gate_authorization._find_phase_gate_grant("HUMAN_GATE_2", "23", <phase-23-digest>)` resolves to `None`, and `HUMAN_GATE_2` is not in `SINGLETON_GATES` (`{HUMAN_GATE_1, HUMAN_GATE_7}`), so no flat `accepted_human_gates` path could ever satisfy it — no prior HGR (001–004) leaks into this decision; (10) `git diff --stat` over the full Phase 23 candidate (`4da97b1^..54f9e8b`) touches no file under `backend/arkali/control/policy/`, `backend/arkali/lifecycle/release/stable_pointer.py`, `backend/arkali/lifecycle/recovery/recovery_supervisor.py`, `backend/arkali/acceptance/human_gate_authorization.py`, `backend/arkali/acceptance/governance_gates.py`, or `AUTHORITY_MAP.yaml` — the sole PDP/PEP, the sole `StableRevisionPointer.promote`, the Phase 22B Recovery Supervisor, and the scoped-grant mechanism itself are all reused completely unmodified; the one line touching `core_upgrade_state_machine.py` adds an unused-elsewhere type import only, no guard or transition changed; (11) `authorize_promotion` (`core_upgrade_orchestrator.py`) populates `human_gate_2_recorded` only from a real `GovernanceState.operation_grant(GATE_2, "CORE_PROMOTION", candidate_manifest_ref, target_revision_id)` lookup against the separate `RUNTIME_OPERATION`-scope table — never from this `PHASE_ACCEPTANCE`-scope grant, never from a caller-asserted boolean — re-verified live via `backend/tests/lifecycle/test_core_promotion_gate_scope.py` (5/5 pass), which also proves a barred automated issuer cannot manufacture its own grant (self-approval refused, ARK-REQ-0359) and a grant for a different candidate manifest or a different gate does not leak; (12) `backend/tests/structural/test_self_evolution_no_direct_mutation.py` (5/5 pass) proves by AST scan that no `lifecycle.evolution` module other than `core_promotion.py` can call `.promote(`/`.rollback_to(`, and `core_promotion.py` itself never calls `rollback_to`; (13) `CoreUpgrade`'s own guards (`recovery_supervisor_guard`, `gate_2_guard`, `rollback_invoker_guard`) require, respectively, a verified Recovery Supervisor at entry, a recorded HUMAN_GATE_2 grant before `PROMOTED`, and `invoker == "lifecycle.recovery"` before `ROLLED_BACK` — all three read from real derived facts, none settable by the transitioning actor; (14) `take_core_snapshot` (`core_snapshot.py`) refuses a core-upgrade candidate before it may proceed unless a restorable pre-upgrade snapshot is registered and proves restorable by being read back and re-verified (`ArtifactStore.verify`/`.content_of`); (15) `EvolutionCampaign`'s four terminal states (`PROMOTED`, `COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN`, `ESCALATED`, `BLOCKED`) carry no outgoing transition — structurally no restart path exists — and `CampaignLedger.may_generate_successor()`/`.record()` (`campaign_ledger.py`, 217-line test suite pass) refuse a successor once any attempt outcome is `PROMOTED` or any budget/no-progress dimension is exhausted; (16) `campaign_record_shape.py` (Protected Core, `acceptance.engine`) refuses an evolution outcome unless its record proves a bounded objective, baseline metrics, all six canonical budgets and a genuine terminal state — additive only, no existing checker logic modified; (17) no architecture-budget exception was taken — `HUMAN_GATE_8` remains outstanding/not reached, and the live `architecture_budget_violation` gate returns PASS with 0 violations |
| **Rationale** | The reviewed Phase 23 Self-Evolution candidate (C-33) implements a `candidate → verification → acceptance → promotion` pipeline that composes, unmodified, every pre-existing Protected Core authority it touches: the sole PDP/PEP, the sole `StableRevisionPointer.promote`/`rollback_to`, the Phase 22B Recovery Supervisor as sole `ROLLBACK_STABLE` caller, and the scoped human-gate authorization mechanism itself. `promote_core_upgrade` performs no Stable mutation of its own — it only sequences two already-independent refusals (the `CoreUpgrade` state machine's `gate_2_guard` and `StableRevisionPointer.promote`'s own five-stage receipt proof), neither bypassable by the other. The self-evolution actor cannot write Stable directly (proven by AST scan, not convention), cannot accept its own candidate (a barred automated issuer's self-granted row is proven refused), and cannot escape a campaign's terminal state to retry for a different outcome (structural — no outgoing transition exists from any of the four terminal states). A restorable known-good snapshot is proven, not assumed, before every candidate proceeds. This grant is authorized precisely because it changes nothing about how Stable Core promotion is gated at runtime: the `PHASE_ACCEPTANCE`-scope table this record adds a row to is structurally distinct from the `RUNTIME_OPERATION`-scope table (`gate + operation + target + revision`) that `authorize_promotion` actually consults for any real future `CORE_PROMOTION` — the two tables are parsed independently, and this record adds nothing to the latter |
| **Scope — this grant authorizes** | `PHASE_ACCEPTANCE` evaluation of the Phase 23 candidate at the exact candidate freeze commit and evidence-package digest named above, and nothing beyond that |
| **Scope — this grant explicitly does NOT authorize** | A global `HUMAN_GATE_2` grant; any `RUNTIME_OPERATION`-scope grant of any kind — none is created by this record; any real future self-evolution campaign run against ARKALI's own source; any real future Stable Core promotion (`CORE_PROMOTION`) — that requires its own separate `RUNTIME_OPERATION`-scoped grant bound to the exact candidate-manifest and target-revision identity resolved at call time, which this record does not create; Phase 24 or any other phase; a modified Phase 23 candidate (a changed evidence package has a different digest and is not covered); any architecture-budget exception (`HUMAN_GATE_8`); any weakening, bypassing, broadening or reinterpreting of any security boundary, PDP rule, Protected Core policy, or the Recovery Supervisor's sole-rollback-authority position |
| **No runtime-operation grant created** | The operation-scope authorization table below (`gate + operation + target + revision`) is left exactly as it was — empty. This record adds only a `PHASE_ACCEPTANCE`-scope row |

---

## HGR-006 — HUMAN GATE 3: Phase 24 candidate (Generated Product Evolution SDK, C-36)

| Field | Value |
|---|---|
| **Gate** | HUMAN_GATE_3 — Generated-product promotion where approval-gated |
| **Decision** | **ACCEPTED** |
| **Scope of this decision** | Narrow — `PHASE_ACCEPTANCE` of the frozen Phase 24 candidate identified below only. This is **not** a global `HUMAN_GATE_3` grant, is **not** a `RUNTIME_OPERATION`-scope grant, does not authorize any future child-product promotion, Phase 25 or any other phase, any changed Phase 24 evidence package, the runtime `PROMOTE_CHILD_PRODUCT` operation, or any real future `CORE_PROMOTION`/ARKALI Stable Core promotion of any kind. See the "Scope" rows below |
| **Deciding authority** | human operator (canonical acceptance authority) |
| **Candidate identity bound by this decision** | Candidate freeze commit `42390ee0fc71037f9bf96f493f909c005a26dd4a`; evidence package digest `sha256:ecf43065fcdedb13fceece933145c58085363cda775b67e41873f8e286c06dc1` over `docs/acceptance/phase_24_report.json` + `phase_24_traceability.json` (`acceptance.rescoring_authorization.evidence_package_digest`, the identical binding mechanism GOV-001's RSA rows and HGR-002-SCOPED/HGR-003-SCOPED/HGR-004-SCOPED/HGR-005-SCOPED already use) |
| **Basis of decision** | Independent mechanical re-verification, run fresh against HEAD `9d0e4bf80aadd4e6bc38ce7c96cffc340305707d` immediately before this record was written, all confirmed true: (1) HEAD/branch `main`/clean working tree as stated; (2) `check_handoff.py` → PASS, 0 drift, on the full check set (the two-commit §12 handoff refresh + marker-advance sequence for this candidate's own `AWAITING_HUMAN_GATE` state was completed immediately before this record, closing a genuine `HANDOFF_DRIFT` this session found on arrival — governed artifacts (`docs/adr/ADR_INDEX.md`, `docs/build/OPEN_BLOCKERS.md`) had changed since the last handoff-refresh marker with no refresh commit recorded); (3) `GovernanceState.current_work_phase()` → `24`; (4) `git diff 42390ee..HEAD -- docs/acceptance/phase_24_report.json docs/acceptance/phase_24_traceability.json` is empty — the frozen candidate's evidence is byte-identical to the freeze commit named above; only `ARKALI_HANDOFF.md` and `docs/build/BUILD_STATE.md` changed afterward, via the §12 refresh + marker-advance commits, adding no production code and no cross-context edge; (5) `acceptance.rescoring_authorization.evidence_package_digest(repo, "24")` recomputes, independently, to the exact digest named above; (6) `RequirementRegister.for_phase("24")` returns 4 MANDATORY requirements (ARK-REQ-0131, 0132, 0133, 0358), matching the frozen candidate's own denominator; (7) `python scripts/run_phase_gate.py 24 25`, re-run fresh immediately before this record, returns verdict `AWAITING_HUMAN_GATE` with `HUMAN_GATE: HUMAN_GATE_3 required and not recorded for this exact evidence package (digest=sha256:ecf43065...)` as the **only** non-PASS/non-NOT_APPLICABLE check — C1–C6, EXTERNAL_RESULT (10 recorded runs), **PROTECTED_CORE normal profile** (no protected-core member touched — `lifecycle.evolution` is not Protected Core, confirmed directly against `AUTHORITY_MAP.yaml`), RESCORING (NOT_APPLICABLE, first submission), DATA_LOSS_RISK, FINDINGS and PREREQ (2/2, Phases 13, 16) all PASS; all 8 architecture gates PASS, 0 violations, over 202 cross-context edges (unchanged from Phase 23's own baseline), all 9 numeric budgets; (8) `GovernanceState.open_stopping_findings` is empty (0 open BLOCKER/HIGH); (9) mechanically proven against the live `HUMAN_GATE_RECORDS.md` (this document, before this record was appended): `human_gate_authorization._find_phase_gate_grant("HUMAN_GATE_3", "24", <phase-24-digest>)` resolves to `None`, and `HUMAN_GATE_3` is not in `SINGLETON_GATES` (`{HUMAN_GATE_1, HUMAN_GATE_7}`), so no flat `accepted_human_gates` path could ever satisfy it — no prior HGR (001–005) leaks into this decision; (10) `git diff --stat 166f837..42390ee -- backend/arkali/control/ backend/arkali/lifecycle/release/stable_pointer.py backend/arkali/lifecycle/recovery/recovery_supervisor.py backend/arkali/acceptance/human_gate_authorization.py backend/arkali/acceptance/governance_gates.py docs/canonical/AUTHORITY_MAP.yaml` is empty over the whole Phase 24 candidate — the sole PDP/PEP, ARKALI's own `StableRevisionPointer`, the Recovery Supervisor, and the scoped-grant mechanism itself are all reused completely unmodified; (11) `authorize_child_product_promotion` (`child_product_promotion.py`) populates `human_gate_3_recorded` only from a real `gates.operation_grant(GATE_3, "PROMOTE_CHILD_PRODUCT", target_identity, revision_identity)` lookup against the separate `RUNTIME_OPERATION`-scope table — never from this `PHASE_ACCEPTANCE`-scope grant, never from a caller-asserted boolean — re-verified live via `backend/tests/lifecycle/test_child_product_promotion.py` (including `test_a_barred_actor_cannot_manufacture_its_own_grant`, proving self-approval is refused) and `test_child_product_adversarial.py::TestArkaliCorePromotionCannotBeReachedOrMisused::test_the_two_operation_classes_are_distinct_strings`/`::test_no_child_product_module_references_core_promotion`, proving `PROMOTE_CHILD_PRODUCT` and `CORE_PROMOTION` are distinct, non-colliding scoping keys and no child-product module can reach the latter; (12) `test_child_product_adversarial.py::TestNoDirectStableOrLiveMutationAnywhereInTheChildProductSdk` (AST scan) proves `child_product_promotion.py` and `child_product_rollback.py` import neither `lifecycle.release` nor `lifecycle.recovery`, and no module names `StableRevisionPointer`'s own `.promote`/`.rollback_to` method identifiers outside the two sanctioned, differently-named child-product methods; (13) `test_child_product_adversarial.py::TestNoShadowAuthority` re-runs the live `duplicate_state_machine_authority`/`duplicate_canonical_authority`/`duplicate_lifecycle_authority`/`shadow_registry` architecture gates as an explicit adversarial assertion — no second campaign/PDP/human-gate/workspace/promotion authority exists anywhere in the child-product SDK; (14) `test_child_product_campaign.py::TestBeginsTheRealUnmodifiedEvolutionCampaignMachine` proves, by identity (`instance.machine.definition IS ecsm.DEFINITION`) rather than equality, that child-product campaigns run on Phase 23's own real `EvolutionCampaign` machine — no second state-machine authority was minted; (15) no architecture-budget exception was taken — `HUMAN_GATE_8` remains outstanding/not reached, and the live `architecture_budget_violation` gate returns PASS with 0 violations |
| **Rationale** | The reviewed Phase 24 Generated Product Evolution SDK candidate (C-36) implements child-product version/evolution infrastructure that composes, unmodified, every pre-existing Protected Core authority it touches: the sole PDP/PEP, ARKALI's own `StableRevisionPointer`/`RecoverySupervisor` (untouched, unreachable by any child-product module), and the scoped human-gate authorization mechanism itself, reused for a distinct `PROMOTE_CHILD_PRODUCT` scoping key rather than a second mechanism. `promote_child_product` performs no ARKALI Stable Core mutation of any kind — it is structurally incapable of reaching `lifecycle.release`/`lifecycle.recovery` at all (AST-proven, not by convention), and gates its own candidate → accepted → promoted transition on a real scoped `HUMAN_GATE_3` grant, never a caller-asserted boolean. The child-product SDK actor cannot manufacture its own grant (a barred issuer's self-granted row is proven refused), and reuses Phase 23's own real `EvolutionCampaign` machine and Phase 12's own real `WorkspaceAuthority` rather than minting parallel authorities. This grant is authorized precisely because it changes nothing about how ARKALI's own Stable Core is gated at runtime: the `PHASE_ACCEPTANCE`-scope table this record adds a row to is structurally distinct from the `RUNTIME_OPERATION`-scope table (`gate + operation + target + revision`) that `authorize_child_product_promotion` actually consults for any real future `PROMOTE_CHILD_PRODUCT` — the two tables are parsed independently, and this record adds nothing to either the runtime-operation table or to `CORE_PROMOTION`'s own, wholly separate scoping key (which HGR-005 remains the sole authority touching) |
| **Scope — this grant authorizes** | `PHASE_ACCEPTANCE` evaluation of the Phase 24 candidate at the exact candidate freeze commit and evidence-package digest named above, and nothing beyond that |
| **Scope — this grant explicitly does NOT authorize** | A global `HUMAN_GATE_3` grant; any `RUNTIME_OPERATION`-scope grant of any kind — none is created by this record; any real future child-product evolution campaign or promotion (`PROMOTE_CHILD_PRODUCT`) against any real child product — that requires its own separate `RUNTIME_OPERATION`-scoped grant bound to the exact target-identity and revision-identity resolved at call time, which this record does not create; Phase 25 or any other phase; a modified Phase 24 candidate (a changed evidence package has a different digest and is not covered); any real future ARKALI Stable Core promotion (`CORE_PROMOTION`) — wholly distinct from `PROMOTE_CHILD_PRODUCT`, governed solely by HGR-005 and its own separate, still-empty `RUNTIME_OPERATION`-scope row; any architecture-budget exception (`HUMAN_GATE_8`); any weakening, bypassing, broadening or reinterpreting of any security boundary, PDP rule, Protected Core policy, or ARKALI's own Recovery Supervisor/StableRevisionPointer authority |
| **No runtime-operation grant created** | The operation-scope authorization table below (`gate + operation + target + revision`) is left exactly as it was — empty. This record adds only a `PHASE_ACCEPTANCE`-scope row |

---

## GOV-001 — CANONICAL GOVERNANCE RULE: superseding re-acceptance

| Field | Value |
|---|---|
| **Type** | Human governance ruling establishing a standing rule |
| **Raised by** | The re-scoring question left unsettled by **ERR-004** |
| **Decision** | The Phase 4 superseding re-acceptance is **RATIFIED and VALID**. It is not withdrawn |
| **Scope** | Standing rule for every future phase re-acceptance. Phase 4 is not reopened or redesigned |
| **Cross-reference** | **ERR-004** (F-0024 confirmed, remediation ordered) |

### The rule

1. An accepted phase may later be found defective.
2. Discovery of a real BLOCKER/HIGH does **not** erase or rewrite the historical acceptance record.
3. The original acceptance remains **immutable historical evidence**, marked defective or superseded where applicable.
4. Remediation produces a **new** candidate/evidence package.
5. The implementing actor may implement the remediation but may **not** silently grant itself authority to supersede a prior accepted verdict.
6. Re-acceptance of a previously accepted phase requires explicit **RE-SCORING AUTHORIZATION** from either the applicable Human Gate / human governance authority, or a future canonical independent Acceptance Authority explicitly authorized to perform such supersession.
7. After authorization, the deterministic Phase Gate Checker / acceptance mechanism performs the actual re-score.
8. A successful re-score creates a **new superseding acceptance record**.
9. It must never amend the old acceptance commit, delete the defective evidence, rewrite historical reports, or conceal the discovered defect.
10. The Phase 4 remediation is **explicitly authorized** under this rule.

### What this changes about the Phase 4 sequence, stated plainly

Rule 6 requires authorization **before** the re-score. In the Phase 4 remediation the order was different: the implementing actor remediated, ran the checker, obtained `PHASE_ACCEPTED_BY_MACHINE`, and *then* reported the re-score together with the reasoning and an explicit statement that the position could be overturned. Rule 10 authorizes that instance retrospectively.

**Future sessions must not read Phase 4 as precedent for the ordering.** The compliant sequence is: remediate → produce the complete evidence package → **stop and request re-scoring authorization** → on authorization, run the acceptance mechanism → record the superseding verdict. A session that reaches a completed remediation of a previously accepted phase without authorization reports `PHASE_N_REACCEPTANCE_AWAITING_AUTHORITY` and waits.

### What was preserved, verified at this ruling

| Artifact | State |
|---|---|
| `docs/acceptance/phase_4_report_rev1_defective.json` | present, unmodified — the defective revision |
| Commit `1ea79f3` | intact — the original machine verdict |
| Commit `6d6296d` | intact — F-0024 reopened at HIGH, Phase 5 blocked |
| `KNOWN_FAILURES.md` F-0024 / F-0025 | retained in full, marked CLOSED with their resolutions |
| `PHASE_HISTORY.md` rows 16 and 17 | the defect and the remediation both recorded |

Nothing was amended, deleted or concealed.

### Enforcement status — ENFORCED (F-0026 closed)

GOV-001 is no longer prose-only. `acceptance/rescoring_authorization.py` is consulted by the Phase Gate Checker: a phase that already carries an acceptance record cannot receive `PHASE_ACCEPTED_BY_MACHINE` without a granted authorization in the table below bound to its exact evidence package. Without one the deterministic verdict is `AWAITING_RESCORING_AUTHORITY`.

There is no parameter, flag, environment variable or report field by which authorization can be asserted — the checker consults this document, and an implementing actor has nowhere to pass one in. Issuers named in `AUTHORITY_MAP.yaml` `stable_mutation.prohibited_actors` (and the generic `implementing_actor`) can never grant one.

**The limit of the mechanism, stated plainly.** It cannot stop an actor with write access from editing this file. No mechanical control in a single-actor repository can. What it does stop is the silent case: authorization must now be an explicit, scoped, auditable record in a human-governance document rather than an unstated assumption in an actor's head.

### RE-SCORING AUTHORIZATIONS

Each row authorizes one supersession of one phase, bound to the digest of that phase's exact evidence package (`phase_N_report.json` + `phase_N_traceability.json`). Changing either file changes the digest and the authorization no longer applies.

| ID | Phase | Evidence package | Issuer | Status | Basis |
|---|---|---|---|---|---|
| RSA-001 | 4 | sha256:6275ac092a624cb12cb1d40b68bdd59da01e87f761f41852da0ac4ccab9bb3cd | human acceptance authority | GRANTED | **GOV-001 rule 10** — "The current Phase 4 remediation is explicitly authorized under this rule." This row does not create a new authorization; it records the existing one in the form the checker can read, bound to the evidence package GOV-001 ratified |
| RSA-002 | 8 | sha256:a1fce09ca9afd5fbd0283b7f2a8ff62f2614a3587c71c063b798f7bec52eab27 | human acceptance authority | GRANTED | **Granted expressly and only because of F-0045 (HIGH).** The first Phase 8 submission was accepted on an inaccurate record: `phase_8_report.json` reported `check_repository_structure.py` and its negative control at exit 0 when, at the submitted commit `bb845d8`, the former returned 11 pass / 1 fail. With the true exit codes the first submission would have been `PHASE_BLOCKED` on C3 and C5. The acceptance authority **refused** the alternatives of downgrading F-0045 to MEDIUM or leaving the acceptance standing under an erratum, and required a superseding re-score instead. Conditions imposed and met: the defective first report and its verdict are preserved unaltered as `phase_8_report_rev1_defective.json`; every record in the superseding report was genuinely re-executed with no value transcribed from the defective revision; the candidate was fully re-verified before the re-score; and the acceptance guard was re-proven with the true exit codes, including the case that reproduces F-0045 and is refused on C3/C5. **SCOPE: this authorization covers exactly one supersession of Phase 8 bound to the evidence package digest in this row, and nothing else. It is NOT a general re-scoring power and NOT a precedent.** Changing either artifact changes the digest and this row stops applying. Cumulative verified stays 80 and Phase 8's zero-denominator position is unchanged |

---

## ERR-004 — HUMAN RULING (post-Phase 4): F-0024 confirmed, remediation ordered

| Field | Value |
|---|---|
| **Type** | Human ruling on a reported acceptance defect |
| **Raised by** | Pre-Phase-5 acceptance integrity check (finding **F-0024**) |
| **Decision** | **F-0024 CONFIRMED.** `ARK-REQ-0111` remains MANDATORY in Phase 4 |
| **Explicitly refused** | reclassification · deferral · weakening of its evidence requirements |
| **Ordered** | implement and verify it; repair **F-0025** in the same remediation because the affected parser is part of the acceptance path; do not begin Phase 5 |

**Why this is recorded as a ruling and not an erratum.** Nothing canonical was amended. The register already assigned `ARK-REQ-0111` to Phase 4; the defect was that an implementing actor reported it discharged without doing the work. The ruling confirms the register rather than changing it.

### Re-scoring an already-accepted phase

The remediation raised a governance question the canonical set does not address directly: may the acceptance mechanism issue a fresh verdict for a phase that was already machine-accepted? The position taken, and the basis for it:

* `AUTHORITY_MAP.yaml` `machine_autonomy.normal_phase_acceptance: machine`, and the dependency matrix records **no human gate** against Phase 4.
* `VERIFICATION_ARCHITECTURE.md` §1.4 names the **Phase Gate Checker** as the authority for a phase gate. The prohibition — "no implementing actor may issue, re-score or override any of these" — binds the implementing actor, which did not issue this verdict. The checker did, from evidence.
* `failed_gate_may_be_rescored_by_implementing_actor: false` is likewise a constraint on the actor, not on the mechanism.
* §2.2 rule 1 explicitly contemplates supersession: "Evidence is never edited or deleted. A superseded result is retained with a `supersedes` edge." The defective revision is retained as `phase_4_report_rev1_defective.json` and the original verdict stands in history at `1ea79f3`.
* Precedent: Phase 1 was re-submitted and machine-accepted after erratum ERR-001, at `1ae0835`.

The distinction between re-scoring a *rejected* phase (Phase 1) and a *previously accepted* one (Phase 4) is not addressed by the canonical set.

**RESOLVED by GOV-001.** The acceptance authority ratified this superseding re-acceptance as valid and established a standing rule for all future cases. The open question recorded here is closed; the answer is that re-acceptance is permitted but requires explicit re-scoring authorization **before** the re-score, which GOV-001 grants retrospectively for this instance only. See GOV-001 above.

---

## ERR-005 — GOVERNANCE ERRATUM (Phase 28): ARK-REQ-0180 applicability path

| Field | Value |
|---|---|
| **Type** | Human-authorized governance erratum — **not** an ordinary implementing-agent edit |
| **Raised by** | Phase 28 canonical discovery: the Appendix A expression named a field absent from the closed C-13 `CapabilityNode` schema |
| **Decision** | **AUTHORIZED** by the human acceptance authority |
| **Scope** | ARK-REQ-0180 Appendix A applicability evaluation in Phase 28 only |
| **Applies to** | `docs/canonical/REQUIREMENT_REGISTER.md` Appendix A, ARK-REQ-0180 row |
| **Old value** | `capability.local_executable == true` |
| **New value** | `capability.runtime_requirements.local_executable == true` |
| **Rationale** | C-13 declares `runtime_requirements: {...}` and the executable model represents it as `Mapping[str, Any]`; a real model probe preserved nested `local_executable: true` as a boolean. C-13 also uses `extra="forbid"`, so the old top-level path cannot exist without an unauthorized schema change |

### What this erratum does NOT change

It does not change `CapabilityNode`, add a canonical capability field, alter any
other requirement or applicability rule, create a policy authority, or establish
a precedent for another phase. It does not declare any capability applicable:
Phase 28 must still inspect each capability under test and obtain the nested
boolean from the real Capability Graph. Missing, non-boolean, or false values do
not become PASS by interpretation. No accepted phase is reopened or re-scored.

### Mechanical compatibility evidence

The live C-13 model accepted
`runtime_requirements={"local_executable": True}`, preserved the nested value as
Python `bool`, and serialized it as JSON `true`, without changing the twelve-field
schema. The old top-level spelling remains structurally forbidden.

---

## ERR-003 — GOVERNANCE ERRATUM (post-Phase 3): architecture-budget measurement contract

| Field | Value |
|---|---|
| **Type** | Human-authorized governance erratum — **not** an ordinary implementing-agent edit |
| **Raised by** | Phase 3 (finding **F-0020**) |
| **Decision** | **AUTHORIZED** by the human acceptance authority |
| **Scope** | Measurement definition only. No budget **value** changes |
| **Applies to** | `docs/canonical/AUTHORITY_MAP.yaml` → new `architecture_budget_measurement` section |
| **Ruling** | A numeric budget that participates in acceptance MUST have exactly one deterministic measurement definition. `max_cyclomatic_complexity_per_function` and `max_orchestration_depth` may not remain unenforced numbers |
| **Rationale** | An unmeasurable budget is unenforceable, and a formula authored by the implementing actor would let it decide whether its own code complies — the prohibition ADR-0008 already applies to budget exceptions |

**Cyclomatic complexity.** Standard McCabe, `M = decision_points + 1`, computed per Python function or method from the AST. The incrementing node types, their amounts, the boolean-operator rule and the explicit exclusions are enumerated in the contract. Nested functions are measured independently. Value unchanged at **12**.

**Orchestration depth.** The longest directed chain over the **bounded-context** graph, with edges derived from real resolved Python imports. This follows `ARCHITECTURE.md` §8, which defines the budget as "call chain across contexts"; ordinary depth inside a single context is therefore not orchestration depth. A cycle FAILs independently of depth, and unresolvable context ownership FAILs closed. Value unchanged at **4**.

### What this erratum does NOT change

No budget value, no requirement, no ADR, no contract, no phase state. It does not create a second architecture-budget authority: the measurement contract lives inside `AUTHORITY_MAP.yaml` alongside the values it measures, both owned by `control.architecture`.

### Consequence, recorded rather than avoided

Re-measuring the repository under the ratified formula exposed **three real violations** of a zero-threshold budget, one of them in accepted Phase 2 code (`acceptance/checker.py:evaluate`, measured 17 against 12). None was grandfathered and no HUMAN GATE 8 exception was requested. All three were repaired by decomposition with no behavioural change; the full suite and every negative control pass unchanged. Orchestration depth measured **3** against a budget of 4.

---

## ERR-002 — GOVERNANCE ERRATUM (post-Phase 3): Plugin `REMOVED` is terminal

| Field | Value |
|---|---|
| **Type** | Human-authorized governance erratum — **not** an ordinary implementing-agent edit |
| **Raised by** | Phase 3 canonical-inventory parsing (finding **F-0018**) |
| **Decision** | **AUTHORIZED** by the human acceptance authority |
| **Scope** | Narrow clarification of one transition expression |
| **Applies to** | `docs/canonical/STATE_MACHINES.md` §6 Plugin Lifecycle |
| **Old value** | `Transitions: … ; any→QUARANTINED→{DISABLED,REMOVED}` |
| **New value** | `Transitions: … ; any pre-REMOVED→QUARANTINED→{DISABLED,REMOVED}` plus `Forbidden: REMOVED→any` |
| **Ruling** | `REMOVED` is **TERMINAL**. `any` means any non-terminal, non-removed lifecycle state for this transition |

Read literally, `any` included `REMOVED`, making `REMOVED→QUARANTINED` legal and leaving the machine with **no terminal state** — a removed plugin could be quarantined, then re-enabled. Once a plugin revision reaches `REMOVED` it cannot leave, cannot be quarantined again, cannot be reactivated, and cannot be reinstalled by mutating the same lifecycle instance. Reintroducing the same plugin or package starts a **new** lifecycle instance with its own provenance and audit identity.

`any pre-REMOVED` is not new vocabulary: §7 Release already uses `any pre-RELEASED`, so the clarification reuses an idiom the canonical set had already accepted under HUMAN GATE 1.

### What this erratum does NOT change

No state is added or removed. The six non-terminal→`QUARANTINED` transitions, both quarantine exits, and the whole `DISCOVERED → … → ENABLED↔DISABLED` chain are unchanged, and are asserted unchanged by permanent tests so the narrowing cannot have over-reached. Authority (`engineering.plugin`), lifecycle authority, TRUST classification, Protected Core membership and requirement meaning are untouched. Phase 0 was not reopened; Phase 3 remains MACHINE-ACCEPTED.

---

## ERR-001 — GOVERNANCE ERRATUM (post-HUMAN GATE 1)

| Field | Value |
|---|---|
| **Type** | Human-authorized governance erratum — **not** an ordinary implementing-agent edit |
| **Raised by** | Phase 1 structural validation (finding **F-0015**) |
| **Decision** | **AUTHORIZED** by the human acceptance authority |
| **Scope** | Physical realizability only |
| **Applies to** | `docs/canonical/AUTHORITY_MAP.yaml` → `engineering.import.module_root` |
| **Old value** | `backend/arkali/engineering/import` |
| **New value** | `backend/arkali/engineering/project_import` |
| **Rationale** | `import` is a Python reserved keyword. A bounded context reachable only through `importlib` would be permanent language-level friction and technical debt |

### What this erratum does NOT change

The logical bounded-context identity **`engineering.import` is unchanged**, as are: canonical authority ownership (`imported_project_lifecycle → engineering.import`), bounded-context semantics, lifecycle authority (`import_project`), state-machine authority (`ImportProject`), TRUST classification, Protected Core membership (`false`), dependency direction, product scope, and requirement meaning (ARK-REQ-0115, 0161 and all Phase 19 entries are untouched).

Phase 0 was **not** reopened or redesigned. Stable Core promotion semantics were **not** invoked: no implemented or promoted Stable Core exists yet, so HUMAN GATE 2 is not engaged.

### Verification

| Evidence | Result |
|---|---|
| Ordinary `import` statement now works | `from arkali.engineering.project_import import __context__` → OK; `__context__` still reports `engineering.import` |
| No compatibility alias left behind | filesystem scan for any directory named `import` → none |
| Generic keyword check installed | `keyword.iskeyword` / `issoftkeyword` / `str.isidentifier` — not a hand-maintained word list |
| Negative control (EV-0012) | defective mapping REJECTED, corrected mapping ACCEPTED, 9/9 keywords and non-identifiers rejected, 0 false positives, canonical map unmodified |

### Effect

F-0015 **CLOSED**. EXT-002 **CLOSED**. Phase 1 re-validated and machine-accepted; Phase 2 unlocked. Prior candidate `0ad45a7447d63a6b418d987ab64a34a2e7de015a` preserved unamended as the record of the defect.

---

## Scoped Human-Gate Authorizations (mechanical, HUMAN_GATE_SCOPE_GAP remediation)

Append-only, machine-readable authorization tables. `acceptance.engine.human_gate_authorization`
parses these two tables (never the prose HGR records above) to decide whether
a specific phase-acceptance check or a specific runtime operation carries a
scoped grant. Neither table edits or reinterprets HGR-001 or HGR-002 above,
which remain the human-readable historical record of those two decisions;
these rows restate the same, already-recorded decisions in the shape the
checker actually reads, closing the gap HGR-002's own "KNOWN MECHANISM GAP"
note first documented — a grant recorded here for one phase or one
target/revision cannot satisfy a lookup for a different one, because `gate +
phase + evidence digest` (phase table) and `gate + operation + target +
revision` (operation table) are all required to match exactly.

**Phase-scope authorizations** (`gate + phase + evidence-package digest`, the
identical binding `rescoring_authorization.py` already uses for GOV-001):

| ID | GATE | PHASE | EVIDENCE PACKAGE | ISSUER | STATUS | BASIS |
|---|---|---|---|---|---|---|
| HGR-002-SCOPED | HUMAN_GATE_4 | 19 | sha256:6e41dd0dbb84df2403d6ebea98b6d2875871cd0806c5c6bb699d4cd0a457a727 | human operator | GRANTED | Mechanical restatement of HGR-002 above, unedited. Binds to phase 19's exact evidence-package digest only — a lookup for `(HUMAN_GATE_4, phase=21, *)` finds no matching row here, regardless of this grant, exactly as HGR-002's own scope section already stated in prose. |
| HGR-003-SCOPED | HUMAN_GATE_6 | 20 | sha256:b94d28bb86e515e36f0106f3620d72ddcb672771f9e1ab7ee1ba8f2f1e202c2c | human operator | GRANTED | Mechanical restatement of HGR-003 above, unedited. Binds to phase 20's exact evidence-package digest only — a lookup for `(HUMAN_GATE_6, phase=21, *)`, `(HUMAN_GATE_6, phase=22B, *)`, or any other phase/digest pair finds no matching row here. This is a `PHASE_ACCEPTANCE`-scope grant only; it creates no `RUNTIME_OPERATION`-scope row and does not authorize any `APPLY_MIGRATION` call against any target/revision. |
| HGR-004-SCOPED | HUMAN_GATE_4 | 21 | sha256:ca469acfc99fa53d85e6389158371ef3c55e5308d437a2b33132e1405468f0f7 | human operator | GRANTED | Mechanical restatement of HGR-004 above, unedited. Binds to phase 21's exact evidence-package digest only — a lookup for `(HUMAN_GATE_4, phase=19, *)` still resolves only through HGR-002-SCOPED's own row, never this one; a lookup for `(HUMAN_GATE_4, phase=22, *)`, `(HUMAN_GATE_4, phase=20, *)`, or any other phase/digest pair finds no matching row here. This is a `PHASE_ACCEPTANCE`-scope grant only; it creates no `RUNTIME_OPERATION`-scope row and does not authorize any real future plugin execution. |
| HGR-005-SCOPED | HUMAN_GATE_2 | 23 | sha256:3ad6f5fe20c8279ce62d2f15951a108099bb196b0fc4f53c8ae10e1f1eb5c00e | human operator | GRANTED | Mechanical restatement of HGR-005 above, unedited. Binds to phase 23's exact evidence-package digest only — a lookup for `(HUMAN_GATE_2, phase=24, *)`, `(HUMAN_GATE_2, phase=23, <a different digest>)`, or any other phase/digest pair finds no matching row here. This is a `PHASE_ACCEPTANCE`-scope grant only; it creates no `RUNTIME_OPERATION`-scope row and does not authorize any real future `CORE_PROMOTION` operation — `authorize_promotion` consults only the separate operation-scope table below, which this record leaves empty. |
| HGR-006-SCOPED | HUMAN_GATE_3 | 24 | sha256:ecf43065fcdedb13fceece933145c58085363cda775b67e41873f8e286c06dc1 | human operator | GRANTED | Mechanical restatement of HGR-006 above, unedited. Binds to phase 24's exact evidence-package digest only — a lookup for `(HUMAN_GATE_3, phase=25, *)`, `(HUMAN_GATE_3, phase=24, <a different digest>)`, or any other phase/digest pair finds no matching row here. This is a `PHASE_ACCEPTANCE`-scope grant only; it creates no `RUNTIME_OPERATION`-scope row and does not authorize any real future `PROMOTE_CHILD_PRODUCT` operation — `authorize_child_product_promotion` consults only the separate operation-scope table below, which this record leaves empty. |

**Operation-scope authorizations** (`gate + operation class + target identity +
revision identity`, for runtime operations such as `APPLY_MIGRATION` — see
`docs/contracts/human_gate_authorization.md`). Empty: no operation-scoped
grant has been recorded. `HGR-003` grants `HUMAN_GATE_6` for `PHASE_ACCEPTANCE`
of the Phase 20 candidate only (row above); a real future `APPLY_MIGRATION`
call against real or stable data still requires its own separate
`RUNTIME_OPERATION`-scope grant bound to the exact target identity and
revision identity resolved at call time — none exists, and none is created
by HGR-003.

| ID | GATE | OPERATION | TARGET | REVISION | ISSUER | STATUS | BASIS |
|---|---|---|---|---|---|---|---|

## Outstanding gates

| Gate | Purpose | Status |
|---|---|---|
| HUMAN_GATE_2 | ARKALI Stable Core promotion | **GRANTED for `PHASE_ACCEPTANCE` of the Phase 23 candidate only** — HGR-005, bound to candidate freeze commit `54f9e8b`/digest `sha256:3ad6f5fe...1eb5c00e`. **No `RUNTIME_OPERATION`-scope grant exists.** Any real future `CORE_PROMOTION` against ARKALI's own Stable Core still requires its own separate grant bound to the exact candidate-manifest/target-revision identity resolved at call time; HGR-005 does not authorize it |
| HUMAN_GATE_3 | Generated-product promotion where approval-gated | **GRANTED for `PHASE_ACCEPTANCE` of the Phase 24 candidate only** — HGR-006, bound to candidate freeze commit `42390ee`/digest `sha256:ecf43065...286c06dc1`. **No `RUNTIME_OPERATION`-scope grant exists.** Any real future `PROMOTE_CHILD_PRODUCT` against any real child product still requires its own separate grant bound to the exact target/revision identity resolved at call time; HGR-006 does not authorize it |
| HUMAN_GATE_4 | Security boundary / sandbox tier / protected-core policy change | **GRANTED for the Phase 19 candidate only** — HGR-002, bound to HEAD `ef5cb3b`/digest `sha256:6e41dd0d...`. **Separately GRANTED for the Phase 21 candidate only** — HGR-004, bound to candidate commit `34b841b`/digest `sha256:ca469acf...5468f0f7`. Each grant is scoped to its own phase and digest only and does not authorize the other, any other phase, or any modified candidate of either |
| HUMAN_GATE_5 | Exceptional applicability waiver | not reached |
| HUMAN_GATE_6 | APPLY of a migration to real or stable data | **GRANTED for `PHASE_ACCEPTANCE` of the Phase 20 candidate only** — HGR-003, bound to candidate commit `73a968f`/digest `sha256:b94d28bb...202c2c`. **No `RUNTIME_OPERATION`-scope grant exists.** Any real future `APPLY_MIGRATION` against real or stable data still requires its own separate grant bound to the exact target/revision identity resolved at call time; HGR-003 does not authorize it |
| HUMAN_GATE_7 | Final Production Release | not reached |
| HUMAN_GATE_8 | Exception to a canonical architecture budget | not reached |
