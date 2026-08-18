# Evolution campaign declaration + terminal record — derived contract (C-33, Phase 23)

**Owner:** `lifecycle.evolution` (campaign declaration, ledger, orchestration),
`lifecycle.recovery` (restorable snapshot), `control.policy` (scoped
HUMAN_GATE_2 grant consumption, unmodified beyond this phase's own use of the
already-accepted mechanism), `acceptance.engine` (campaign-record shape)
**Kind:** EVD (evidence contract; no ORM table of its own — a campaign
record is C-14 artifacts plus C-15 evidence rows, both reused unmodified)
**Confinement:** STRICT
**Identity:** content-addressed (`CampaignDeclaration.campaign_ref`,
`CampaignLedger.ledger_ref`)
**Version:** 1.0.0

This document records the executable Phase 23 contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0134`, `ARK-REQ-0137` through
`ARK-REQ-0142`, `ARK-REQ-0359`, `ARK-REQ-0360`),
`docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md` section "ARKALI
Self-Evolution", `docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md`
section "ARKALI Self-Evolution", `docs/canonical/AUTHORITY_MAP.yaml`'s
`stable_mutation` and `human_gates` blocks, `docs/canonical/STATE_MACHINES.md`
§8 (Core Upgrade) and §10 (Evolution Campaign), and
`docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md` row 23 (`GATE 2`). It
does not replace those authorities.

## 0. Scope of this revision

Seven atomic packages, no new state machine minted (`STATE_MACHINES.md`
stays at twelve — `CoreUpgrade` and `EvolutionCampaign` were already
declared, scaffolding only) and no second release, recovery, policy or
acceptance authority created:

1. `lifecycle.evolution`: `campaign_declaration.py` — `CampaignBudgets` (the
   six MS-named budgets as typed fields) and `CampaignDeclaration`, wired to
   the pre-existing `evolution_campaign_state_machine.declaration_guard`.
2. `lifecycle.evolution`: `campaign_ledger.py` — `CampaignLedger`, mirroring
   `engineering.repair.contracts.RepairBudgetLedger`'s structural shape at
   the campaign's own six budgets. `may_generate_successor()` and
   `terminal_state()`.
3. `lifecycle.recovery`: `core_snapshot.py` — `take_core_snapshot`, a real
   restorable-snapshot proof distinct from `RecoveryService` (workspace
   SQLite backup) and `RecoverySupervisor` (Stable rollback).
   `lifecycle.evolution`: `core_upgrade_orchestrator.py`'s
   `begin_core_upgrade`, reaching it through a `RestorableSnapshotProof`
   `Protocol` (no declared sibling edge exists to reach it directly).
4. `lifecycle.evolution`: `core_upgrade_orchestrator.py`'s
   `authorize_promotion`, reaching `acceptance.engine.GovernanceState.
   operation_grant` through a `HumanGate2Source` `Protocol` — the identical
   shape `migration_safety_types.HumanGateSource` already uses for
   `HUMAN_GATE_6`. `CORE_PROMOTION` is this context's own scoping key for
   the human-gate table, not a new PDP `operation_classes` entry.
5. `lifecycle.evolution`: `core_promotion.py` — `promote_core_upgrade`,
   composing the real `StableRevisionPointer.promote` (the only `promote()`
   in the codebase) through the declared `lifecycle.evolution ->
   lifecycle.release` sibling edge. Sequences two independent refusals; a
   real ordering defect (a stale receipt could leave the state machine
   claiming `PROMOTED` while Stable was never written) was found by testing
   and repaired before this phase closed.
6. Structural negative/adversarial proofs: no `lifecycle.evolution` module
   but `core_promotion.py` can reach `StableRevisionPointer.promote`/
   `.rollback_to`; the composed HUMAN_GATE_2/CORE_PROMOTION grant lookup
   inherits every scoped-grant negative control already proven generically
   (forbidden issuer, confused deputy, gate/phase/digest scope) without
   reimplementing any of them.
7. `acceptance.engine`: `campaign_record_shape.py` (private —
   `acceptance.engine`'s public-surface budget was already at its ceiling
   and no live caller exists yet), operating on primitive mappings only
   (`acceptance.engine` cannot import `lifecycle.evolution` — upward layer
   edge). The composed VDC journey, this contract document, the C-17 report
   and traceability record.

**Not implemented or claimed by this revision:** an actual self-evolution
campaign run against ARKALI's own source (no candidate-generation, no AI
routing decision is made — Phase 23 builds the governed mechanism, not a
live improvement cycle), the Product Evolution SDK (Phase 24), Golden
Factory/Golden Repair, any change to `WRITE_STABLE_FILE` (still `DENY` for
every actor, unconditionally), a second HGR grant-scoping mechanism, or a
live `HUMAN_GATE_2` grant for this phase's own acceptance (see §6).

## 1. The campaign declaration and ledger (`lifecycle.evolution`)

| Object | What it proves |
|---|---|
| `CampaignBudgets` | Exactly the six MS-named budgets (`candidate_budget`, `ai_call_budget`, `time_budget_seconds`, `cost_budget`, `regression_ceiling`, `no_progress_threshold`) as typed, required pydantic fields — the "six budgets" by construction, not an arbitrary count. |
| `CampaignDeclaration.guard_context()` | The exact fact set `declaration_guard` reads (objective, baseline metrics, the six budget names) — the only path that can satisfy `DECLARED -> RUNNING` with a real declaration, never a hand-built dict skipping real typed budgets. |
| `CampaignLedger.may_generate_successor()` | ARK-REQ-0141: true only while every budget dimension has headroom and the no-progress threshold has not been reached; false unconditionally once any attempt is `PROMOTED`. |
| `CampaignLedger.terminal_state()` | ARK-REQ-0140: `PROMOTED` once any attempt records it; otherwise mirrors `HardeningRound`'s own canonical rule (`STATE_MACHINES.md` §11) — exhaustion with the most recent attempt's baseline intact yields `COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN`, a regression present yields `ESCALATED`. Refuses to answer while the campaign may still continue. `BLOCKED` is deliberately not derived here — it is `CoreUpgrade`'s own entry-gate concern. |

ARK-REQ-0142 ("never restarted to obtain a different terminal state") is
structural in the kernel state-machine primitive itself: every terminal
state carries no outgoing transition, so `TerminalStateEscape` refuses any
further transition unconditionally, proven against the real
`EvolutionCampaign` machine.

## 2. The restorable snapshot (`lifecycle.recovery` / `lifecycle.evolution`)

`take_core_snapshot(pointer, artifacts, candidate_id)` (ARK-REQ-0137):
records a real C-14 artifact for the current Stable revision and proves it
restorable by reading the bytes back through `ArtifactStore.verify`/
`.content_of` — the same discipline `RecoveryService.prove_by_restore`
already uses for a workspace backup, applied here to a pre-upgrade evidence
record rather than a SQLite image. Refuses if no Stable revision exists yet,
and refuses (`SnapshotNotRestorableError`) rather than trusts the
registration if the read-back does not confirm it.

`begin_core_upgrade(snapshot, candidate_id)` is the production entry point
that constructs a `CoreUpgrade` instance in `SNAPSHOT_TAKEN` — the only one,
since `StateMachine.start` carries no guard of its own to enforce "no
snapshot, no instance" otherwise.

## 3. The scoped HUMAN_GATE_2 grant (`control.policy` / `acceptance.engine`)

`AUTHORITY_MAP.yaml` defines `HUMAN_GATE_2 = "ARKALI Stable Core promotion"`.
It is not a `SINGLETON_GATE`: a scoped grant is required, exactly as
`HUMAN_GATE_6`/`APPLY_MIGRATION` already needs. `authorize_promotion(gates,
candidate_manifest_ref, target_revision_id)` populates
`gate_2_guard`'s context only from `gates.operation_grant(HUMAN_GATE_2,
CORE_PROMOTION, candidate_manifest_ref, target_revision_id)` — never a
caller-asserted boolean. `acceptance.engine.GovernanceState` satisfies the
`HumanGate2Source` `Protocol` structurally (proven by `isinstance`), through
its own already-accepted, already-proven scoped-grant mechanism
(`human_gate_authorization.py`) — no second implementation.

`CORE_PROMOTION` is not a PDP `operation_classes` entry:
`StableRevisionPointer.promote` is gated by `StableCandidatePath`'s
five-stage receipt proof, not by the PDP's Stable-mutation vocabulary
(`WRITE_STABLE_FILE`/`ROLLBACK_STABLE` are its only two entries). No
`control.policy`/`AUTHORITY_MAP.yaml` change was needed.

## 4. Composed promotion (`lifecycle.evolution` -> `lifecycle.release`)

`promote_core_upgrade(request)` sequences two independent refusals, neither
bypassable by the other:

```
1. path.promotion_receipt(receipt)          -> may raise StablePathError
   (validated BEFORE the state machine transitions — see the ordering note
   below)
