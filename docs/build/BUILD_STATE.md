# BUILD STATE — ARKALI GENESIS v2

**Current state:** **PHASE 7 MACHINE-ACCEPTED. PHASE 8 UNLOCKED — IN PROGRESS, NOT ACCEPTED (Package 1 of 3 complete).**

**Phase 8 Package 1 (C-21 worker contract + worker declarations).** `execution.scheduler` now holds the C-21 declaration: `worker_vocabulary` parses the seven canonical worker classes and the six declaration dimensions from `EXECUTION_AND_CAPABILITY.md` §4 at call time, and `worker_contract` validates and holds declarations under an injected PEP. **Neither list is transcribed into code** — a control asserts the parser contains none of what it parses, and a second reconciles the canonical prose, the single binding table, the pydantic model and `docs/contracts/worker.md` in all directions. Canonical spelling is exact: `Agent`, `build_test`, `local-ai` and `computer use` are all refused, because a second spelling is a second vocabulary. **Tiers and isolation properties are asked of `control.isolation`, not copied** — rank 3 depending on rank 1, so no sibling edge was needed and an unknown tier raises that context's own `TrustTierViolation` unchanged.

**C-21 is INT, and Package 1 is honest about what that excludes.** No table, no migration, no ORM record, no engine, no session, no SQL, and no state machine — the canonical count stays at **12** and no machine names a worker or a scheduler. **No admission decision exists**: capability resolution, isolation composition and resource budget are all Package 2, and a control derives the scheduler's public operations and rejects any admission-, queue-, priority- or fairness-shaped name. Capability activation is Phase 9B and is not queried at all; failure-domain isolation is `ARK-REQ-0354` at **Phase 31** and is named as NOT CLAIMED. `execution.scheduler` imports no `execution.durable` module and names no C-19 concern, asserted from both sides.

**A real budget fired and was answered by decomposition, not an exception.** `kernel.contracts.errors` was already at `max_fan_in_per_module` (15), so the scheduler's error module would have been the sixteenth importer. Under ADR-0008 the abstract base layer — `ArkaliError`, `ContractViolation`, `GovernanceStateError`, `AuthoritativeSourceError` — moved to `kernel.contracts.error_base`, which `errors.py` re-exports, so **no existing call site changed** and the seam is the real one the module's own closing comment already described: what other contexts *derive from* versus what they *catch*. No GATE 8 exception was requested or authored. Orchestration depth is unchanged at **4 of 4**.

**F-0041 was found, opened, repaired and verified within the package.** Two governed phase titles disagreed with the canonical matrix — Phase 8 (`Execution Scheduler + Worker Contract`) and Phase 6 (`Artifact / Evidence Plane`) — because both were transcribed rather than derived, and nothing compared them. The new control reconciles **every** phase both documents name, and found the Phase 6 drift that was not being looked for. MEDIUM: `PhaseStatus.title` is consumed by no acceptance decision, so no accepted phase relied on it.

**Package 1 discharges no requirement, and none was claimed.** The register assigns Phase 8 **zero** `ARK-REQ` entries, so cumulative verified stays at **80**. No traceability record, no phase report and no gate run exist for Phase 8.

**Phase 7 Package 1 (C-19 persistence foundation).** `execution.durable` now holds the durable job record, its idempotency identity and the checkpoint record, with migration `0005_durable_job`. Two identities, one store: `job_id` is the primary key and (`job_type`, `idempotency_key`) is a named unique constraint, so a repeated submission resolves to the existing job across an engine dispose/reopen and cannot create a second one. Checkpoint ordering *is* identity — the primary key is (`job_id`, `sequence`) — and checkpoints refuse both update and delete. The canonical `Job` machine delivered in Phase 3 remains the sole transition authority; the store writes no state literal and no transition table, asserted structurally. Every governed operation passes an injected PEP under `READ_FILE`/`WRITE_WORKSPACE_FILE`, and a real PDP loaded from a denying authority map proves a refusal prevents the write. The clock is injected, so no test sleeps.

**The Phase 4 durable-surface tripwire fired as designed and was replaced, not weakened.** `test_surfaces_not_yet_built_are_still_absent` asserted no module existed under `execution/durable`; the first real module made it fail, naming its own obligation — "must be brought under a real PEP with runtime evidence". That obligation is now met, and the assertion is replaced by a stronger live control that derives which execution packages are built and requires each of them to consult a PEP, so it keeps failing for every unenforced package added later instead of going quiet. Same precedent as Phase 5 Package 4; not a finding, because nothing was defective.

**The Package 1 change set is PROTECTED_CORE** by `select_profile` from its own paths — member `control.architecture`, because completing the `refusal.py` decomposition that the kernel error fan-in budget demanded touches `authority_map.py` and `gates/runner.py`. All three canonical categories were executed at exit 0: *security review* (188), *adversarial review* (479 plus both negative-control validators) and *full regression* (1404 passed, 13 skipped).

