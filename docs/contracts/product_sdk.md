# Product Evolution SDK — derived contract (C-36, Phase 24)

**Owner:** `lifecycle.evolution` (identity, campaign, version lineage,
promotion, rollback — all seven packages)
**Kind:** SDK (a library composition; no ORM table, no HTTP route)
**Confinement:** PINNED (per `CONTRACT_INVENTORY.md`'s own row)
**Identity:** content-addressed (`ChildProductIdentity.product_ref`,
`ChildProductVersion.version_ref`, `ChildProductVersionLineage.lineage_ref`,
`ChildProductRollbackReceipt.receipt_ref`)
**Version:** 1.0.0

This document records the executable Phase 24 contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0131`, `ARK-REQ-0132`, `ARK-REQ-0133`,
`ARK-REQ-0358`), `docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md` section
"AI-Native Child Products", `docs/ARKALI_GENESIS_V2_VERIFICATION_AND_
DELIVERY_CONTRACT.md` section "Child Product Evolution",
`docs/canonical/AUTHORITY_MAP.yaml`'s `lifecycle.evolution` declaration, and
`docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md` row 24
(`GATE 3 where approval-gated`, ADR-0010). It does not replace those
authorities.

## 0. Scope of this revision

Seven atomic packages, no new state machine minted (`STATE_MACHINES.md`
stays at twelve — `EvolutionCampaign` was already declared, reused as-is)
and no second campaign, promotion, or human-gate authority created:

1. `child_product_identity.py` — `ChildProductMode` (the three MS-named
   modes: `STANDARD`, `AI_ASSISTED`, `AI_NATIVE_SELF_EVOLVING`) and
   `ChildProductIdentity`, content-addressed like `CampaignDeclaration`.
2. `child_product_campaign.py` — `declare_child_product_campaign`/
   `begin_child_product_campaign`, composing the real, unmodified Phase 23
   `EvolutionCampaign` machine and `CampaignDeclaration`/`CampaignBudgets`
   directly; refuses before constructing anything for a non-SDK-eligible
   mode.
3. `child_product_version.py` — `ChildProductVersion`/
   `ChildProductVersionLineage`, mirroring `StableRevisionPointer`'s
   discipline (content-addressed, append-only, no silent rewrite) without
   sharing its instance; durability follows the C-14/C-15 evidence-plane
   pattern Phase 23's own campaign records already use, not a new
   persistence mechanism.
4. `child_product_promotion.py` — `promote_child_product`, gated by a
   scoped `HUMAN_GATE_3` grant reusing the identical `HUMAN_GATE_2`/
   `CORE_PROMOTION` mechanism (`GovernanceState.operation_grant`)
   unmodified (ADR-0010: fail-closed, no exemption path).
5. `child_product_rollback.py` — `rollback_child_product`, a separate
   authority from promotion (ADR-0009 reapplied), requiring no fresh
   `HUMAN_GATE_3` since it only ever restores already-approved content.
6. Structural negative/adversarial proofs (`test_child_product_no_direct_
   promotion.py`, `test_child_product_adversarial.py`): no direct
   Stable/live mutation, no self-approval, no cross-product leak, no
   ARKALI-core-promotion misuse, no campaign-restart manipulation, no
   shadow authority.
7. The composed real-authority journey (`test_child_product_journey.py`),
   this contract document, the C-17 report and traceability record.

**Not implemented or claimed by this revision:** any live entrypoint that
takes a natural-language goal and produces a generated child product (that
gap is tracked separately and permanently as `DEF-009`, `docs/build/
OPEN_BLOCKERS.md` — explicitly out of this phase's scope, not silently
absorbed here); AI-provider-driven multi-file product generation (Phase
30's own obligation); a live scheduler/worker that would execute anything
built here in production; any change to ARKALI's own `StableRevisionPointer`
or `RecoverySupervisor`; a second campaign, promotion, or rollback
authority; a live `HUMAN_GATE_3` grant for this phase's own acceptance (see
§7).

## 1. Child-product identity and the three canonical modes (`lifecycle.evolution`)

| Object | What it proves |
|---|---|
| `ChildProductMode` | Exactly the three MS-named modes — `STANDARD`, `AI_ASSISTED`, `AI_NATIVE_SELF_EVOLVING` — and no others; a fourth mode cannot be constructed. |
| `ChildProductIdentity.uses_evolution_sdk` | The single place SDK eligibility is decided (`AI_NATIVE_SELF_EVOLVING` only), so no caller re-derives the rule from the mode's name. |
| `ChildProductIdentity.product_ref` | Content-addressed identity, the same discipline `CampaignDeclaration.campaign_ref` already uses. |

`ARK-REQ-0358` ("child product runs independently; full core not copied as
runtime") constrains the generated child's own deployed artifact, which
this context does not build; identity is recorded here, not runtime.

## 2. The child-product campaign (`lifecycle.evolution`)

`declare_child_product_campaign`/`begin_child_product_campaign` compose
`evolution_campaign_state_machine.build()` — `EvolutionCampaign`,
`STATE_MACHINES.md` §10 — directly and unmodified. MS states plainly:
"Product Evolution SDK improvement cycles use the same bounded campaign
model, budgets and terminal states as ARKALI Self-Evolution"; no second
`StateMachineDefinition` is minted, and `lifecycle.evolution` gains no
second `state_machine_authorities` entry.

`_child_campaign_id(identity, objective)` is content-addressed over both
the product and the specific evolution request — not the product alone. A
real defect was found running the composed journey (`test_child_product_
journey.py`): binding the id to product identity only made every
evolution request for the same product collide into one shared campaign
namespace, so a second real request's workspace allocation failed as
"already allocated" against the first's. Repaired before this candidate
froze; the traceability record's own evidence for `ARK-REQ-0132`/`0133`
proves the corrected property directly, not the earlier one.

## 3. Child-product version lineage (`lifecycle.evolution`)

`ChildProductVersion`/`ChildProductVersionLineage` mirror `lifecycle.
release.StableRevisionPointer`'s discipline (content-addressed identity,
append-only history, no silent rewrite) without importing or sharing its
instance — a child product's version history is a distinct concern (many
products, each independent) from ARKALI's own single Stable Core pointer.
`append` refuses a sequence gap or a rewritten parent before returning
anything; `restore_to` (named to avoid colliding with `StableRevisionPointer.
rollback_to`, a real naming collision Phase 23's own structural test caught
and this phase resolved by renaming rather than loosening that test) always
appends rather than truncates.

Durability follows the C-14/C-15 evidence-plane pattern Phase 23's own
campaign records already use: this module defines the pure record shape
only; a composition root registers `rendering()` as a real artifact,
exercised for the first time in the composed journey (§6).

## 4. Scoped `HUMAN_GATE_3` promotion (`lifecycle.evolution`)

`AUTHORITY_MAP.yaml`/`IMPLEMENTATION_DEPENDENCY_MATRIX.md` map Phase 24 to
`HUMAN_GATE_3` ("Generated-product promotion where approval-gated"). ADR-0010
records the engineering decision this phase makes given genuine canonical
silence on the trigger condition: every child-product promotion is treated
as approval-gated by default — fail-closed, no exemption path, mirroring
GATE 2's own unconditional precedent and this repository's consistent
deny-by-default posture elsewhere.

`promote_child_product` never imports `lifecycle.release` and calls no
`StableRevisionPointer` method — it mutates only the child's own
`ChildProductVersionLineage`. The grant is looked up through
`_ChildProductGateSource`, the identical `Protocol` shape `core_upgrade_
orchestrator.HumanGate2Source` already uses to reach `GovernanceState.
operation_grant` — no second parser, no second PDP/PEP, no second
authorization table. `PROMOTE_CHILD_PRODUCT` is this context's own
`RUNTIME_OPERATION` scoping key, parallel to `CORE_PROMOTION`'s, not a new
PDP `operation_classes` entry; the two are proven to stay distinct strings
(`test_child_product_adversarial.py`).

Identity is derived, never caller-asserted: `_child_promotion_target_
identity`/`_child_promotion_revision_identity` are content-addressed over
the real product, the real candidate content, and the real current
version — a grant for one (product, candidate, current-version) triple does
not authorize a different product, a different candidate, a different
target, or a replay after the current version has moved on (8 scoped-grant
negative tests, mirroring `test_core_promotion_gate_scope.py` exactly).

Ordering is enforced before any mutation: candidate validity, SDK
eligibility, acceptance-record match (`ChildProductAcceptanceRecord` — real
executed evidence, never a boolean, matching `verification_profile.py`'s
own "evidence is execution" discipline), then the grant, all checked before
`ChildProductVersionLineage.append` is ever reached; a refusal at any step
leaves the lineage byte-identical (proven directly, not assumed from
immutability alone).

## 5. Rollback, a separate authority (`lifecycle.evolution`)

ADR-0009's own precedent reapplied at child-product scope: `child_product_
promotion.py` never calls `restore_to`, and `child_product_rollback.py`
never calls `.append` with `is_rollback=False` — two authorities, one
direction of trust, proven by AST.

Rollback requires no fresh `HUMAN_GATE_3`: it only ever restores content
already present in the lineage's own durable history (`find` refuses any
target that is not) — content a `HUMAN_GATE_3` grant already approved once,
at the promotion that first introduced it. Identical reasoning to why
`RecoverySupervisor`'s own rollback (Phase 22B) needs no fresh human
approval either, only proof the target was previously verified. No new
PDP/PEP entry; this module imports neither `lifecycle.release` nor
`lifecycle.recovery`, so it cannot reach ARKALI's own Stable Core pointer or
Recovery Supervisor at all — proven by AST, not convention.

`ChildProductRollbackReceipt` records what actually happened (mirrors
`RecoverySupervisor.RollbackRecord`); a mismatched identity/lineage pair is
refused before anything is touched.

## 6. Negative / adversarial proofs and the composed journey

`test_child_product_no_direct_promotion.py` and `test_child_product_
adversarial.py` (consolidated) prove: no direct Stable/live mutation
anywhere in the child-product SDK; `PROMOTE_CHILD_PRODUCT`/`CORE_PROMOTION`
stay distinct and unreachable from each other; the lineage primitive itself
refuses an unrecorded rollback target even bypassing orchestration; a
child-product campaign built from the real `EvolutionCampaign` machine
raises `TerminalStateEscape` on any transition attempted after reaching a
terminal state — proven directly, not assumed from Phase 23's own abstract
proof; the live `duplicate_state_machine_authority`/`duplicate_canonical_
authority`/`shadow_registry` architecture gates are re-run as an explicit
adversarial assertion; no child-product module parses `HUMAN_GATE_RECORDS.md`
itself.

`test_child_product_journey.py` composes real infrastructure, not unit
doubles: the real, unmodified Phase 12 `WorkspaceAuthority` over a real
filesystem; a real SQLite database migrated through the real Alembic chain;
the real C-14 `ArtifactStore` and C-15 `AuditChain`; the real scoped
`HUMAN_GATE_3` grant mechanism (a temporary `HUMAN_GATE_RECORDS.md` copy,
mirroring `test_core_promotion_gate_scope.py`'s own fixture discipline). Two
full evolution cycles run to real, different outcomes — refused with no
grant, promoted with one, a stale grant proven not to leak into a second
promotion, rollback to the first version with no fresh grant, full
lineage/evidence history verified intact.

## 7. GATE 3 and this phase's own acceptance

The matrix's `GATE 3` column on Phase 24's own row is parsed identically to
Phase 23's `GATE 2` — the parser extracts the gate number from the cell
regardless of the "where approval-gated" qualifier, so Phase 24's own
acceptance mechanically requires a `_PhaseGateGrant` (`HUMAN_GATE_3`,
`phase_id="24"`, this phase's own evidence digest), the same shape Phase 23
(`HGR-005`) needed for its own acceptance. No such grant exists yet,
confirmed against the live, unmodified `HUMAN_GATE_RECORDS.md`. This
phase's own machine verdict is expected to be `AWAITING_HUMAN_GATE`, not
`PHASE_ACCEPTED_BY_MACHINE` — the mechanism in sections 1 through 6 is
complete and evidenced; the human decision is not self-granted.

## 8. What is explicitly not claimed

- **No live goal-to-child-product generation pipeline.** Tracked separately
  and permanently as `DEF-009` — a real, measured gap this phase does not
  close and does not silently absorb.
- **No change to ARKALI's own Stable Core or Recovery Supervisor.** Neither
  `StableRevisionPointer` nor `RecoverySupervisor` is imported anywhere in
  the child-product SDK.
- **No new canonical state machine.** `STATE_MACHINES.md` still declares
  exactly twelve.
- **No second grant-scoping, PDP, evidence-plane, or promotion mechanism.**
  Every authority this phase composes already existed and is reused
  unmodified beyond two new `Protocol`s (§5's workspace decoupling; §4's
  gate-source decoupling) and one new operation-class scoping key
  (`PROMOTE_CHILD_PRODUCT`, §4).
- **No production surface.** Nothing here exposes an HTTP route or a UI
  affordance; every module is a library composition, exercised only through
  tests, matching every self-evolution-adjacent authority's own scope
  boundary before it.
- **No self-granted `HUMAN_GATE_3`.** Section 7 is explicit: this phase's
  own acceptance requires a human decision this phase does not and cannot
  make for itself.
