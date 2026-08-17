# Scoped human-gate authorization — derived contract (HUMAN_GATE_SCOPE_GAP remediation)

**Owner:** `acceptance.engine`
**Kind:** INT (no table, no migration, no ORM record)
**Version:** 1.0.0

This document records the mechanism that closes **HUMAN_GATE_SCOPE_GAP**: a
repository-wide defect in which `GovernanceState.accepted_human_gates` was a
flat `frozenset[str]` keyed only by gate ID, so a human decision recorded for
one candidate, phase, or operation mechanically satisfied any future check of
the same gate number. Proven for `HUMAN_GATE_4` by HGR-002's own "KNOWN
MECHANISM GAP" note (Phase 19's grant would also have satisfied Phase 21's
future check), and proven for `HUMAN_GATE_6` by direct, non-mutating probe
against the real PDP and the real `MigrationSafetySequence.step_apply` before
this module existed.

This is a governance-safety remediation authorized by explicit human ruling
under the stronger Protected Core verification profile, without treating
HUMAN_GATE_4 as a prerequisite (the ruling's own stated reason: the repair
only narrows existing authority, it does not weaken, relax, bypass, expand
or redefine a security permission).

## 1. Two scope kinds, never one

| | Subject | Reviewed at | Binding |
|---|---|---|---|
| `PhaseGateGrant` | a finished, already-built phase evidence package | phase acceptance time | `gate_id + phase_id + evidence_package_digest` — identical to `rescoring_authorization.RescoringAuthorization`'s existing GOV-001 pattern, reused rather than duplicated |
| `OperationGateGrant` | a specific runtime operation (`APPLY_MIGRATION`) | before that operation exists | `gate_id + operation_class + target_identity + revision_identity`, both mechanically derived from real facts, never a caller-asserted label |

Collapsing these into one shape would either under-scope the phase case or
force an operation grant to pretend it has a phase — both invented semantics
this contract refuses.

## 2. Storage: append-only tables in `HUMAN_GATE_RECORDS.md`

Two new markdown tables, parsed by `human_gate_authorization.py`'s own
generic reader (`rescoring_authorization._tables`, reused, not duplicated):

```
| ID | GATE | PHASE | EVIDENCE PACKAGE | ISSUER | STATUS | BASIS |
| ID | GATE | OPERATION | TARGET | REVISION | ISSUER | STATUS | BASIS |
```

