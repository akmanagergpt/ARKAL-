# Migration safety sequence — derived contract (Phase 20)

**Owner:** `lifecycle.recovery` (orchestration), `kernel.persistence` (mechanics),
`control.policy` (Apply-step enforcement, unmodified), `acceptance.engine`
(release-blocking check)
**Kind:** INT (no table, no migration, no ORM record of its own)
**Version:** 1.0.0

This document records the executable Phase 20 contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0151`, `ARK-REQ-0152`, `ARK-REQ-0336`,
`ARK-REQ-0337`), `docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md`
section "Migration safety", `docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md`
section "Database / Backup / Recovery", and
`docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md` row 20. It does not
replace those authorities, and it completes rather than redefines C-03
(`docs/contracts/persistence.md`), which explicitly deferred HUMAN_GATE_6 and
the nine-step sequence to this phase.

## 0. Scope of this revision

Three atomic packages, no new C-ID minted (this is C-03's deferred runtime
half, plus an extension of Phase 5's `lifecycle.recovery` authority):

1. `kernel.persistence`: `migrations.run_upgrade` (the real Alembic apply
   mechanic, previously only reachable through test-local duplicates) and
   `migration_impact.py` (an AST-based static analyser flagging
   `op.drop_table`, `op.drop_column` and a raw destructive `op.execute`).
2. `lifecycle.recovery`: `migration_safety_types.py` /
   `migration_safety_steps.py` / `migration_safety.py` —
   `MigrationSafetySequence`, composing the nine VDC steps (Impact, Backup,
   Dry Run, Integrity, Candidate Migration, Application Tests, Apply, Verify,
   Rollback Point) out of Phase 5's `RecoveryService`/`BackupRestore` machine,
   Phase 4's PDP/PEP, and Phase 19's `WorkflowApprovalGate` — all reused
   unmodified.
3. `acceptance.engine`: `check_migration_data_loss_risk`
   (`migration_release_check.py`), wired into the existing check list.

**Not implemented or claimed by this revision:** a second migration authority,
a second backup/restore authority, a thirteenth canonical state machine, a
Stable-mutation path, or genuine PostgreSQL migration evidence (no PostgreSQL
driver is installed on this host; that half is honestly `NOT_CONFIGURED`, not
fabricated).

## 1. The nine steps, and what each one actually proves

| # | Step | Mechanism | On failure |
|---|---|---|---|
| 1 | Impact | `kernel.persistence.migration_impact.analyze_file` over every revision between the target's current applied revision (exclusive) and the requested target (inclusive) | Stops the **whole sequence** — steps 2-9 are recorded `BLOCKED`, not skipped silently |
| 2 | Backup | `RecoveryService.create_backup` (Phase 5, unmodified) | Stops |
| 3 | Dry Run | Restore the pre-migration image into a scratch SQLite file, then `run_upgrade` the scratch copy to the target revision — the real target is never touched | Stops |
| 4 | Integrity | `PRAGMA integrity_check` on the backup image and on the migrated scratch copy | Stops |
| 5 | Candidate Migration | Re-validates the declared chain is linear and forward-only, and that the backed-up revision does not follow the target (`kernel.persistence.migrations`, unmodified) | Stops |
| 6 | Application Tests | Caller-supplied `Callable[[Engine], bool]` run against the migrated scratch copy | Stops |
| 7 | Apply | Gated — see section 2 | Stops (`BLOCKED`, not `FAIL`, when policy or approval refuses) |
| 8 | Verify | Applied-revision check + integrity check + caller-supplied verifier, all against the real target | Stops |
| 9 | Rollback Point | `RecoveryService.prove_by_restore` on the pre-migration backup into a second scratch copy, confirming it restores to the exact pre-migration revision | Terminal; `MigrationSafetyResult.rollback_point_backup_id` records the proven backup id |

Step 1 stopping the entire sequence, not only Apply, is the VDC's own
wording: "Known data-loss risk blocks release" is not scoped to the Apply
step alone. `acceptance.engine`'s independent check (section 3) re-derives
the same property over the whole shipped chain, not over one candidate run.

## 2. Apply-step gating (ARK-REQ-0152)

`APPLY_MIGRATION` is fixed in `AUTHORITY_MAP.yaml` to
`HUMAN_GATE_6_ON_REAL_OR_STABLE_DATA`, and `SECURITY_ARCHITECTURE.md` §2 fixes
it to `ASK_USER` at TRUST-0/1 **unconditionally** — there is no tier at which
this operation class is `AUTO`. The PDP mechanism for this was already
complete at Phase 4 (`pdp.py::_required_gate`); Phase 20 exercises it rather
than building a second one.

Two independent conditions must both hold before Apply mutates the real
target:

1. **A genuine, non-stale human decision.** `WorkflowApprovalGate.
   is_enforced_approval` (Phase 19's `control.policy` authority, reused
   unmodified) refuses an automated actor (`stable_mutation.prohibited_actors`),
   a non-`APPROVED` decision, or an approval whose `approval_revision_hash`
   does not match the resolved target revision.
2. **`targets_real_or_stable_data`.** When `True`, `HUMAN_GATE_6` must already
   appear in `HumanGateSource.accepted_human_gates` (see section 4) — an
   ordinary local approval is never sufficient for real-or-stable-data data on
   its own. When `False` (the shape every automated test in this repository
   uses), condition 1 alone is sufficient.

Neither condition can be supplied by the sequence itself; both are facts the
caller must already hold before calling `run`.

## 3. ARK-REQ-0337: known data-loss risk blocks release

`acceptance.engine.checker.PhaseGateChecker.check_migration_data_loss_risk`
re-derives `migration_impact.analyze_chain` over the **live shipping**
`backend/alembic/versions/` directory on every phase-gate evaluation — never
read from a phase report's own claim, the same discipline C6 already applies
to discharge claims. A flagged revision anywhere in the chain fails the
`DATA_LOSS_RISK` check and therefore blocks phase acceptance
(`PhaseGateChecker._is_blocked`), independent of the Impact-step refusal a
single candidate run performs (section 1, step 1).

## 4. `HumanGateSource`: a `Protocol`, not an import

`lifecycle.recovery` cannot import `acceptance.engine.GovernanceState`
directly: `acceptance.engine`'s own context-dependency chain
(`acceptance.engine -> control.specification -> control.architecture ->
kernel.contracts`) already measures 4 of 4 against `max_orchestration_depth`,
and attaching `lifecycle.recovery` in front of it would measure 5. Instead
`migration_safety_types.HumanGateSource` is a `runtime_checkable` structural
`Protocol` exposing one property, `accepted_human_gates`. `GovernanceState`
satisfies it without either module knowing about the other; the composition
root (currently `test_migration_safety.py`, later any real surface) supplies
a real `GovernanceState.load(repo_root)`. This is the identical shape Phase
16's `product_generation.py` and Phase 19's `pipeline.py` used against
`engineering.candidate` for the same reason.

## 5. What is explicitly not claimed

- **No new canonical state machine.** `STATE_MACHINES.md` still declares
  exactly twelve; the nine steps are an ordered composition, not a
  thirteenth machine.
- **No PostgreSQL migration evidence.** No PostgreSQL driver is installed on
  this host (`ModuleNotFoundError: psycopg2`/`psycopg`, verified directly).
  ADR-0006 registers the engine-neutral abstraction as MANDATORY and verified
  PostgreSQL operation as *not* a canonical requirement; this phase changes
  neither position.
- **No Stable-revision rollback.** "Rollback Point" here is a proven,
  restorable pre-migration backup — Phase 5's `lifecycle.recovery` authority,
  hardened. It is not `ROLLBACK_STABLE`, which stays `DENY` for every actor
  until Phase 22B's Recovery Supervisor exists (`pdp.py::_rollback_rule`,
  untouched by this phase).
- **No production surface.** Nothing here exposes an HTTP route or a UI
  affordance; `MigrationSafetySequence` is a library composition, matching
  every other Phase-20-adjacent authority's own scope boundary.
