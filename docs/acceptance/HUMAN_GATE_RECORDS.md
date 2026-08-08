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
