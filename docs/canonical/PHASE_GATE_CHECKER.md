# ARKALI GENESIS v2 — PHASE GATE CHECKER SPECIFICATION (PHASE 0B)

**Status:** PHASE 0 CANDIDATE — AWAITING HUMAN GATE 1
**Implementation phase:** Phase 2. **NOT implemented in Phase 0.**
**Owner:** `acceptance.engine` · **Protected Core:** yes

---

## 1. Why it exists

Under the canonical autonomy model, normal phases are accepted by machine, not by a human. But the Acceptance Engine does not exist until Phase 13. Without a deterministic gate, Phases 1–12 would be accepted by the same actor that produced them — self-certification.

The Phase Gate Checker closes exactly that window. It is deliberately small, deterministic and dumb.

## 2. What it is not

- **It uses no AI judgment.** No model call, no heuristic, no scoring, no natural-language evaluation. Given the same repository state it always returns the same verdict.
- **It does not replace the Acceptance Engine.** It performs no capability verification, no evidence-graph reasoning, no security analysis, no coverage computation against real test results.
- **It cannot weaken an acceptance contract.** It is Protected Core; it reads contracts and never writes them. It has no code path that edits a test, a threshold, a register entry or an authority map.
- **It does not grant human gates.** A HUMAN GATE always requires a recorded human decision; the Checker only observes whether one exists.

## 3. What it validates

Five deterministic checks. All must PASS for a phase to be machine-accepted.

**C1 — Phase report completeness.** The phase report contains all seventeen fields required by the Build Protocol §Phase report. A missing or empty field is FAIL. No field is inferred.

**C2 — Requirement register linkage.** Every ARK-REQ ID cited by the phase report exists in `REQUIREMENT_REGISTER.md`; every requirement whose `owning phase` equals this phase is either cited as closed or explicitly listed as deferred with a reason. An ID not in the register is FAIL. A MANDATORY requirement for this phase that is neither closed nor deferred is FAIL.

**C3 — Recorded test execution.** Every test the report claims was executed has a recorded invocation, exit code and duration in the evidence store. A claimed test with no recorded exit code is FAIL — not NOT_TESTED. A non-zero exit code that the report labels PASS is FAIL.

**C4 — Architecture gate evidence.** The eight architecture gates in `AUTHORITY_MAP.yaml` have recorded results for this phase, each with its negative-control fixture result. A gate reporting 0 violations without a passing negative control is FAIL — a detector that cannot detect is not evidence.

**C5 — Honest-state integrity.** No state in the report converts a non-PASS honest state into PASS. No `NOT_APPLICABLE` appears without a register citation. No applicability claim originates in the report.

## 4. Verdict model

```
all(C1..C5) == PASS            -> PHASE_ACCEPTED_BY_MACHINE   (progression continues)
any(C1..C5) == FAIL            -> PHASE_BLOCKED               (progression stops)
phase reaches a HUMAN GATE     -> AWAITING_HUMAN_GATE_n       (progression stops)
```

A `PHASE_BLOCKED` verdict stops progression until the underlying failure is repaired or explicitly escalated to the human authority. The implementing actor may not bypass, downgrade or re-score it. There is no override input.

## 5. Handover to the Acceptance Engine

From Phase 13 the Acceptance Engine performs capability verification and evidence-graph verdicts. The Checker is **superseded in capability but not in authority**: C1–C5 remain necessary conditions for every phase, and the Acceptance Engine adds sufficiency. The Checker is never removed and never relaxed.

## 6. Inputs and outputs

Inputs (read-only): phase report, `REQUIREMENT_REGISTER.md`, `AUTHORITY_MAP.yaml`, evidence store test records, architecture gate results, human gate records.
Output: one verdict record per phase, written to the evidence store, containing check-by-check results and the exact failing condition when blocked.

## 7. Acceptance criteria for the Checker itself (Phase 2)

- Deterministic: same repository state ⇒ same verdict, proven by repeated runs.
- Negative controls: a report with a missing field, an unknown ARK-REQ, a test claimed but not recorded, a gate without a negative control, and a `NOT_APPLICABLE` without citation must each produce FAIL.
- No AI dependency: the module imports no provider client. Enforced by architecture test.
- No write path to acceptance contracts: enforced by Protected Core boundary test.
