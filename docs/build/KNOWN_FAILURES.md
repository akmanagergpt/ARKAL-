# KNOWN FAILURES — ARKALI GENESIS v2

Failures are recorded whether or not they were caught before commit. A defect found and fixed inside the same phase is still a defect and is logged here.

## Phase 0

| ID | Failure | Detected by | Severity | Resolution |
|---|---|---|---|---|
| F-0001 | `AUTHORITY_MAP.yaml` opened with a fullwidth `＃` (U+FF03) instead of ASCII `#`, which would have prevented the machine-readable authority map from parsing at all — the file's entire purpose | Phase 0 self-audit, before commit | HIGH (would have been) | Corrected to ASCII `#`; YAML parse re-verified exit 0 |
| F-0002 | `REQUIREMENT_REGISTER.md` Appendix B asserted 371 entries / 360 MANDATORY without measurement; actual values are 311 / 300 | Mechanical count during self-audit | HIGH (would have been) | Appendix B corrected to measured values; note added that counts are mechanically verified, not asserted |
| F-0003 | `PHASE_GATE_CHECKER.md` §6 contained a non-English word ("содержащее") from a generation slip | Self-audit read-back | LOW | Corrected to "containing" |
| F-0004 | `.gitignore` rule `build/` (Python packaging artifacts) silently excluded the entire canonical `docs/build/` tree — the six state files the Build Protocol requires to be version controlled (ARK-REQ-0221, 0222). Six Phase 0 artifacts were invisible to git | `git status` showed 9 files where 15 were expected; confirmed with `git check-ignore -v` | **HIGH (would have been)** | Added `!docs/build/` + `!docs/build/**` negations immediately after the `build/` rule. Re-verified: all six canonical files tracked, `backend/build/**` and `frontend/dist/**` still ignored |

### Failure analysis

F-0002 is the most instructive. The register exists precisely so coverage claims stop being assertions, and the first draft of its own summary was an unverified assertion. The general lesson, applicable to every later phase: **any number that appears in a report must be produced by a command whose output is recorded, never by recollection.** This is already required by Phase Gate Checker check C3; F-0002 demonstrates why C3 must also apply to counts, not only to test exit codes.

F-0001 shows that a machine-readable artifact is not machine-readable until something has actually parsed it. The parse is now part of the evidence record rather than an assumption.

F-0004 is the most dangerous of the four because it was silent. The files existed on disk, the phase looked complete, and nothing errored — the canonical build-state tree simply would not have been committed. It was caught only because the expected file count was compared against `git status` rather than against the filesystem. Generalised rule for later phases: **an artifact is not delivered until git reports it as tracked**; presence on disk is not delivery. This is now part of Phase Gate Checker check C1 (report completeness must be verified against version-controlled state, not the working directory).

## Prior phases

| ID | Failure | Phase | Resolution |
|---|---|---|---|
| F-0000 | Canonical set contained 9 BLOCKER and 16 HIGH contract defects | canonical repair (pre-Phase 0) | Repaired in commit `079c925`; three further defects were introduced by the repair itself and caught in its own audit (escape-hatch survival, MS/VDC fuzzing contradiction, undefined "clean Windows"), all fixed before that commit |

## No test failures

No test suite exists yet. There are no failing tests to report. This is NOT_APPLICABLE, not PASS.
