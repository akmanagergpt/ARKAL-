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

## Outstanding gates

| Gate | Purpose | Status |
|---|---|---|
| HUMAN_GATE_2 | ARKALI Stable Core promotion | not reached |
| HUMAN_GATE_3 | Generated-product promotion where approval-gated | not reached |
| HUMAN_GATE_4 | Security boundary / sandbox tier / protected-core policy change | not reached |
| HUMAN_GATE_5 | Exceptional applicability waiver | not reached |
| HUMAN_GATE_6 | APPLY of a migration to real or stable data | not reached |
| HUMAN_GATE_7 | Final Production Release | not reached |
| HUMAN_GATE_8 | Exception to a canonical architecture budget | not reached |
