# EVIDENCE INDEX — ARKALI GENESIS v2

**Phase 0 candidate.** Evidence recorded here is limited to what was actually executed. Nothing in Phase 0 is capability evidence; Phase 0 produces no implementation.

## Evidence records

| ID | Evidence | Type | Command / method | Result | Covers |
|---|---|---|---|---|---|
| EV-0001 | `AUTHORITY_MAP.yaml` is machine-readable and internally consistent | mechanical validation | `python -c` YAML safe_load + invariant assertions | **exit 0.** 31 contexts · 39 concerns · 14 operation classes · 8 architecture gates · duplicate concern authorities = 0 · all `max_*` budgets numeric = True · contexts with unknown layer = [] · `stable_mutation.direct_mutation_permitted_by` = [] · protected_core members = 7 | ARK-REQ-0018, 0030, 0108, 0109 |
| EV-0002 | `REQUIREMENT_REGISTER.md` structural integrity | mechanical validation | `python -c` regex extraction + counting | **exit 0.** 313 entries · 313 unique · duplicate IDs = 0 · MANDATORY 303 / CONDITIONAL 8 / OPTIONAL 2 · CONDITIONAL entries missing an applicability rule = 0 · orphan applicability rules = 0 | ARK-REQ-0033, 0034, 0035, 0039 |
| EV-0003 | Phase 0A/0B deliverable reconciliation against the Build Protocol lists | mechanical validation | file-existence check per canonical list item | **exit 0.** Phase 0A 16/16 present · Phase 0B 11/11 present | ARK-REQ-0224, 0225 |

Both commands were executed in this phase and their output recorded. No result in this index is estimated, recalled or inferred.

## Evidence deliberately absent

| Evidence class | State | Reason |
|---|---|---|
| Unit / contract / integration tests | NOT_APPLICABLE | no implementation exists in Phase 0 |
| Architecture gate results | NOT_TESTED | gates require source code; executable from Phase 2 |
| Negative-control fixtures for gates | NOT_TESTED | built with the gates in Phase 2 |
| Phase Gate Checker verdict | NOT_TESTED | Checker implemented in Phase 2 |
| Security / sandbox escape tests | NOT_TESTED | no executable surface; isolation probe at Phase 4 |
| Real runtime / browser / persistence | NOT_APPLICABLE | no runtime exists |
| Real generated product | NOT_APPLICABLE | factory does not exist until Phase 16 |
| Provider evidence | NOT_CONFIGURED | no provider configured; none required for Phase 0 |
| Golden Repair corpus **definition** | **PASS** | delivered: `docs/canonical/GOLDEN_REPAIR_CORPUS_DEFINITION.md` (ARK-REQ-0090, 0091) |
| Golden Repair corpus **instantiation** | NOT_APPLICABLE | ARK-REQ-0187/0188 — no accepted Golden Product to inject into until Phase 30 |
| Golden Repair benchmark run | NOT_APPLICABLE | requires an accepted Golden Product |
| Mutation / property / chaos | NOT_APPLICABLE | nothing to mutate or perturb |
| L2 / L3 execution evidence | NOT_APPLICABLE | no packaged artifact exists |
| HUMAN GATE 1 record | **AWAITING** | must be granted by the human acceptance authority |

## Coverage statement

Mandatory requirement coverage is **0 / 303 verified** at Phase 0, by design. Phase 0 establishes the denominator; it verifies no capability. Any coverage percentage reported before Phase 2 would be meaningless, and none is claimed.
