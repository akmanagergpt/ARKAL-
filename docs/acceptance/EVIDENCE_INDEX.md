# EVIDENCE INDEX — ARKALI GENESIS v2

**Phase 0 ACCEPTED (HGR-001). Phase 1 candidate — NOT accepted.** Evidence recorded here is limited to what was actually executed. Every non-executed check carries an honest state and a reason; none is reported as PASS.

## Evidence records

| ID | Evidence | Type | Command / method | Result | Covers |
|---|---|---|---|---|---|
| EV-0001 | `AUTHORITY_MAP.yaml` is machine-readable and internally consistent | mechanical validation | `python -c` YAML safe_load + invariant assertions | **exit 0.** 31 contexts · 39 concerns · 14 operation classes · 8 architecture gates · duplicate concern authorities = 0 · all `max_*` budgets numeric = True · contexts with unknown layer = [] · `stable_mutation.direct_mutation_permitted_by` = [] · protected_core members = 7 | ARK-REQ-0018, 0030, 0108, 0109 |
| EV-0002 | `REQUIREMENT_REGISTER.md` structural integrity | mechanical validation | `python -c` regex extraction + counting | **exit 0.** 313 entries · 313 unique · duplicate IDs = 0 · MANDATORY 303 / CONDITIONAL 8 / OPTIONAL 2 · CONDITIONAL entries missing an applicability rule = 0 · orphan applicability rules = 0 | ARK-REQ-0033, 0034, 0035, 0039 |
| EV-0003 | Phase 0A/0B deliverable reconciliation (superseded by EV-0005) | mechanical validation | file-existence check per canonical list item | **exit 0**, but count was hand-mapped and produced a false PASS (F-0008) and a miscount (F-0010). Superseded | ARK-REQ-0224, 0225 |
| EV-0004 | Phase dependency graph is executable and deadlock-free | mechanical validation | `python scripts/check_phase_graph.py` | **exit 0. 10/10 PASS.** Graph **parsed from authoritative documents**, not hard-coded: 41 phases from the Master Specification · 41 prerequisite rows from `IMPLEMENTATION_DEPENDENCY_MATRIX.md` · 1 DENY from the Master Specification · 8 human gates from `AUTHORITY_MAP.yaml`. 92 edges over 3 graph-edge classes; human gates checked separately. No forward prerequisite · no directed cycle · all phases reachable · DENY satisfiable (22B before 23) · Release reachable · Installer integrates Recovery Supervisor · no duplicate release authority | ARK-REQ-0135, 0136, 0182 |
| EV-0004N | **Drift negative control** for EV-0004 | mechanical validation | `python scripts/check_phase_graph_negative.py` | **exit 0 (control behaved correctly).** The HG1-05 defect is injected into an **in-memory copy** of the authoritative matrix and the same parser + validator re-run: **3 checks FAIL as required**, reporting the cycle `25 → 26 → 22B → 23 → 24 → 25`. Repository matrix verified unmodified afterwards. Proves the validator rejects a defective authoritative input rather than passing vacuously | — |
| EV-0005 | Phase 0A/0B deliverable reconciliation, counts derived from canonical lists | mechanical validation | `python scripts/check_phase0_deliverables.py` | **exit 0.** Phase 0A **16/16**, Phase 0B **11/11**. Bullet counts parsed from the Build Protocol; every bullet resolved by file existence **and** content probe | ARK-REQ-0224, 0225 |
| **EV-0006** | **HUMAN GATE 1 acceptance decision** | **human decision record** | independent inspection of the actual Phase 0A/0B artifacts and independent execution of the validation scripts by the human acceptance authority | **ACCEPTED.** Candidate `007ebf6e9275fa99d932022004440b1b869701d4`. Phase 0A and 0B accepted as one package. Recorded as `HGR-001` in `HUMAN_GATE_RECORDS.md` | ARK-REQ-0183, 0201, 0226 |
| EV-0007 | Phase 1 repository structure validation | mechanical validation | `python scripts/check_repository_structure.py` | **exit 1. 11 PASS / 1 FAIL.** 31/31 context roots exist as packages with matching declarations · 0 duplicate module_root · 0 implementation modules · budgets respected · 0 secrets · 0 fake markers · 0 Stable mutation paths · 0 Phase 2+ constructs. **FAIL check 8** — `engineering.import` module root is a Python keyword (F-0015). Dependency-direction check reported **PASS (vacuous)** — 0 cross-context imports exist to reject | ARK-REQ-0206, 0208 |
| EV-0008 | Backend test discovery and execution | real test run | `python -m pytest -q` (backend/) | **exit 1. 7 collected, 6 passed, 1 failed.** The failure is the structural test asserting no keyword module root (F-0015). Not skipped, xfailed or deleted | ARK-REQ-0208, 0209 |
| EV-0009 | Python package import validation | mechanical validation | importlib over every declared context | **exit 0.** 31/31 contexts import. `engineering.import` reachable only via `importlib.import_module` | ARK-REQ-0206 |
| EV-0010 | Frontend manifest and lockfile validation | real tooling | `npm install --package-lock-only`; JSON parse of manifest/lock/tsconfig; `npm pkg get` | **exit 0.** `package-lock.json` lockfileVersion 3, **183 packages resolved by real npm**, `node_modules` not installed. Lock name matches manifest | ARK-REQ-0208 |

