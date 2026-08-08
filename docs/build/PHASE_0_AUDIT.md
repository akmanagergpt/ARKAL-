# PHASE 0 — INTERNAL CONTRADICTION AND TRACEABILITY AUDIT

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1
**Audited against:** canonical set at `079c925996034017855fb9d1f1fa532077d7e86d`
**Method:** mechanical checks against the generated artifacts, executed and recorded. Not asserted.

---

## Mandated checks

| # | Check | Result | Basis |
|---|---|---|---|
| 1 | Every major canonical concern has exactly one authority | **PASS** | A1 — 39 concerns, 0 with multiple owners |
| 2 | Every normative requirement maps to an ARK-REQ ID | **PASS (with scope note)** | 313 entries covering every section of MS/BP/VDC; see note below |
| 3 | Every MANDATORY requirement has an owner and evidence definition | **PASS** | A2, A3 — 313/313 |
| 4 | Every CONDITIONAL requirement has an objective applicability rule | **PASS** | A4, A5 — 8/8, and no orphan rules |
| 5 | No implementing actor can self-author applicability | **PASS** | ARK-REQ-0040, 0217, 0306; MS §Applicability; BP mandatory rule |
| 6 | No direct Stable mutation path exists | **PASS** | A6 — `direct_mutation_permitted_by: []`; A16 — `WRITE_STABLE_FILE` fixed DENY |
| 7 | ROLLBACK_STABLE is Recovery-Supervisor-only and immutable-revision based | **PASS** | A7–A10 |
| 8 | Protected Core membership is explicit | **PASS** | A11 — 7 contexts flagged, all 9 canonical minimum components mapped |
| 9 | TRUST tiers have enforceable required security properties | **PASS** | A12 — all 5 tiers, TRUST-4 requires all 7 properties |
| 10 | Isolation Backend failure ⇒ DENY/UNSUPPORTED, never silent downgrade | **PASS** | A13, A14 |
| 11 | Computer-Use operation classes map to policy | **PASS** | A15–A17 — 14 classes, unmapped ⇒ DENY |
| 12 | Human Gates are consistent | **PASS** | A18 — 8 gates identical across BP, SC, MS references and authority map |
| 13 | Normal machine phase autonomy remains intact | **PASS** | A19, A20 — no human approval for normal phases; failed gate blocks and is not rescorable |
| 14 | Phase 0A/0B form one acceptance package | **PASS** | ARK-REQ-0183; MS §Phases; BP §Phase 0 |
| 15 | No Phase 1 work is unlocked yet | **PASS** | `BUILD_STATE.md` Phase 1 = NOT_STARTED; no source code exists |
| 16 | Architecture budgets are numeric | **PASS** | A21, A22 — 9 numeric budgets, exception gated at GATE 8, not self-authorable |
| 17 | Workflow canonical graph authority is singular | **PASS** | A23 — sole owner `execution.workflow`; derived caches hash-bound |
| 18 | Hardening / self-evolution loops are bounded | **PASS** | ARK-REQ-0139–0142, 0145–0148; four terminal states each; no restart to change terminal state |
| 19 | No orphan BLOCKER/HIGH requirement remains | **PASS** | see §Findings |

**Note on check 2.** Every *section* of all three canonical documents is represented, and every requirement in the register carries a source citation. Because the register was authored by extraction rather than by an automated normative-statement parser, exhaustiveness at the sentence level is asserted by construction, not proven mechanically. The canonical safety net is MS §Canonical Requirement Register: any normative statement not classified **defaults to MANDATORY**, so an omission cannot silently downgrade a requirement — it fails closed. A mechanical normative-statement extractor is deferred to Phase 2 (DEF-001 class work) and will reconcile against this register.

## Additional structural checks

| # | Check | Result |
|---|---|---|
| 20 | No duplicate ARK-REQ IDs | **PASS** — 313 entries, 313 unique |
| 21 | No duplicate state-machine authority | **PASS** (A24) |
| 22 | No duplicate lifecycle authority | **PASS** — 14 lifecycles, single owner each |
| 23 | Provider fields single-owned, copying and caching prohibited | **PASS** (A25) |
| 24 | All contexts in known layers; upward deps and cycles forbidden | **PASS** (A26, A27) |
| 25 | Eight architecture gates each require a negative-control fixture | **PASS** (A28) |
| 26 | Identifier-only checker declared insufficient | **PASS** (A29) |
| 27 | `AUTHORITY_MAP.yaml` parses as YAML | **PASS** — EV-0001 |
| 28 | Canonical documents unmodified by Phase 0 | **PASS** — 0 modifications |
| 29 | No application source code produced | **PASS** — code-file scan returns none |

## Findings

**BLOCKER: 0. HIGH: 0.**

**MEDIUM: 3 (new, Phase 0 specific)**
- M-P0-1 — Register exhaustiveness is by construction, not by mechanical extraction (check 2 note). Mitigated by the default-MANDATORY rule; reconciliation deferred to Phase 2.
- M-P0-2 — The architecture is unproven. Every ownership claim, layer rule and budget is a declaration until Phase 2 gates execute against real code. Phase 0 cannot establish more than this.
- M-P0-3 — 9 ADRs are PROPOSED, not ACCEPTED. They become ACCEPTED on HUMAN GATE 1 as part of the package.