**Phase 7 Package 2 (durability semantics).** `job_execution_attempt` records one row per execution attempt — owner, `started_at`, `heartbeat_at`, an absolute `deadline_at`, and `ended_at`/`outcome` when it closes — with migration `0006_durable_execution`, which also records `max_attempts` and `attempt_timeout_seconds` on the job. **Retry accounting is rows, not a counter**: the count is `count(job_execution_attempt)`, so it cannot be reset by restarting a process, set by a caller, or drift from what happened, and the primary key (`job_id`, `attempt`) is the concurrency backstop rather than a service check. The deadline is an absolute instant, so a restart cannot move the timeout basis. A failure disposes through the canonical machine: `RUNNING → FAILED`, then `RECOVERABLE` while the recorded bound leaves an attempt and `DEAD_LETTER` when it does not. `DEAD_LETTER` has no outgoing transition and `CANCELLED` is reachable only from `RUNNING`, so "cannot be silently retried" and "a queued job cannot be cancelled" are properties of the canonical relation rather than of code. A stale owner cannot heartbeat, complete or fail an attempt, and a closed attempt cannot be written again. Timing out twice is idempotent and a deadline that has not passed is refused.

**The Package 2 change set is NORMAL** by `select_profile` — it touches no Protected Core context. The battery was run in full regardless: full regression 1447 passed / 13 skipped, security 188, structural+governance 489, mypy strict clean over 124 modules, 8 gates PASS over **82** edges, 9 budgets no violation.

**Package 2 stopped where Package 3 begins.** It entered no `RESUMING`, ran no recovery sweep, and implemented no pause/resume or `supports_pause` registry. What it recorded (`heartbeat_at`, `deadline_at`, a `RECOVERABLE` disposition) is exactly what Package 3's recovery reads.

**Phase 7 Package 3 (job-type registry, pause/resume, crash recovery).** `durable_job_type` is the registry `ARK-REQ-0060`'s Appendix A rule reads — `job_type.supports_pause == true` — with migration `0007_job_type_registry`, which also adds `heartbeat_timeout_seconds` to the job. **The canonical relation was read before any code was written, and it decided the routes.** `RESUMING` has exactly two predecessors, `PAUSED` and `RECOVERABLE`, so pause and crash recovery share one lifecycle meaning because the machine says so; and `RUNNING → RECOVERABLE` is **not declared** and `evaluate` refuses it, so recovery travels `RUNNING → FAILED → RECOVERABLE → RESUMING` — the disposition Package 2 already owns, composed rather than repeated. `EXECUTION_AND_CAPABILITY.md` §3 names the states a crashed job resolves *to*; `STATE_MACHINES.md` §3 owns the edges it travels, and the two agree once the route is derived rather than assumed. **Nothing was added to the canonical machine.**

**Pause suspends; recovery disposes.** A paused job keeps its open attempt, its owner, its absolute deadline and its position in the retry budget — closing it would consume an attempt and pausing is not failing, while extending its deadline would reset the timeout basis the job was admitted under. A crashed job's attempt is closed, which is what makes the departed owner unable to act: a returning zombie worker cannot heartbeat, complete or fail it. A **paused** job is never swept however silent, because the sweep selects `RUNNING` — a filter that is load-bearing, not tidy. The sweep is idempotent by construction rather than by a guard, stops at `RESUMING` and starts nothing: choosing who runs a job next is `execution.scheduler` at Phase 8.

**F-0036 was found, opened, repaired and verified within the package.** Package 2's `heartbeat_expired` resolved to a comparison against `deadline_at` and never read `heartbeat_at` at all — proven by AST against the untouched tree before anything was edited. The name promised silence since the last proof of life; the behaviour measured elapsed work. Package 2 was unharmed because both callers meant timeout, but the canonical crash-recovery rule keys on the heartbeat, so consuming the name as written would have swept live workers and left dead ones holding their jobs. MEDIUM; no accepted phase relied on it.

**The Package 3 change set is NORMAL** by `select_profile` from its own paths — no Protected Core member touched, no unresolved path. The battery was run in full regardless: full regression **1535 passed / 13 skipped**, mypy strict clean over **126** modules, 8 gates PASS over **86** edges, 9 budgets evaluated. **14 mutations injected, 14 caught**, each verified to fail its *intended* control rather than incidentally. A real budget fired — `test_durable_recovery.py` reached 440 logical lines — and was answered by decomposition under ADR-0008 along a real seam (decide correctly / survive a restart), not by an exception.

**Phase 7 Package 4 (the enqueue surface for ARK-REQ-0027).** `POST /api/jobs` persists durable work through C-19 and returns a durable reference; `GET /api/jobs/{job_id}` resolves one. **The guarantee is architectural, not a latency budget** — the register gives `ARK-REQ-0027` `arch` evidence, and what is asserted is that after the response the work demonstrably has *not* started: the job sits in the state the canonical machine declares initial, with **zero** execution attempts and zero checkpoints. A handler that had run the job could not leave that state. The forbidden call set is **derived from `JobExecution` and `JobRecovery` themselves**, so a method added to either later is covered without editing a control. `202 Accepted` is the honest status: the request was accepted and the processing has not completed, and it avoids inventing a created-versus-existing distinction that C-19's persisted idempotency makes irrelevant. Idempotency is not reimplemented — a repeated `(job_type, idempotency_key)` resolves to the recorded job across a full application restart, which an in-memory cache could not do. The route builds no engine, issues no query, writes no lifecycle state and names no scheduler, worker, dispatch or provider concept. **The job-type registry is not an admission gate:** an undeclared type enqueues, because requiring registration to submit would be admission control and that is C-21 at Phase 8.