Every command above was executed and its exit code recorded. No result in this index is estimated, recalled or inferred. EV-0007 and EV-0008 record real failures rather than suppressing them.

## Evidence deliberately absent

| Evidence class | State | Reason |
|---|---|---|
| Unit / contract / integration tests | NOT_APPLICABLE | no capability implemented; only structural tests exist |
| Architecture gate results (the 8 canonical gates) | NOT_TESTED | Phase 2 deliverable; Phase 1 ran a structure validator, which is not one of the 8 gates |
| TypeScript / Vite build validation | NOT_CONFIGURED | frontend dependencies not installed |
| Rust / Tauri workspace validation | UNSUPPORTED | no Rust toolchain on this machine |
| Python 3.13 canonical-runtime validation | NOT_CONFIGURED | local runtime is 3.12.10 |
| Python lockfile | NOT_CONFIGURED | no lock tool (poetry/uv/pip-tools) available; none fabricated |
| ruff lint | NOT_CONFIGURED | ruff not installed |
| Negative-control fixtures for gates | NOT_TESTED | built with the gates in Phase 2 |
| Phase Gate Checker verdict | NOT_TESTED | Checker implemented in Phase 2 |
| Security / sandbox escape tests | NOT_TESTED | no executable surface; isolation probe at Phase 4 |
| Real runtime / browser / persistence | NOT_APPLICABLE | no runtime exists |
| Real generated product | NOT_APPLICABLE | factory does not exist until Phase 16 |
| Provider evidence | NOT_CONFIGURED | no provider configured; none required for Phase 0 or 1 |
| Golden Repair corpus **definition** | **PASS** | delivered: `docs/canonical/GOLDEN_REPAIR_CORPUS_DEFINITION.md` (ARK-REQ-0090, 0091) |
| Golden Repair corpus **instantiation** | NOT_APPLICABLE | ARK-REQ-0187/0188 — no accepted Golden Product to inject into until Phase 30 |
| Golden Repair benchmark run | NOT_APPLICABLE | requires an accepted Golden Product |
| Mutation / property / chaos | NOT_APPLICABLE | nothing to mutate or perturb |
| L2 / L3 execution evidence | NOT_APPLICABLE | no packaged artifact exists |
| HUMAN GATE 1 record | **PASS — GRANTED** | see EV-0006 |

## Coverage statement

Mandatory requirement coverage is **5 verified** after the Phase 1 candidate (ARK-REQ-0206, 0208, 0220, 0223, 0243). Phase 0 itself verified 0. The denominator is read from the Canonical Requirement Register (snapshot at this candidate: 303 MANDATORY); it is not maintained independently here. Phase 1 verified only its own five governance requirements; it implemented no capability. No capability coverage is claimed.
