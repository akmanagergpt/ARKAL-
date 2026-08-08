# KNOWN FAILURES — ARKALI GENESIS v2

Failures are recorded whether or not they were caught before commit. A defect found and fixed inside the same phase is still a defect and is logged here.

## Phase 0

| ID | Failure | Detected by | Severity | Resolution |
|---|---|---|---|---|
| F-0001 | `AUTHORITY_MAP.yaml` opened with a fullwidth `＃` (U+FF03) instead of ASCII `#`, which would have prevented the machine-readable authority map from parsing at all — the file's entire purpose | Phase 0 self-audit, before commit | HIGH (would have been) | Corrected to ASCII `#`; YAML parse re-verified exit 0 |
| F-0002 | `REQUIREMENT_REGISTER.md` Appendix B asserted 371 entries / 360 MANDATORY without measurement; actual values are 311 / 300 | Mechanical count during self-audit | HIGH (would have been) | Appendix B corrected to measured values; note added that counts are mechanically verified, not asserted |
| F-0003 | `PHASE_GATE_CHECKER.md` §6 contained a non-English word ("содержащее") from a generation slip | Self-audit read-back | LOW | Corrected to "containing" |
| F-0004 | `.gitignore` rule `build/` (Python packaging artifacts) silently excluded the entire canonical `docs/build/` tree — the six state files the Build Protocol requires to be version controlled (ARK-REQ-0221, 0222). Six Phase 0 artifacts were invisible to git | `git status` showed 9 files where 15 were expected; confirmed with `git check-ignore -v` | **HIGH (would have been)** | Added `!docs/build/` + `!docs/build/**` negations immediately after the `build/` rule. Re-verified: all six canonical files tracked, `backend/build/**` and `frontend/dist/**` still ignored |

| F-0005 | **False closure of a MANDATORY requirement.** `PHASE_HISTORY.md` claimed ARK-REQ-0090/0091 CLOSED while `BUILD_STATE`, `OPEN_BLOCKERS` and `PHASE_0_AUDIT` recorded the corpus as unpopulated and deferred (DEF-004). Four Phase 0 artifacts disagreed with each other | **Independent review (HG1-02)** — internal audit missed it | **HIGH** | Canonical basis re-read: BP §Phase 0B assigns the corpus *definition*; MS binds injected defects to an accepted Golden Product. Definition delivered as `GOLDEN_REPAIR_CORPUS_DEFINITION.md`; 0090/0091 restated as definition obligations; instantiation registered separately as new ARK-REQ-0187/0188 at Phase 30; all four artifacts reconciled |
| F-0006 | **Five Phase 0A deliverables absent.** Build Protocol §Phase 0A requires contract inventory, verification/test architecture, evidence graph strategy, implementation dependency matrix and contradiction/blocker analysis. The candidate deferred the contract inventory to Phase 2 (DEF-007) and covered the other four only incidentally inside other documents | **Independent review (HG1-01, HG1-04)** | **HIGH** | Created `CONTRACT_INVENTORY.md` (36 families), `VERIFICATION_ARCHITECTURE.md` (test architecture + evidence graph strategy), `IMPLEMENTATION_DEPENDENCY_MATRIX.md`, `CONTRADICTION_ANALYSIS.md`. DEF-007 withdrawn |
| F-0007 | **Classification narrowed an unconditional requirement.** ARK-REQ-0012 ("PostgreSQL-ready abstractions", stated unconditionally in MS §Frozen technology direction) was classified CONDITIONAL with rule `deployment.database_engine == "postgresql"` — which would make the abstraction requirement inapplicable in exactly the default deployment | **Independent review (HG1-03)** | **HIGH** | Reclassified MANDATORY; applicability rule removed; ADR-0006 wording corrected. Verified *operation* on PostgreSQL is not a canonical requirement and remains unregistered |

| F-0008 | **The correction repeated the defect it was correcting.** While building the Phase 0B deliverable matrix to verify F-0006 was fixed, the "canonical Windows clean-test baseline definition" row was mapped to `ARCHITECTURE.md` without checking, producing a false PASS. The definition existed only in the canonical source document; no Phase 0B artifact defined it | grep verification of the matrix's own claim, immediately after the matrix reported 11/11 | **HIGH** | Created `docs/canonical/CLEAN_TEST_BASELINE.md`. Matrix re-run against verified paths |

### Failure analysis

F-0002 is the most instructive. The register exists precisely so coverage claims stop being assertions, and the first draft of its own summary was an unverified assertion. The general lesson, applicable to every later phase: **any number that appears in a report must be produced by a command whose output is recorded, never by recollection.** This is already required by Phase Gate Checker check C3; F-0002 demonstrates why C3 must also apply to counts, not only to test exit codes.

F-0001 shows that a machine-readable artifact is not machine-readable until something has actually parsed it. The parse is now part of the evidence record rather than an assumption.

**F-0005, F-0006 and F-0007 are the most serious failures of Phase 0, because the internal audit passed while all three were present.** All three are canonical traceability defects — a mandatory requirement marked closed without its evidence, five required deliverables absent, and a classification that would have excused an unconditional requirement. The 29-check internal audit did not catch any of them because every check tested the artifacts against *each other* rather than against the canonical deliverable lists and the canonical requirement text.

The corrective rule, now reflected in Phase Gate Checker check C2: **a phase audit must reconcile the phase report against the canonical deliverable list item by item, and every requirement claimed closed must name the artifact that closes it.** Self-consistency among generated artifacts is not evidence of canonical conformance. This is the concrete justification for the canonical rule that the implementing actor is not the acceptance authority.

**F-0008 is the sharpest evidence in this log.** The deliverable matrix built specifically to prove F-0006 was fixed itself asserted a mapping without verifying it, and reported 11/11 while one deliverable did not exist. The correction reproduced the defect. Strengthened rule, now binding on the Phase Gate Checker: **a deliverable matrix must resolve each claimed location by file existence and content probe, and the probe result must be recorded — a mapping asserted by the author is not a check.** Applies equally to every future phase report.

F-0004 is the most dangerous of the first four because it was silent. The files existed on disk, the phase looked complete, and nothing errored — the canonical build-state tree simply would not have been committed. It was caught only because the expected file count was compared against `git status` rather than against the filesystem. Generalised rule for later phases: **an artifact is not delivered until git reports it as tracked**; presence on disk is not delivery. This is now part of Phase Gate Checker check C1 (report completeness must be verified against version-controlled state, not the working directory).

## Prior phases

| ID | Failure | Phase | Resolution |
|---|---|---|---|
| F-0000 | Canonical set contained 9 BLOCKER and 16 HIGH contract defects | canonical repair (pre-Phase 0) | Repaired in commit `079c925`; three further defects were introduced by the repair itself and caught in its own audit (escape-hatch survival, MS/VDC fuzzing contradiction, undefined "clean Windows"), all fixed before that commit |

## No test failures

No test suite exists yet. There are no failing tests to report. This is NOT_APPLICABLE, not PASS.