**The surface was decomposed before it was written, not after a gate fired.** `app.py` and `error_mapping.py` were each already at `max_contexts_touched_by_module` (3), measured first, so the routes went into `jobs.py` and the durable error table into `job_error_mapping.py` under ADR-0008. **`max_orchestration_depth` is now 4 of 4** — `surfaces.command → execution.durable → control.policy → kernel.contracts` — at its ceiling and not over it. The next package that adds a context hop to that chain will breach it and must decompose rather than ask for an exception.

**Three findings were opened and closed, two of them pre-existing Phase 5 defects this package exposed.** F-0037: a contract control assumed every backend route was also a browser-slice route, which expired on the repository's first backend-only route; routes now declare their audience and the control reads it off the live document. F-0038: one durable timestamp had two wire representations, aware or naive depending on whether the row was still in the session — reproduced on the Phase 5 routes alone. F-0039: `PolicyDenied` mapped to 403 but was unreachable from any route because `guard()` runs before the `try`, so a real denial surfaced as HTTP 500 — also reproduced on Phase 5 alone, and the control that should have caught it asserted the table rather than the route. All three MEDIUM; none failed open.

**Phase 7 Package 5 (final integration, evidence, traceability, acceptance).** The composed journey drives one durable job through its whole life across **six separate runtimes** on one real SQLite file: declared job type, enqueue through the real HTTP API, execution with ownership and heartbeat, a checkpoint, pause and resume, a full restart, recovery from an expired heartbeat, a second attempt, completion. Real fault injection at the available tier covers process loss with persisted `RUNNING` state, heartbeat expiry seen by a process that never watched the job start, a returning zombie owner, a failed transaction, a duplicate attempt refused by the primary key, retry exhaustion to `DEAD_LETTER`, timeout while the worker still reports, and sweep idempotency across restarts. **T12, `ARK-REQ-0327` and Phase 31 are named as NOT CLAIMED**, and a control derives from the register that `ARK-REQ-0327` is not Phase 7's to discharge. Phase 7 evidence is recorded through the Phase 6 C-14/C-15 authorities unchanged — no second evidence mechanism, no Phase 13 graph.

**Fifteen anti-vacuity cases and eight false-discharge variants were proven to fail before the gate ran.** Every critical Phase 7 property was broken in the shipping source and the control that claims to protect it rejected the break; every defective traceability shape was rejected by check C6, and the real record was restored byte-for-byte with its digest re-verified.

**PHASE 7 IS MACHINE-ACCEPTED** on its **first** gate submission: verdict `PHASE_ACCEPTED_BY_MACHINE`, progression PERMITTED, recorded in `docs/acceptance/phase_7_report.json` and `phase_7_traceability.json`. C1–C6 PASS; **PROTECTED_CORE COMPLETE** — the profile derived as PROTECTED_CORE from the phase's own changed paths (member `control.architecture`, from Package 1's kernel-error decomposition), with security review, adversarial review and full regression all at exit 0; RESCORING NOT_APPLICABLE; FINDINGS, PREREQ (2/2) and all 8 architecture gates PASS over **91** edges; HUMAN_GATE NOT_APPLICABLE. **ARK-REQ-0003, 0027, 0059, 0060 and 0061 are all DISCHARGED.**

