# BUILD STATE — ARKALI GENESIS v2

**Current state:** **PHASE 5 MACHINE-ACCEPTED. PHASE 6 UNLOCKED — IN PROGRESS, NOT ACCEPTED.**

Phase 5 is accepted and unchanged. Phase 6 is delivered in atomic packages; **Packages 1 and 2 are complete**.

**Package 1 (C-14).** `evidence.artifact` holds the artifact descriptor, provenance record and parent edges. Identity *is* the content address, derived from the bytes and never supplied. Artifacts and provenance are immutable by ORM refusal; a tampered blob is detected and never repaired. Blob writes are PEP-governed under `WRITE_WORKSPACE_FILE`. C-12 was not touched.

**Package 2 (C-15).** `evidence.audit` — **Protected Core** — holds the append-only evidence chain: `record_hash` is a digest over every field *including* the predecessor's digest, so the chain is a real hash chain and `verify()` **recomputes** rather than reading any stored flag. Update and delete are both refused at the ORM; the public authority is `append/get/require/head/records/verify/superseded_by` with no amend or delete escape. Supersession appends and preserves. A record must name a requirement the canonical register declares and an artifact C-14 actually registered.

**The two evidence contexts share a mechanism, not an authority.** The content-address primitive moved to `kernel.contracts` so both siblings could reach it at rank 0; `allow_same_layer` stays false, no exemption was widened, and `test_live_repository_uses_no_exempt_edge` passes. Artifact linkage is enforced by the persisted foreign key rather than by importing the sibling's ORM record.

**The Package 2 change set is PROTECTED_CORE** by `select_profile` from its own paths — members `control.architecture` and `evidence.audit`. All three canonical categories were executed at exit 0: *security review* (185), *adversarial review* (413 plus both negative-control validators) and *full regression* (1293 passed, 13 skipped).

**ARK-REQ-0004, ARK-REQ-0057 and ARK-REQ-0349 are NOT discharged.** No Phase 6 report, no traceability record, no gate run. Cumulative verified stays at **72**.

**Canonical source commit:** `079c925996034017855fb9d1f1fa532077d7e86d`
**Accepted Phase 0 candidate:** `007ebf6e9275fa99d932022004440b1b869701d4`
**HUMAN GATE 1:** ACCEPTED — record `HGR-001` in `docs/acceptance/HUMAN_GATE_RECORDS.md`
**Last updated by:** Phase 6 Atomic Package 2 (C-15 audit / evidence integrity chain)
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
| 6 | Artifact / Evidence Plane (C-14, C-15) | **UNLOCKED — IN PROGRESS, NOT ACCEPTED** ← current work. Packages 1–2 complete: C-14 artifact descriptor + provenance under `evidence.artifact`, and C-15 append-only evidence integrity chain under `evidence.audit` (Protected Core), with migrations `0003_artifact_provenance` and `0004_audit_record`. Package 3 owes final integration, evidence, traceability and the gate. No phase report, no traceability record, no gate run |
| 7 … 37 | all subsequent phases | NOT_STARTED — reachable in canonical order; next human gate is GATE 2 at Phase 23 |

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
- **The first execution surface now exists.** Phase 4's "no execution surface" statement is superseded for `surfaces.command` only: every route enforces through the Phase 4 PEP and is audited. The other five canonical paths — sandbox, scheduler, durable, workflow, operations — remain absent, and end-to-end bypass resistance across all six (ARK-REQ-0325, 0347) is still Phase 31 and is not claimed.
- **No Recovery Supervisor, Stable rollback or `ROLLBACK_STABLE` capability.** Phase 5 delivered *minimal* backup/restore only; the Supervisor is Phase 22B and `ROLLBACK_STABLE` remains DENY for every actor. `ARK-REQ-0153` and `ARK-REQ-0335` **are discharged** — Phase 5 is accepted and its traceability record claims both SATISFIED under C6 — but what they discharge is the minimal capability, not the Supervisor.
- No Phase 20 migration-safety workflow: restore requires an exactly matching schema revision rather than migrating across one.
- **Content-addressed artifact identity now exists** (Phase 6 Package 1): `evidence.artifact` registers artifacts by the address of their bytes, with provenance and parent edges. A revision's `provenance_ref` resolves to one. What still does **not** exist is the audit / evidence integrity chain (C-15, Package 2), evidence-graph computation and coverage (Phase 13), and release manifests with cryptographic hashes (C-31, Phase 26).
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

**Phase 6 Atomic Package 3 — Final Integration + Evidence + Traceability + Phase Acceptance.**

C-14 and C-15 both exist and are controlled. What remains:

1. **Integration evidence** that the two halves work together as the Evidence Plane the register's `ARK-REQ-0004` names — an artifact registered by C-14 and evidenced by C-15, end to end.
2. **`docs/acceptance/phase_6_traceability.json`** — three claims (0004, 0057, 0349), each SATISFIED only with a named implementation and a named evidence source. C-15 has no register row of its own, so it must be mapped explicitly to `ARK-REQ-0004` or the audit half discharges nothing.
3. **`docs/acceptance/phase_6_report.json`** (C-17, 17 fields), carrying the three Protected Core categories as real executions — the profile applies because `evidence.audit` and `control.architecture` were touched.
4. **`python scripts/run_phase_gate.py 6 7`**, and record the acceptance only if the verdict is genuinely `PHASE_ACCEPTED_BY_MACHINE`.

Out of scope and not to be pulled forward: Phase 13 evidence-graph computation, coverage and verdicts (C-16); the Acceptance Engine; provider runtime (9); Capability Graph activation (9B); durable jobs (7); Recovery Supervisor and `ROLLBACK_STABLE` (22B); Stable Core promotion (23); release/SBOM (26); T7/T8/T12 (31).

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