**LOW: 2 (new)**
- L-P0-1 — `docs/contracts/` and `docs/security/` are declared in the Build Protocol but remain empty at Phase 0; their content is Phase 2 work.
- L-P0-2 — Golden Repair corpus is defined but unpopulated (DEF-004).

Prior MEDIUM/LOW findings carried from the canonical repair are listed in `OPEN_BLOCKERS.md` and are unchanged.

## Counts

| Metric | Value |
|---|---|
| BLOCKER | 0 |
| HIGH | 0 |
| MEDIUM | 3 new + 10 carried |
| LOW | 2 new + 7 carried |
| Orphan requirements | 0 (all 311 have owner + evidence) |
| Orphan acceptance gates | 1 — `ARKALI_RELEASE_QUALITY_REPORT.md` content contract (LOW, carried) |
| Authority conflicts | 0 |
| Unbounded loops | 0 |
| Security boundary ambiguities | 0 |

### Current-state denominator (single source)

All current-state assertions in this document use the Canonical Requirement Register as their only denominator:

| Metric | Current value |
|---|---|
| Register entries | **313** |
| MANDATORY | **303** |
| CONDITIONAL | **8** |
| OPTIONAL | **2** |
| Phase 0A deliverables | **16/16** (count derived from the canonical Build Protocol list) |
| Phase 0B deliverables | **11/11** (count derived from the canonical Build Protocol list) |

Any figure elsewhere in this file that differs from the table above is **historical failed evidence** and is labelled as such. No stale value is used as a current PASS basis.

---

# HUMAN GATE 1 CORRECTION RE-AUDIT

Four HIGH defects were found after the first internal audit passed — three by independent review, one by this correction repeating the defect it was fixing. All are closed.

| Finding | Defect | Closure | Verified by |
|---|---|---|---|
| HG1-01 / F-0006 | Contract inventory absent (deferred to Phase 2 as DEF-007) | `CONTRACT_INVENTORY.md` — 36 families, 0 with multiple owners | content probe |
| HG1-02 / F-0005 | ARK-REQ-0090/0091 claimed CLOSED while other artifacts recorded the corpus unpopulated | Canonical basis re-read; definition delivered; instantiation split to new ARK-REQ-0187/0188 at Phase 30, recorded NOT_APPLICABLE at 0B | check 1, check 6 |
| HG1-03 / F-0007 | ARK-REQ-0012 CONDITIONAL narrowed an unconditional canonical requirement | Reclassified MANDATORY; rule removed; ADR-0006 corrected | check 4 |
| HG1-04 / F-0006 | Verification architecture, evidence graph strategy, dependency matrix, contradiction analysis only incidental | Four dedicated artifacts created | content probe |
| — / F-0008 | The 0B matrix falsely PASSed "clean-test baseline definition" by asserting a path without checking | `CLEAN_TEST_BASELINE.md` created; matrix rebuilt to resolve every claim by file existence **and** content probe | check 3 |

## Re-audit results (12 mandated checks, all executed)

| # | Check | Result |
|---|---|---|
| 1 | No Phase 0 requirement marked CLOSED without required evidence | **PASS** |
| 2 | Every Phase 0A deliverable exists | **PASS** — 16/16, count derived from the canonical list, content-probed (EV-0005) |
| 3 | Every Phase 0B deliverable exists | **PASS** — 11/11, count derived from the canonical list, content-probed (EV-0005) |
| 4 | Classifications do not narrow unconditional requirements | **PASS** |
| 5 | CONDITIONAL rules cannot be scope-reduction exploits | **PASS** — 8/8 with objective rules, 0 orphan rules |
| 6 | BUILD_STATE / OPEN_BLOCKERS / PHASE_HISTORY / PHASE_0_AUDIT / REGISTER agree | **PASS** |
| 7 | BLOCKER = 0 | **PASS** |
| 8 | HIGH = 0 | **PASS** |
| 9 | Authority conflicts = 0 | **PASS** — 39 concerns, one owner each |
| 10 | Phase 1 remains locked | **PASS** |
| 11 | ADRs remain PROPOSED | **PASS** — 9 PROPOSED, 0 ACCEPTED |
| 12 | No application source code | **PASS** |

## Standing lesson

The first internal audit reported 29/29 PASS while four HIGH defects were present, because every check compared the generated artifacts against **each other** rather than against the canonical deliverable lists and requirement text. Self-consistency is not conformance. This is the concrete, observed justification for the canonical rule that the implementing actor is not the acceptance authority — and it is why HUMAN GATE 1 exists.

## Verdict

Internal audit after correction: **PASS**. This is an internal machine/self audit only. It is **not** acceptance. Phase 0 is submitted as a candidate package to the human acceptance authority for HUMAN GATE 1 and must not be treated as accepted on the strength of this document.
