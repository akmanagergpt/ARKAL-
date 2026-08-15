# C-26 Repair Fingerprint + Budget Ledger — derived contract

**Owner:** `engineering.repair`  
**Kind:** EVD  
**Version:** 1.0.0  
**Lifecycle:** STRICT

This document records the executable Phase 14 contract derived from the
canonical requirement register, `CONTRACT_INVENTORY.md`, the repair pipeline in
`MASTER_SPECIFICATION.md`, and the failure protocol in
`CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md`. It does not replace those
authorities.

## Repair fingerprint

Every attempted repair records exactly the failure signature, root-cause class,
files, strategy, provider/model, and outcome. The immutable canonical rendering
is content-addressed. File order is normalised and duplicate or empty file sets
are refused so the same attempt cannot acquire multiple identities through
presentation alone.

## Six-dimensional budget

The ledger accounts for attempts, AI calls, elapsed time in seconds, provider
cost, touched files, and regression delta. All six ceilings are declared before
an attempt. Recording returns a new immutable ledger and refuses any candidate
that would cross a ceiling. Attempt accounting is reconciled with the number of
recorded fingerprints, so an unaccounted repair cannot pass as evidence.

## Anti-loop refusal

A ledger is scoped to one candidate's convergence attempt on one defect. A
fingerprint whose (failure signature, root-cause class, strategy) repeats one
already recorded in the same ledger is refused by `record` before the budget
is touched — by construction a repeat means the first attempt at that exact
strategy did not resolve the defect, since otherwise the loop would not have
reached a second attempt. `files`, `provider/model` and `outcome` do not
participate in that identity: `outcome` is declared free text with no
canonical pass/fail vocabulary for a single attempt (unlike the campaign-level
`ESCALATED`/`BLOCKED` machines defined elsewhere), so the refusal is a
structural property of the fingerprint history, never a classification of
`outcome`'s text. This is `ARK-REQ-0087` and `ARK-REQ-0239`'s "repeated failed
strategy escalates instead of looping", and is the anti-loop property C-26's
own inventory row names as this contract's verification responsibility.

## Failure-protocol stage vocabulary — CANONICAL_AMBIGUITY

`failure_protocol.py` parses both pipelines the canonical set declares for
`ARK-REQ-0086` (`MS §Root-Cause and Convergence Engine`) and `ARK-REQ-0238`
(`BP §Failure protocol`):

```
MS (9 stages): Reproduce -> Observe -> Evidence -> Hypotheses -> Experiment
               -> Root Cause -> Minimal Repair -> Targeted Acceptance
               -> Regression
BP (11 stages): Reproduce -> Evidence -> Classify -> Hypotheses -> Experiment
               -> Root Cause -> Minimal Change -> Candidate -> Targeted Tests
               -> Regression -> Accept/Reject
```

Reconciled with the identical algorithm `harness_elements.py` established for
this exact shape of problem (`ARK-REQ-0054`/`ARK-REQ-0231`, Phase 10): the two
declarations must agree in stage count, and at each position one name must be
a word-wise abbreviation of the other. **They do not reconcile.** The counts
differ (9 against 11), and the two mismatched segments are not abbreviation
pairs:

- Positions 2–3: MS declares `Observe`, `Evidence`; BP declares `Evidence`,
  `Classify`. Neither MS name shares a word root with the BP name at the same
  position (`Observe`/`Evidence` at position 2; `Evidence`/`Classify` at
  position 3) — this is not a wording variance, it is two different pairs of
  words.
- Positions 8–11 (BP numbering): MS names one stage, `Targeted Acceptance`;
  BP names `Candidate`, `Targeted Tests`, `...`, `Accept/Reject` — BP declares
  two explicit stages (`Candidate`, `Accept/Reject`) that MS's text does not
  name at all, at any position.

`Reproduce`, `Hypotheses`, `Experiment`, `Root Cause` and `Regression` are the
only stages identical in both documents.

**Neither document is preferred.** The register assigns `ARK-REQ-0086` to MS
and `ARK-REQ-0238` to BP with equal MANDATORY weight, and this contract's own
precedent (`harness_elements.py`) refuses to invent a mapping neither
document's text actually states — doing so here (e.g. deciding `Observe`
means the same thing as `Classify`) would be the alias-table defect (F-0013
wearing a different hat) that precedent's docstring names explicitly.

**This is CANONICAL_AMBIGUITY, not a defect in this module.**
`FailureProtocolVocabulary.stages()` is proven (by
`test_failure_protocol.py::TestTheRealDocumentsGenuinelyDoNotReconcile`) to
raise `AuthoritativeSourceError` against the live documents, naming both
counts. The minimal governance decision this needs, from whoever holds
authority to interpret canonical text (not the implementing actor): either
(a) rule which document's stage vocabulary governs the operational, machine-
enforced pipeline (`MS`'s 9-stage summary or `BP`'s 11-stage procedure), or
(b) amend one canonical document so the two texts genuinely reconcile under
the established algorithm. Until that ruling exists, no root-cause pipeline
orchestrator can be built against a single derived stage list without
inventing content neither document states.

## Deliberate boundary

This contract provides the C-26 evidence contract, the anti-loop refusal, and
the failure-protocol vocabulary parser's proof of the MS/BP ambiguity above.
It does not run the root-cause pipeline (`ARK-REQ-0086`, `ARK-REQ-0238`) —
blocked on the ambiguity above — alter a candidate, choose which strategy to
attempt next, decide what "escalate" means beyond refusing a repeat,
discharge any Phase 14 requirement, or run the Phase 14 gate. Deterministic
repair transformers and `control.policy` enforcement (`ARK-REQ-0240`) remain
subsequent Phase 14 packages; Golden Repair remains Phase 30.