2. instance.apply(PROMOTED, authorize_promotion(...))
                                             -> may raise GuardRejected
3. pointer.promote(promotion_receipt, ...)  -> the real Stable mutation,
                                                reused completely unmodified
```

**Ordering matters.** The receipt is validated into its final promotion
stage *before* step 2, not after. A stale or incomplete receipt discovered
only after the `CoreUpgrade` instance already recorded `PROMOTED` would
leave the instance claiming a promotion that never actually reached the
pointer — an orphaned claim this codebase's evidence discipline exists to
prevent. This was a real defect found by testing during this phase, not a
hypothetical, and is repaired in the shipped code.

`lifecycle.evolution -> lifecycle.release` is a declared sibling edge
("promotion handoff"), so this composition is a direct import — unlike
sections 2 and 3's undeclared edges, which reach their authorities through a
`Protocol`.

## 5. Negative / adversarial proofs (ARK-REQ-0134, ARK-REQ-0359)

Structural, AST-based (mirrors `test_repair_pipeline_authority.py`): no
`lifecycle.evolution` module but `core_promotion.py` can call
`StableRevisionPointer.promote`/`.rollback_to`, `core_promotion.py` itself
never calls `.rollback_to`, and no module performs file/process I/O of its
own — this context orchestrates already-independent authorities; it does
not gain a second mutation path. No local D-026 tier-ordering vocabulary is
declared (Phase 23 builds no AI-assisted candidate-generation step).

The self-approval boundary: `CORE_PROMOTION`/`HUMAN_GATE_2` composed
end-to-end against a real (temporary) `HUMAN_GATE_RECORDS.md` proves a
barred automated actor (`stable_mutation.prohibited_actors`) cannot
manufacture its own core-promotion authorization, a grant for a different
candidate manifest does not leak, and a grant for a different gate does not
satisfy `HUMAN_GATE_2` — the same scoped-grant guarantees every other gate
already has, inherited rather than reimplemented.

## 6. The campaign-record shape check (`acceptance.engine`, ARK-REQ-0360)

`_check_campaign_record_shape(declaration, outcome)` refuses an evolution
run's outcome unless its campaign record proves bounded: a real objective,
real baseline metrics, exactly the six canonical budgets, and a genuine
terminal state — VDC's own enumerated fields. It operates on primitive
mappings, never a `lifecycle.evolution` import (an upward layer edge
`AUTHORITY_MAP.yaml` forbids); a dedicated reconciliation test, outside the
context graph, proves its restated vocabulary is identical to the real
`CampaignBudgets.model_fields` and `EvolutionCampaign`'s real terminal set.
Kept private: `acceptance.engine`'s public-surface budget was already at its
ceiling, and no live campaign-acceptance path exists yet to call this
publicly — `checker.py` gains a public caller for it the day one does, not
before.

## 7. GATE 2 and this phase's own acceptance

The matrix's `GATE 2` column on Phase 23's own row is a distinct obligation
from section 3's runtime mechanism: it requires a `_PhaseGateGrant`
(`HUMAN_GATE_2`, `phase_id="23"`, this phase's own evidence digest) — the
same shape Phase 19/`GATE 4` (HGR-002) and Phase 20/`GATE 6` (HGR-003)
needed for their own acceptance. No such grant exists yet, confirmed against
the live, unmodified `HUMAN_GATE_RECORDS.md`. This phase's own machine
verdict is expected to be `AWAITING_HUMAN_GATE`, not
`PHASE_ACCEPTED_BY_MACHINE` — the mechanism in sections 1 through 6 is
complete and evidenced; the human decision is not self-granted.

## 8. What is explicitly not claimed

- **No live self-evolution campaign.** Nothing in this phase generates or
  repairs a real candidate against ARKALI's own source; the composed journey
  drives the real mechanism with real infrastructure, not a live improvement
  cycle.
- **No change to `WRITE_STABLE_FILE`.** Still `DENY` for every actor,
  unconditionally.
- **No new canonical state machine.** `STATE_MACHINES.md` still declares
  exactly twelve; `CoreUpgrade` and `EvolutionCampaign` were already
  declared before this phase (scaffolding only).
- **No second grant-scoping, PDP, evidence-plane, or promotion mechanism.**
  Every authority this phase composes already existed and is reused
  unmodified beyond the two new `Protocol`s (sections 2 and 3) and one new
  operation-class scoping key (`CORE_PROMOTION`, section 3).
- **No production surface.** Nothing here exposes an HTTP route or a UI
  affordance; every module is a library composition, exercised only through
  tests, matching every other Phase-23-adjacent authority's own scope
  boundary.
- **No self-granted `HUMAN_GATE_2`.** Section 7 is explicit: this phase's
  own acceptance requires a human decision this phase does not and cannot
  make for itself.