Neither table edits the historical prose HGR records (HGR-001, HGR-002)
above them. A phase-scope row may *restate* an already-recorded decision
mechanically (HGR-002-SCOPED restates HGR-002's Phase 19 grant); it never
grants anything the prose record did not already grant, and adding it does
not require re-litigating the original human decision.

`forbidden_issuers` (the same `stable_mutation.prohibited_actors`-derived set
`rescoring_authorization.py` already reads) bars self-issued grants in both
tables — no second issuer list.

## 3. Two exempted gates, and only two

`HUMAN_GATE_1` ("PHASE 0 canonical architecture acceptance") and
`HUMAN_GATE_7` ("Final Production Release") name a unique, non-repeatable
project event in their own canonical text
(`CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md` §Canonical HUMAN GATES) and
appear on exactly one row each in `IMPLEMENTATION_DEPENDENCY_MATRIX.md` (0B
and 37 respectively) — not coincidentally, but because both gates are
canonically singular. `human_gate_authorization.SINGLETON_GATES` is a narrow,
canon-cited carve-out permitting the legacy, gate-ID-only check
(`GovernanceState.accepted_human_gates`, unchanged) to remain sufficient for
these two only. Every other gate — including `HUMAN_GATE_6`, whose matrix row
count also happens to be one today — requires a scoped grant, because a
row-count coincidence is not the same canonical guarantee gates 1 and 7's own
definitions carry.

## 4. Phase-gate enforcement (`acceptance.engine`)

`PhaseGateChecker.check_human_gate` → `governance_gates._evaluate_human_gate`:
singleton gates take the legacy path; every other gate computes the phase's
own `evidence_package_digest` (the exact function `check_rescoring_authority`
already calls) and looks up a `PhaseGateGrant` covering `(gate_id, phase_id,
digest)`. No grant, no PASS — regardless of what the same gate number granted
for any other phase.

## 5. Runtime-operation enforcement (`lifecycle.recovery`, composed — not `control.policy`)

Neither `pdp.py` nor `policy_contract.py` changed. The PDP's own contract was
already correct and generic: `APPLY_MIGRATION` at TRUST-0/1 is `ASK_USER`
unconditionally, and `_required_gate` already resolves `HUMAN_GATE_6` purely
from `AUTHORITY_MAP.yaml` and `targets_real_or_stable_data` — the defect was
never in the PDP's decision logic, only in what the caller supplied as
`recorded_human_gates`. `migration_safety_steps.step_apply` now:

1. Probes the PDP once with an empty `recorded_human_gates` to learn
   `required_human_gate` — reusing the PDP's own resolution, never
   duplicating `_required_gate`'s logic in `lifecycle.recovery`.
2. If a gate is required, computes `target_identity` from
   `BackupSet.manifest.digest` (the pre-migration backup's real content
   digest, `kernel.persistence`-computed) and `revision_identity` from the
   already-resolved target revision, then asks
   `request.human_gates.operation_grant(gate, "APPLY_MIGRATION",
   target_identity, revision_identity)`.
3. Re-evaluates the PDP with the correctly scoped `recorded_human_gates`.

`HumanGateSource` (`migration_safety_types.py`) is a structural `Protocol`
exposing `operation_grant`, satisfied by `GovernanceState.operation_grant` —
never a direct `lifecycle.recovery → acceptance.engine` import, which would
extend `acceptance.engine`'s already-4-of-4 orchestration-depth chain
(`acceptance.engine → control.specification → control.architecture →
kernel.contracts`) to 5. Identical shape to Phase 20's own original
`HumanGateSource` design and to Phase 16/19's `WorkspaceAuthority`
compositions for the same reason.

**Confused-deputy resistance.** `MigrationSafetyRequest` has no field a
caller could set to claim an arbitrary target or revision identity — both
are derived inside `step_apply` from a real `BackupSet` the sequence itself
produced earlier in the same run. `TestConfusedDeputyCannotSpoofTargetIdentity`
and `TestOperationGrantScopePrecision` prove this both structurally and
behaviourally.

## 6. Historical compatibility

HGR-001 and HGR-002 are **unedited**. `HUMAN_GATE_1` (HGR-001) is
grandfathered via `SINGLETON_GATES` — no migration needed or possible (Phase
0 predates the `phase_N_report.json`/`traceability.json` scheme
`evidence_package_digest` depends on). HGR-002's Phase 19 scope is restated
in the new phase-scope table (`HGR-002-SCOPED`), proven — against the real,
live document, not a synthetic fixture — to satisfy a Phase 19 lookup and
refuse a Phase 21 lookup for the identical gate number
(`TestControl3RealHistoricalPhase19DoesNotLeakToPhase21`). Phase 19's own
acceptance record in `BUILD_STATE.md` is untouched; this repair does not
re-verify or re-score it.

## 7. What is explicitly not claimed

- **`HUMAN_GATE_6` is not granted by this repair.** The operation-scope table
  is seeded empty. Phase 20's candidate remains `AWAITING_HUMAN_GATE` exactly
  as before.
- **No new shadow authority.** Table parsing, digest computation and the
  forbidden-issuer list are all reused from `rescoring_authorization.py`; no
  second markdown-table reader, no second issuer list, no second acceptance
  or policy authority exists.
- **Replay is intentionally content-bound, not use-once.** A grant matches by
  content (digest / target+revision), the same discipline GOV-001's own
  digest-binding already established — an identical resubmission of an
  already-reviewed subject is deterministic re-use, not a replay
  vulnerability. Whether a *pause-and-resume* operational workflow (a human
  reviewing an already-taken backup's digest before a later, separate Apply
  invocation reuses it) is fully built is explicitly out of scope: no
  production surface exposes `MigrationSafetySequence` with real data today,
  and building that workflow is a distinct, later concern from closing the
  scope-binding defect this document addresses.