**Phase 7 is the first phase to discharge a CONDITIONAL requirement, so two counts now differ and both are recorded.** Of the five, four are MANDATORY (0003, 0027, 0059, 0061) and one is CONDITIONAL and **APPLICABLE on its merits** (0060 — its Appendix A rule is now mechanically evaluable and evaluates true against persisted data, rather than being APPLICABLE by governing rule 7's unevaluable default). Cumulative discharged rises 75 → **80**; MANDATORY verified rises 75 → **79**. No applicability waiver was requested or granted.

Phase 5 is accepted and unchanged. Phase 6 was delivered in three atomic packages and accepted on its **first** gate submission: verdict `PHASE_ACCEPTED_BY_MACHINE`, progression PERMITTED, recorded in `docs/acceptance/phase_6_report.json` and `docs/acceptance/phase_6_traceability.json`. C1–C6 PASS; PROTECTED_CORE **COMPLETE**; RESCORING NOT_APPLICABLE (no prior acceptance record); FINDINGS, PREREQ and all eight architecture gates PASS; HUMAN_GATE NOT_APPLICABLE — the matrix Gate column for Phase 6 is empty, and `evidence.audit` being Protected Core does not invent one. **Re-running the gate for Phase 6 now returns `AWAITING_RESCORING_AUTHORITY`; that is GOV-001 working, not a regression.**

**Package 1 (C-14).** `evidence.artifact` holds the artifact descriptor, provenance record and parent edges. Identity *is* the content address, derived from the bytes and never supplied. Artifacts and provenance are immutable by ORM refusal; a tampered blob is detected and never repaired. Blob writes are PEP-governed under `WRITE_WORKSPACE_FILE`. C-12 was not touched.

**Package 2 (C-15).** `evidence.audit` — **Protected Core** — holds the append-only evidence chain: `record_hash` is a digest over every field *including* the predecessor's digest, so the chain is a real hash chain and `verify()` **recomputes** rather than reading any stored flag. Update and delete are both refused at the ORM; the public authority is `append/get/require/head/records/verify/superseded_by` with no amend or delete escape. Supersession appends and preserves. A record must name a requirement the canonical register declares and an artifact C-14 actually registered.

**The two evidence contexts share a mechanism, not an authority.** The content-address primitive moved to `kernel.contracts` so both siblings could reach it at rank 0; `allow_same_layer` stays false, no exemption was widened, and `test_live_repository_uses_no_exempt_edge` passes. Artifact linkage is enforced by the persisted foreign key rather than by importing the sibling's ORM record.

**The Package 2 change set is PROTECTED_CORE** by `select_profile` from its own paths — members `control.architecture` and `evidence.audit`. All three canonical categories were executed at exit 0: *security review* (185), *adversarial review* (413 plus both negative-control validators) and *full regression* (1293 passed, 13 skipped).

**Package 3 (integration, evidence, traceability, acceptance).** The two contracts were proved to compose as one Evidence Plane on real persistence: bytes registered through C-14, evidenced through C-15 against a real register requirement, the engine disposed, a fresh engine opened over the same SQLite file and blob root, the artifact resolved, its bytes re-verified against their content address, the record re-read, the chain recomputed, and a superseding record appended whose predecessor is proven unchanged and whose chain still verifies after a further reopen — four separate engines in one journey, asserted. Provenance evidence records every item `VDC §Provenance` and `MS §Artifact Fabric` name and re-verifies the binding to the content address after reopen. Graph-readiness asserts only that Phase 6 writes data Phase 13 could use; it builds no graph and computes no coverage.

**ARK-REQ-0004, ARK-REQ-0057 and ARK-REQ-0349 are DISCHARGED**, each SATISFIED with a named implementation and a named evidence source, reconciled by check C6. C-15 has no register row of its own and is mapped explicitly onto ARK-REQ-0004, so the audit half is traced rather than merely implemented. Cumulative verified rises 72 → **75**.

**F-0033 was found, opened, repaired and verified before acceptance.** Running the T11 tier standalone — the way this phase's report records it — showed `alembic/env.py` holding one table out of seven as its autogenerate target, because `PersistenceBase.metadata` is populated by import side effect. Autogenerate treats an unseen table as removed, so the tool was configured to propose dropping six real tables. MEDIUM: every migration in the chain is hand-written, none was autogenerated, and the comparison control failed in the **detecting** direction, so no defective schema was ever produced and Phase 5's acceptance is unaffected.

**Canonical source commit:** `079c925996034017855fb9d1f1fa532077d7e86d`
**Accepted Phase 0 candidate:** `007ebf6e9275fa99d932022004440b1b869701d4`
**HUMAN GATE 1:** ACCEPTED — record `HGR-001` in `docs/acceptance/HUMAN_GATE_RECORDS.md`
**Last updated by:** Phase 8 Atomic Package 1 (C-21 worker contract and worker declarations; `kernel.contracts.error_base` decomposition under ADR-0008; F-0041 phase-title reconciliation)
**Governance errata and rulings:** ERR-001 (closes F-0015) · **ERR-002** (closes F-0018 — Plugin `REMOVED` is terminal) · **ERR-003** (closes F-0020 — architecture-budget measurement contract) · **ERR-004** (confirms F-0024, orders remediation) · **GOV-001** (superseding re-acceptance rule; ratifies the Phase 4 re-acceptance) — see `docs/acceptance/HUMAN_GATE_RECORDS.md`

---

## Phase status

| Phase | Title | Status |
|---|---|---|
| 0A | Canonical Architecture | **ACCEPTED** |
| 0B | Governance & Executable Contracts | **ACCEPTED** |
| 0 | Acceptance package (0A + 0B) | **ACCEPTED — HUMAN GATE 1 granted** |
| 1 | Repository Bootstrap | **MACHINE-ACCEPTED** (validator 12/12, suite 7/7) |
| 2 | Foundation + Contracts + Phase Gate Checker | **MACHINE-ACCEPTED** (66 tests, 8 gates, mypy clean) |
| 3 | Formal State Machines + Capability Graph Schema | **MACHINE-ACCEPTED** (12 machines, C-13 schema, 444 new tests) |
| 4 | Security + Governance + Isolation Backends | **MACHINE-ACCEPTED** (re-accepted after the ERR-004 remediation; the defective first revision is retained as evidence) |
| 5 | Persistence + Project Registry + Minimal Backup/Restore | **MACHINE-ACCEPTED** (verdict `PHASE_ACCEPTED_BY_MACHINE`; C1–C6 PASS, PROTECTED_CORE COMPLETE. Five atomic packages; 7/7 requirements SATISFIED and discharged under C6. First real T10: 9 browser tests in Chromium against the production build, a live API and a real SQLite file) |
| 6 | Evidence Plane + Provenance + Artifact Store (C-14, C-15) | **MACHINE-ACCEPTED** (verdict `PHASE_ACCEPTED_BY_MACHINE` on first submission; C1–C6 PASS, PROTECTED_CORE COMPLETE over members `acceptance.engine`, `control.architecture`, `evidence.audit`. Three atomic packages; 3/3 requirements SATISFIED and discharged under C6. Migrations `0003_artifact_provenance` and `0004_audit_record`) |
| 7 | Durable Job + Workflow Core (C-19) | **MACHINE-ACCEPTED** (verdict `PHASE_ACCEPTED_BY_MACHINE`, progression PERMITTED, on the **first** submission; `docs/acceptance/phase_7_report.json`, `phase_7_traceability.json`). Five atomic packages: the C-19 durable-job persistence foundation, the durability semantics, the job-type registry with pause/resume and the crash-recovery sweep — migrations `0005_durable_job`, `0006_durable_execution`, `0007_job_type_registry` — the `ARK-REQ-0027` enqueue surface under `surfaces.command`, and final integration with real fault-injection evidence. C1–C6 PASS; PROTECTED_CORE **COMPLETE** (member `control.architecture`); RESCORING NOT_APPLICABLE; FINDINGS, PREREQ (2/2) and all 8 architecture gates PASS; HUMAN_GATE NOT_APPLICABLE. **5/5 requirements discharged.** Both prerequisites, Phases 5 and 6, are accepted; the matrix Gate column for Phase 7 is empty, so no human gate applies. *(This cell's prose is the exact wording F-0034 mis-read as accepting the phase; it is written plainly because the parser now reads the declared state and ignores prose — this row is the live proof.)* |
| 8 | Resource Scheduler + Worker Contracts (C-21) | **UNLOCKED — IN PROGRESS, NOT ACCEPTED** ← current work. Unlocked by Phase 7's machine acceptance, which the gate recorded as progression PERMITTED. **Package 1 (C-21 worker contract + worker declarations) is complete**; Packages 2 (admission decision) and 3 (integration, evidence, gate) are not started. No requirement is discharged — the register assigns Phase 8 none. |
| 9 … 37 | all subsequent phases | NOT_STARTED — reachable in canonical order; next human gate is GATE 2 at Phase 23 |

## What exists

- Canonical document set (4 files), unmodified by Phase 0.
- **Phase 0A architecture package (8):** `ARCHITECTURE.md`, `SECURITY_ARCHITECTURE.md`, `STATE_MACHINES.md`, `EXECUTION_AND_CAPABILITY.md`, `CONTRACT_INVENTORY.md` (36 families), `VERIFICATION_ARCHITECTURE.md` (test architecture + evidence graph strategy), `IMPLEMENTATION_DEPENDENCY_MATRIX.md`, `CONTRADICTION_ANALYSIS.md`.
- **Phase 0B governance package (5):** `REQUIREMENT_REGISTER.md` (313 entries), `AUTHORITY_MAP.yaml` (machine-readable, parses), `GOLDEN_REPAIR_CORPUS_DEFINITION.md`, `PHASE_GATE_CHECKER.md`, `ADR_INDEX.md` (9 ADRs, all **ACCEPTED** under HUMAN GATE 1, now immutable).
- Build state artifacts (this file and siblings), `EVIDENCE_INDEX.md`, `HUMAN_GATE_RECORDS.md`.
- **Executable governance (Phase 2):** `backend/arkali/` now contains 15 implementation modules across 8 bounded contexts — error taxonomy, honest states, correlation envelope, persistence schema contract, requirement register parser, authority map parser, 8 architecture gates, phase report, gate verdict and the deterministic Phase Gate Checker. Entry point: `scripts/run_phase_gate.py`.
- **Validation tooling (5):** `scripts/check_phase_graph.py`, `check_phase_graph_negative.py`, `check_phase0_deliverables.py`, `check_repository_structure.py`. Validators, not application source code — they analyse documents and repository structure.
- **Phase 1 repository bootstrap (candidate, not accepted):** `backend/` (31 bounded-context packages + 9 layer groupings, `pyproject.toml`, `tests/`, `alembic/versions/`), `frontend/` (workspace config + real `package-lock.json`), `src-tauri/`, `golden/`, `release/` roots.

## What does not exist

- **No application capability beyond the Command Center slice.** One FastAPI application (`surfaces.command`, seven routes) and one React page (the Project Registry) exist. No other module, route, dashboard or surface does.
- **No Python lockfile exists** (no lock tool on this machine). Node dependencies **are** installed: `npm ci` from the tracked `package-lock.json`, then the Vitest/Testing-Library tier, `@playwright/test` and `@types/node` added through real npm tooling, which updated `package.json` and `package-lock.json` as `INSTALL_DEPENDENCY`/`LOCKFILE_BOUND` requires. Nothing was hand-written into the lockfile. The Chromium runtime was downloaded by `npx playwright install chromium` and is not vendored into the repository.
- **No browser/E2E evidence beyond the Project Registry, and none outside Chromium.** T10 is configured and green for one capability: 9 Playwright tests against the production build, a live API and a real SQLite file. Firefox and WebKit are not installed and no cross-browser claim is made. No other capability has a browser journey, because no other capability has a frontend. The 23 jsdom component tests are component evidence and are never reported as T10.
- **The first execution surface now exists.** Phase 4's "no execution surface" statement is superseded for `surfaces.command` only: every route enforces through the Phase 4 PEP and is audited. Of the other five canonical paths, **`durable` (Phase 7) and `scheduler` (Phase 8 Package 1) now exist and both enforce through a real PEP** — the derived control in `test_pep_and_bypass.py` requires it of every execution package that is built, and passes. **`sandbox`, `workflow` and `operations` remain absent**, and the same control asserts that absence rather than assuming it. End-to-end bypass resistance across all six (ARK-REQ-0325, 0347) is still Phase 31 and is not claimed.
- **No Recovery Supervisor, Stable rollback or `ROLLBACK_STABLE` capability.** Phase 5 delivered *minimal* backup/restore only; the Supervisor is Phase 22B and `ROLLBACK_STABLE` remains DENY for every actor. `ARK-REQ-0153` and `ARK-REQ-0335` **are discharged** — Phase 5 is accepted and its traceability record claims both SATISFIED under C6 — but what they discharge is the minimal capability, not the Supervisor.
- No Phase 20 migration-safety workflow: restore requires an exactly matching schema revision rather than migrating across one.
- **The Evidence Plane's storage and integrity contracts now exist** (Phase 6, accepted): `evidence.artifact` registers artifacts by the address of their bytes with provenance and parent edges, and `evidence.audit` holds the append-only evidence chain whose digests are recomputed on every verification. A revision's `provenance_ref` resolves to an artifact. What still does **not** exist is **evidence-graph computation, coverage and verdicts** (C-16, Phase 13) — no coverage number is derived from any evidence record and none is claimed — and release manifests with cryptographic hashes, SBOM and signing (C-31, Phase 26). No Phase 6 capability is reachable from any execution surface: the Command Center API exposes no artifact or evidence route, so the Evidence Plane has no browser, e2e or runtime evidence and none is claimed. There is no artifact deletion, garbage collection or compaction, by design.
- **One acceptance guard is weaker than Phase 6's own traceability record.** C-15 is mapped onto ARK-REQ-0004 in full, but the contract behind check C6 requires only that a SATISFIED claim *name* an implementation and an evidence source — it has no per-contract granularity. Proven mechanically, not assumed. No control was added, because no accepted phase's traceability record names a contract id at all and a repository-wide rule demanding one would retroactively invalidate Phases 2–5; strengthening the traceability contract is an Acceptance Engine change and belongs to Phase 13.
- No runtime database is committed. `.gitignore` excludes `*.db`, `*.db-wal`, `*.db-shm`; migrations are committed.
- **No Rust/Tauri manifest** — toolchain absent; nothing fabricated.
- No Phase Gate Checker implementation (Phase 2).
- No contract **schema files** — the 36 families are inventoried (Phase 0A); schemas are Phase 2 (DEF-008).
- No **instantiated** Golden Repair corpus. The definition is delivered (Phase 0B, ARK-REQ-0090/0091); instantiation is ARK-REQ-0187/0188 at Phase 30 and is **NOT_APPLICABLE** until an accepted Golden Product exists — it is not a closed requirement.

## Honest state of Phase 0 verification

| Item | State | Reason |
|---|---|---|
| Architecture package produced | PASS | documents exist and are internally consistent |
| Requirement register produced | PASS | 313 entries, 0 duplicates, mechanically counted |
| Phase 0A deliverables vs Build Protocol list | PASS | 16/16, count derived from the canonical list, each content-probed (EV-0005) |
| Phase 0B deliverables vs Build Protocol list | PASS | 11/11, count derived from the canonical list, each content-probed (EV-0005) |
| Phase dependency graph executable | PASS | 9/9, all four edge classes, negative control fails as required (EV-0004, EV-0004N) |
| Golden Repair corpus instantiated | NOT_APPLICABLE | no accepted Golden Product exists; ARK-REQ-0187/0188 open at Phase 30 |
| Authority map machine-readable | PASS | parses; 0 duplicate concern authorities |
| Architecture gates executed | NOT_TESTED | no code exists to analyse; gates run from Phase 2 |
| Phase Gate Checker executed | NOT_TESTED | implemented in Phase 2 |
| Any test suite executed | NOT_APPLICABLE | Phase 0 produces no implementation |
| Provider configured | NOT_CONFIGURED | no provider required or used in Phase 0 |
| Isolation backends probed | NOT_TESTED | probe runs at Phase 4 |
| Human Gate 1 | **ACCEPTED** | granted by the human acceptance authority after independent inspection and independent execution of the validators; record `HGR-001` |

## Cross-session handoff (mandatory maintenance)

`ARKALI_HANDOFF.md` at the repository root is the cross-session bootstrap index.
It is **not an authority** and can never override the canonical set, the
requirement register, the authority map, the accepted ADRs, the human-gate
records, this file, `PHASE_HISTORY.md` or accepted Git history. On disagreement
the repository wins and continuation stops with `HANDOFF_DRIFT`.

**It MUST be regenerated from authoritative repository state after:**

- every machine-accepted phase;
- every Human Gate decision;
- every accepted governance erratum;
- Stable Core promotion;
- any rollback;
- any new BLOCKER or HIGH that changes continuation strategy;
- any change to NEXT EXACT ACTION.

Refresh means re-derive from the repository, never hand-edit to match a
recollection. Verify with `python scripts/check_handoff.py` (exit 0 required).

## Next exact action

**Phase 8 Atomic Package 2 — the admission decision.** Package 1 delivered the C-21 declaration; Package 2 decides admission and nothing else. `EXECUTION_AND_CAPABILITY.md` §4 requires **all three**: the capability resolves other than `NOT_CONFIGURED`, an isolation composition satisfies the declared tier, and resource budget is available.

**Expect to be unable to admit, and say so honestly.** Capability Graph *activation* is **Phase 9B**; §1 of the same document states that before activation every query returns `NOT_CONFIGURED` — a determinate answer, never a stub — and names `execution.scheduler` at Phase 8 as a consumer that must handle it **and must not cache a capability verdict**. A Package 2 that cannot admit any job is behaving correctly. Never fake a PASS to demonstrate successful scheduling.

**The boundaries Package 1 established must hold.** No `execution.scheduler` → `execution.durable` import in either direction and no sibling edge; no durable-job read or mutation; no persistence, migration or state machine; no queue, priority, fairness or autoscaling; no provider runtime. `control.isolation` remains the tier and property authority, and `execution.durable` remains sole authority for every C-19 concern.

**Three budget facts to carry in.** `max_orchestration_depth` is at **4 of 4** on `surfaces.command → execution.durable → control.policy → kernel.contracts` — a further hop on that chain breaches it and must be decomposed under ADR-0008, never excepted. `kernel.contracts.errors` fan-in is back to **15 of 15** after the `error_base` decomposition, so a context needing a base error type must import `kernel.contracts.error_base`, not `errors`. Phase 8 owns **zero** registered requirements, so Package 3's traceability record is `claims: []` against an empty denominator and cumulative verified stays at **80**.

*(superseded guidance retained for continuity)*

**Begin Phase 8 — Resource Scheduler + Worker Contracts (C-21).** Done for Package 1: `docs/contracts/worker.md`, the parsed worker vocabulary, the PEP-governed declaration authority, and the `kernel.contracts.error_base` decomposition. F-0041 opened and closed.

**Phase 7 Atomic Package 5 — final integration, evidence, traceability, report and acceptance.** Done: the composed durable journey, real fault-injection evidence at the available tier, `phase_7_traceability.json`, `phase_7_report.json` and one gate run returning `PHASE_ACCEPTED_BY_MACHINE` on the first submission.

**Phase 7 Atomic Package 4 — the enqueue surface for `ARK-REQ-0027`.** Done: `POST /api/jobs` and `GET /api/jobs/{job_id}` under `surfaces.command`, persisting durable work through C-19 and returning a reference without executing it. F-0037, F-0038 and F-0039 opened and closed.

**Phase 7 Atomic Package 3 — pause/resume and crash recovery.** Done: the `durable_job_type` registry that makes `ARK-REQ-0060` evaluable, `RUNNING → PAUSED → RESUMING → RUNNING`, and the sweep that resolves a silent `RUNNING` execution through `FAILED → RECOVERABLE → RESUMING`. F-0036 opened and closed.

**Phase 7 Atomic Package 2 — durability semantics.** Done: attempts, heartbeat and execution ownership, bounded retries with row-derived accounting, absolute deadlines, cancellation and dead-lettering.

*(superseded guidance retained for continuity)*

**Begin Phase 7 — Durable Job + Workflow Core (C-19).** Phase 7 is unlocked and not started; the matrix records prerequisites 5 and 6, both accepted, and no human gate.

Before any Phase 7 work, note what Phase 6 deliberately did **not** deliver, so it is not assumed: the evidence **graph** does not exist. No coverage is computed, no requirement verdict is derived and no acceptance conclusion is drawn from any evidence record — that is C-16 and the Acceptance Engine at **Phase 13**. Phase 6 supplies the `Artifact` and `Evidence` nodes and the identifiers a later graph would need, and nothing more.

Out of scope and not to be pulled forward: Phase 13 evidence-graph computation, coverage and verdicts (C-16); provider runtime (9); Capability Graph activation (9B); Recovery Supervisor and `ROLLBACK_STABLE` (22B); Stable Core promotion (23); release manifests, SBOM and signing (26); the Golden corpus (30); T7/T8/T12 (31); clean-baseline packaging (36).

*(superseded guidance retained for continuity)*

**Phase 6 Atomic Package 3 — Final Integration + Evidence + Traceability + Phase Acceptance.** Done: the integration evidence, `phase_6_traceability.json`, `phase_6_report.json` and the gate run, which returned `PHASE_ACCEPTED_BY_MACHINE`.

*(superseded guidance retained for continuity)*

**Begin Phase 5 — Persistence + Project Registry + Minimal Backup/Restore.** Phase 5 is unlocked and not started.

*(superseded guidance retained for continuity)*

**Remediate F-0024 before any Phase 5 work.** Done: `ARK-REQ-0111` implemented and verified, F-0024 and F-0025 closed, Phase 4 re-accepted. Cumulative verified is **65** again, now genuinely.

*(superseded guidance retained for continuity)*

**Begin Phase 5 — Persistence Foundation.** Phase 5 is unlocked in phase-graph terms but blocked by an open HIGH finding.

*(superseded guidance retained for continuity)*

**Begin Phase 4 — Security + Governance + Isolation Backends.** Phase 4 delivered C-07, C-08, C-09 and C-10; the single PDP and the PEP enforcement contract; Protected Core boundary enforcement; the Secret Vault boundary; Local-Only policy; and the isolation backend availability probe, closing **DEF-003**.

*(superseded guidance retained for continuity)*

**Begin Phase 3 — Formal State Machines + Capability Graph Schema.** Phase 3 delivered the twelve canonical state machines and the Capability Graph schema (C-13). Per ADR-0003 the graph is schema-only until Phase 9B; every capability query returns `NOT_CONFIGURED` before activation.

*(superseded guidance retained for continuity)*

Phase 2 delivers contract definitions C-01, C-03 (definition), C-04, C-17, C-18; the eight architecture gates with their negative-control fixtures; and the deterministic Phase Gate Checker. At that point Phase 0's `NOT_TESTED` items become testable for the first time, and the vacuous dependency-direction check gains real imports to reject.

*(superseded guidance retained for continuity)*

Phase 2 (Foundation + Contracts + Phase Gate Checker) follows, at which point the eight architecture gates and the deterministic Phase Gate Checker become executable and Phase 0's `NOT_TESTED` items become testable for the first time.

From here, normal phases are accepted by machine verdict without human approval. The next human gate is **GATE 2** at Phase 23 (Stable Core promotion), unless a phase reaches GATE 4, 5, 6 or 8 earlier.

## Carried forward

Acceptance of Phase 0 closed no finding other than the gate itself:

- **79 of 303 MANDATORY requirements are verified**, plus **1 CONDITIONAL** requirement (`ARK-REQ-0060`) discharged while APPLICABLE — **80 discharged in total** (5 from Phase 1, 23 from Phase 2, 4 from Phase 3, 33 from Phase 4, 7 from Phase 5, 3 from Phase 6, **5 from Phase 7 of which 4 are MANDATORY**). Phase 7 is the first phase whose discharged set is not entirely MANDATORY, which is why the two figures are stated separately rather than collapsed. The line below is retained as written at Phase 6 and is superseded by this one.
- **75 of 303 MANDATORY requirements are verified** (5 from Phase 1, 23 from Phase 2, 4 from Phase 3, 33 from Phase 4, 7 from Phase 5, 3 from Phase 6), each recorded in its phase's traceability record with a named implementation and a named evidence source. The line below is retained as written at Phase 4 and is superseded by this one.
- **65 of 303 MANDATORY requirements are verified** (5 from Phase 1, 23 from Phase 2, 4 from Phase 3, 33 from Phase 4). All 33 Phase 4 entries were re-derived from the register after F-0024 and each is recorded in `phase_4_traceability.json` with a named implementation and a named control; check C6 refuses any discharge that record does not support.
- **A false discharge can no longer pass.** C6 reconciles the phase report against the phase's traceability record; a requirement in any non-SATISFIED state may not appear in the discharged set.
- **Protected Core changes now carry a stronger profile** from Phase 4 onward (`ARK-REQ-0111`): security review, adversarial review and full regression, each backed by a real execution record. The eight gates now evaluate 41 real cross-context edges.
- **Security is enforced, not described.** One PDP, deterministic and pure; every decision audited including AUTO; unmappable action DENY; `WRITE_STABLE_FILE` DENY for every actor at every tier; Protected Core direct mutation refused. All governed vocabularies are parsed from the authority map — no security module holds a private copy.
- **Host isolation is partial and honestly reported.** TRUST-0/1 satisfiable; TRUST-2/3/4 **UNSUPPORTED** on this host because `NET_EGRESS_CONTROL` (WFP needs elevation) and `KERNEL_ISOLATION` (Windows Sandbox and Hyper-V not enabled) are genuinely unavailable. No Windows feature was enabled to improve the result.
- **No execution surface exists.** Bypass resistance is verified at contract level only; API, UI, agent, workflow, plugin and computer-use are NOT_YET_IMPLEMENTED and are not claimed.
- The twelve canonical state machines are executable and reconciled against `STATE_MACHINES.md` on every run, so the inventory can no longer drift from the code that implements it.
- The Capability Graph exists as schema only. ARK-REQ-0046, 0047 and 0048 remain open at Phase 9B and are **not** claimed by Phase 3.
- The architecture remains a declaration until the Phase 2 gates run against real code (M-P0-2).
- Register exhaustiveness is by construction, not mechanical extraction; Phase 2 reconciles it (M-P0-1).
- 14 MEDIUM and 9 LOW findings remain open in `OPEN_BLOCKERS.md`. Every Phase 3 finding (F-0018 … F-0021) is now **closed**; two by human erratum.
- All **nine** declared numeric architecture budgets are evaluated by the gate under ratified measurement contract 1.0.0 (ERR-003). Max measured complexity **12** of 12; max orchestration depth **3** of 4.
- Every recorded defect remains in `KNOWN_FAILURES.md` as permanent evidence. That file is the authoritative defect ledger; its composition is deliberately **not** mirrored here, because a transcribed count re-rots the moment a defect is added (F-0002, F-0011). Read the ledger. F-0015 is CLOSED by ERR-001 but retained in full.
