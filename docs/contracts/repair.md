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

## Deliberate boundary

This first atomic package provides the C-26 evidence contract only. It does not
run the root-cause pipeline, alter a candidate, choose a repair strategy,
escalate a repeated failed strategy, discharge any Phase 14 requirement, or run
the Phase 14 gate. Deterministic repair transformers and `control.policy`
enforcement remain subsequent Phase 14 packages; Golden Repair remains Phase
30.
