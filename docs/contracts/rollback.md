# Stable revision pointer + rollback record — derived contract (C-32, Phase 22B)

**Owner:** `lifecycle.recovery` (Recovery Supervisor, rollback record),
`lifecycle.release` (Stable-revision pointer mechanism), `control.policy`
(the real `ROLLBACK_STABLE` grant, unmodified beyond this phase's own change)
**Kind:** EVD (evidence contract; no ORM table of its own — the rollback
record is a C-14 artifact plus C-15 evidence rows, both reused unmodified)
**Confinement:** STRICT
**Identity:** revision-hashed (every record is keyed by the content-addressed
`revision_id` it names, never a caller-chosen label)
**Version:** 1.0.0

This document records the executable Phase 22B contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0135`, `ARK-REQ-0136`, `ARK-REQ-0154`
through `ARK-REQ-0160`, `ARK-REQ-0338`, `ARK-REQ-0339`),
`docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md` sections "ARKALI
Self-Evolution" and "Database / Backup / Recovery" (the `ROLLBACK_STABLE`
rules), `docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md`
section "Recovery Supervisor", `docs/canonical/AUTHORITY_MAP.yaml`'s
`stable_mutation` block, and `docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md`
row 22B (decisions **D-017**/**D-018**). It does not replace those
authorities.

## 0. Scope of this revision

Five atomic packages, no new state machine minted (`STATE_MACHINES.md` stays
at twelve) and no second release or recovery authority created:

1. `lifecycle.release`: `stable_pointer.py` — `StableRevisionPointer`, the
   minimal atomic Stable-revision pointer D-017 assigns to this context. A
   revision enters its durable history only through a genuine
   `StableCandidatePath.promotion_receipt` (Phase 12/13's existing forward
   path, reused unmodified) — never a caller's bare assertion.
2. `control.policy`: `pdp.py`'s `_rollback_rule` and a new `PolicyRequest`
   fact, `rollback_target_verified_immutable`. `ROLLBACK_STABLE` grants `AUTO`
   to exactly the canonical invoker (`lifecycle.recovery`, read from
   `AUTHORITY_MAP.yaml`) and only when the request states that fact true;
   every other case is `DENY`. The PDP never computes the fact itself.
3. `lifecycle.recovery`: `recovery_supervisor.py` — `RecoverySupervisor`, the
   sole production caller of the grant above. Independent and deterministic:
   it imports no AI provider, no candidate-generation authority and no repair
   pipeline. A `HealthCheckResult` is supplied by the caller; detecting a bad
   candidate is not this authority's concern. It reaches the PDP grant and
   the evidence plane through two structural `Protocol`s
   (`RollbackAuthorization`, `EvidenceSink`) rather than direct imports of
   `control.policy`/`evidence.audit` — both real, measured budget violations
   found by running the architecture gate (§3 below), not assumed.
4. Composed proof that `lifecycle.evolution`'s pre-existing
   `core_upgrade_state_machine.recovery_supervisor_guard` — declared since the
   twelve machines were first built, and already documented as requiring "a
   verified Recovery Supervisor (Phase 22B) or the PDP returns DENY" — is
   satisfiable only from `RecoverySupervisor.is_verified()`'s real,
   evidence-derived value.
5. The composed VDC "Recovery Supervisor" journey, chaos/adversarial
   controls, this contract document, the C-17 report and traceability record.

**Not implemented or claimed by this revision:** Self-Evolution itself
(Phase 23), the full release/supply-chain/deployment system (Phase 26 — D-017
is explicit that only a minimal pointer primitive is needed here), a
thirteenth canonical state machine, or any change to `WRITE_STABLE_FILE`
(still `DENY` for every actor, unconditionally, untouched by this phase).

## 1. The Stable-revision pointer (`lifecycle.release`)

An atomic, content-addressed, append-only record of which revision is
Stable now and every revision that was Stable before it, stored as one JSON
file written via temp-file-then-`os.replace` — a reader never observes a
partially written pointer (ARK-REQ-0158: "atomic revision/pointer switching
preferred").

| Operation | What it proves |
|---|---|
| `promote(receipt, revision_id, candidate_id)` | Refuses any receipt that did not traverse the complete canonical `stable → candidate → verification → acceptance → promotion` path for the exact candidate named. The abandoned current revision (if any) joins history; nothing is ever discarded. |
| `current()` / `history()` | Read-only. |
| `is_previously_verified(revision_id)` | Whether this pointer's own durable record — never a caller's claim — contains `revision_id`, as current or historical. This is the whole of what ARK-REQ-0157 means by "previously verified immutable revision". |
| `rollback_to(revision_id)` | The raw mechanic only — no policy decision, no PDP call. Refuses any target `is_previously_verified` does not confirm. The target leaves history to become current; the abandoned current re-enters history in its place. |

## 2. The real `ROLLBACK_STABLE` grant (`control.policy`)

`AUTHORITY_MAP.yaml` fixes `ROLLBACK_STABLE` to
`{default: DENY, fixed: RECOVERY_SUPERVISOR_ONLY}`. Before this phase,
`pdp.py::_rollback_rule` was unconditional `DENY` — the canonical invoker
existed in the map but no verified Recovery Supervisor existed to check its
preconditions against. It now resolves:

```
actor != rollback_invoker                              -> DENY
actor == rollback_invoker
  and rollback_target_verified_immutable is not True    -> DENY
actor == rollback_invoker
  and rollback_target_verified_immutable is True         -> AUTO
```

Only `AUTO` or `DENY` are reachable — a genuine Recovery Supervisor rollback
is deterministic and unattended by design (MS: "Independent deterministic
Recovery Supervisor"), so there is no `ASK_USER` outcome for this rule.
`rollback_target_verified_immutable` is a fact the caller states; the PDP
stays pure and never resolves it itself, the identical discipline
`target_is_loopback` already established.

## 3. The Recovery Supervisor (`lifecycle.recovery`)

`RecoverySupervisor.rollback(health, target_revision_id)`:

1. Refuses outright if `health.healthy` — `ROLLBACK_STABLE` exists only to
   recover from a failed upgrade (ARK-REQ-0155/0156).
2. Computes `verified = pointer.is_previously_verified(target_revision_id)`
   honestly, then states it to `RollbackAuthorization.authorize` — an
   unverified target is refused by policy itself (`PolicyDenied`), not by
   convention.
3. Only after a genuine `AUTO` grant: calls `pointer.rollback_to`, the
   identity-only atomic switch — no content is read, generated or rewritten
   (ARK-REQ-0159, ARK-REQ-0339).
4. Registers one real C-14 artifact (Phase 6, unmodified) describing the
   rollback — `from_revision_id`, `to_revision_id`, `candidate_id`, `reason`,
   `performed_at`, and an explicit `transformation: "none"` statement — and
   appends three real C-15 evidence rows against it (Phase 6, unmodified):
   `ARK-REQ-0160` (every rollback is evidenced), `ARK-REQ-0338` (this *is* the
   end-to-end evidenced run), `ARK-REQ-0339` (restored without
   transformation), via `EvidenceSink`.

**Why two `Protocol`s, not imports.** Running the real architecture gate
(never assumed clean) found two genuine violations: `evidence.audit`'s own
chain already imports `control.specification`, so a direct `AuditChain`
import here would extend its already-4-of-4 `max_orchestration_depth` chain
to 5; and `control.policy.pep`/`.policy_contract` were already at their own
`max_fan_in_per_module` ceiling (15 of 15, reached by Phase 20), so any new
direct importer breaches both, and a fourth touched context
(`control.policy`, alongside `evidence.artifact`, `kernel.contracts`,
`lifecycle.release`) would separately breach
`max_contexts_touched_by_module` (3). `RollbackAuthorization` and
`EvidenceSink` (`recovery_supervisor.py`) trade in primitive facts only — the
identical shape `migration_safety_types.HumanGateSource` and
`pipeline.WorkspaceTarget` already use for the same class of problem. The
composition root (`tests/persistence/conftest.py`'s `PepRollbackAuthorization`
and `AuditChainEvidenceSink`) constructs the real `PolicyEnforcementPoint`/
`PolicyRequest` and the real `AuditChain` and adapts each to its Protocol —
**the real PDP decision still gates every rollback, and the real C-15 chain
still records it**; only the glue code that constructs the request/evidence
objects moved outside this module.

`RecoverySupervisor.is_verified()` re-queries the evidence chain, every call,
for a completed `ARK-REQ-0338` `PASS` row — never cached, never settable by a
constructor argument or a setter. Structurally, in shipped source, exactly
one module can ever produce that row
(`backend/tests/persistence/test_self_evolution_gate.py::
TestNotEnforceableByConvention` proves this by scanning the whole tree), and
that module cannot produce it without first obtaining the real grant in
section 2. This is how `ARK-REQ-0136` ("precondition enforced by the PDP, not
by convention") holds for the Self-Evolution entry guard in section 4: the
fact the guard reads is causally downstream of a real PDP decision, not an
assertion any module could fabricate.

## 4. Self-Evolution's DENY-until-verified precondition (ARK-REQ-0135/0136)

`lifecycle.evolution.core_upgrade_state_machine.py` already declares the
`SNAPSHOT_TAKEN -> CANDIDATE_BUILT` guard
(`recovery_supervisor_guard`, reading `recovery_supervisor_verified` from the
transition context) — unchanged by this phase, since it already states the
correct rule. What this phase supplies is the fact that guard now has a real,
non-fabricable source: `RecoverySupervisor.is_verified()`. No Self-Evolution
capability is built or claimed here (Phase 23); this phase closes only the
precondition Phase 23 will depend on.

## 5. What is explicitly not claimed

- **No Self-Evolution capability.** Phase 23 owns the campaign model, budgets
  and promotion workflow; this phase supplies only the rollback-verification
  precondition it is `DENY` without.
- **No change to `WRITE_STABLE_FILE`.** Still `DENY` for every actor,
  unconditionally — the only mutation this phase ever grants is the single,
  narrowly-scoped `ROLLBACK_STABLE` exception in section 2.
- **No new canonical state machine.** `STATE_MACHINES.md` still declares
  exactly twelve.
- **No full release/supply-chain/deployment system.** D-017: the pointer in
  section 1 is deliberately minimal — no signing, no SBOM, no deployment.
  `stable_promotion` keeps its one owner in `AUTHORITY_MAP.yaml`; Phase 26
  extends the same authority rather than creating a second one.
- **No production surface.** Nothing here exposes an HTTP route or a UI
  affordance; `RecoverySupervisor` is a library composition, matching every
  other Phase-22B-adjacent authority's own scope boundary.
