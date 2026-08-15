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

## Deliberate boundary

This contract provides the C-26 evidence and anti-loop refusal only. It does
not run the root-cause pipeline (`ARK-REQ-0086`, `ARK-REQ-0238`), alter a
candidate, choose which strategy to attempt next, decide what "escalate"
means beyond refusing a repeat, discharge any Phase 14 requirement, or run
the Phase 14 gate. Deterministic repair transformers and `control.policy`
enforcement (`ARK-REQ-0240`) remain subsequent Phase 14 packages; Golden
Repair remains Phase 30.
