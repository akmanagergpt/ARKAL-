# C-28 Knowledge Record + Validity State — derived contract

**Owner:** `engineering.knowledge`
**Producer:** knowledge authority
**Consumers:** `agents`, `factory`
**Kind:** INT
**Version:** 1.0.0
**Compatibility:** ADDITIVE

This document records the executable Phase 18 contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0126`, `ARK-REQ-0127`, `ARK-REQ-0128`,
`ARK-REQ-0394`), `CONTRACT_INVENTORY.md` row C-28, MS §Knowledge / Verified
Components / Local AI, and human ruling **D-026**. It does not replace those
authorities.

## 0. Scope of this revision

Three atomic packages: the evidence-backed knowledge record and its
validity lifecycle (`contracts.py`), the reusable-component metadata
descriptor (`component_metadata.py`), and per-model/per-task-class
empirical outcome statistics (`outcome_statistics.py`). All three live
under `backend/arkali/engineering/knowledge/`, the context Phase 1
bootstrapped and Phase 15/16 left untouched. **Not implemented or claimed
by this revision:** a persisted knowledge store, a live evidence-store
lookup that resolves a `content_address` against a really-stored C-14/C-15
record, wiring into `engineering.factory.execution_routing`'s
`VERIFIED_KNOWLEDGE` tier, and any PDP/operation-class enforcement. Each is
recorded below as a deliberate boundary, not a silent gap.

## 1. Compatibility semantics and persistence

The contract is **INT**, the same category `docs/contracts/provider_record.md`
(C-11) and `docs/contracts/capability_node.md` (C-13) carry, and this
package follows their precedent exactly: **no table, no migration, no ORM
record.** `KnowledgeRecord`, `ReusableComponentDescriptor` and
`VerifiedOutcome`/`EmpiricalOutcomeStats` are frozen, `extra="forbid"`
pydantic value objects — content-addressed, immutable, functionally
updated (a "changed" record is a new object, never a mutation) — the same
shape `engineering.repair`'s C-26 `RepairFingerprint`/`RepairBudgetLedger`
already established for an engineering-layer, non-Protected-Core context.
Durable, cross-process storage of a knowledge record is not claimed by
this phase; a future phase that needs it composes `kernel.persistence`
itself rather than this contract inventing a second, INT-labelled table.

## 2. Evidence-backed knowledge, structurally (ARK-REQ-0126, ARK-REQ-0394)

MS §Knowledge: "Only evidence-backed successful outcomes can become
authoritative knowledge." D-026: "only VERIFIED outcomes — never a model's
self-reported claim — may update routing knowledge." Both rules are the
same discipline applied to two different record shapes
(`KnowledgeRecord.evidence`, `outcome_statistics.VerifiedOutcome.evidence`),
so both require the **same** field type, `EvidenceReference`:

```
EvidenceReference:
  kind: artifact | audit | acceptance_result   # closed vocabulary
  content_address: sha256:<64 lowercase hex>   # kernel.contracts.content_address.is_address
```

A model's own unverified statement is a **structurally distinct type**,
`SelfReportedClaim` (`reported_by`, `claim` — no `content_address` field at
all). It is honestly constructible — a caller may record that a self-report
was made — but it can never be substituted where `EvidenceReference` is
required: `KnowledgeRecord(evidence=SelfReportedClaim(...))` and
`VerifiedOutcome(evidence=SelfReportedClaim(...))` both fail pydantic
validation before any domain logic runs. This is a type-level refusal, not
a scan of free text for words like "self-reported" — nothing here
classifies prose.

**What is and is not verified.** `EvidenceReference.content_address` is
validated to be a well-formed canonical content address. This package does
**not** cross-reference that address against a currently-stored C-14
artifact, C-15 audit record or C-16/C-17 acceptance result — the identical
non-live-lookup boundary `docs/contracts/repair.md`'s `RepairFingerprint`
already recorded for its own content-addressed identity. "Evidence-backed"
is enforced as "structurally cannot be a self-report and must carry a
well-formed pointer to one of the three real evidence kinds a future
consumer can resolve" — not as "already resolved against a live store,"
which no requirement in this phase's denominator asks for.

## 3. Knowledge validity lifecycle (ARK-REQ-0127)

MS §Knowledge names five states — `fresh`, `aging`, `revalidation_required`,
`deprecated`, `invalid` — but, unlike every one of the 12 machines
`STATE_MACHINES.md` (Human Gate 1, closed) declares, states no transition
graph for them. `STATE_MACHINES.md`'s own count stays 12: this lifecycle is
not added to it, matching the precedent every prior phase set (Phase 14's
`RepairBudgetLedger`, Phase 15's blueprint engine and Phase 16's execution
routing all added domain-level state without touching the reconciled 12).

The transition graph below is **derived from the ordinary meaning of each
state name**, the same textual-derivation method `harness_elements.py`
(Phase 10) established as this build's answer to a canonical vocabulary
that names values but not their relationships, applied here rather than
inventing an unstated graph silently:

```
fresh                  -> aging, invalid
aging                  -> fresh, revalidation_required, invalid
revalidation_required  -> fresh, deprecated, invalid
deprecated             -> invalid
invalid                -> (none — terminal)
```

Rationale: `fresh` evidence ages without action; `aging` evidence
reconfirmed by new evidence returns to `fresh`, left unconfirmed becomes
`revalidation_required`; a successful revalidation returns to `fresh`, a
lapsed one is `deprecated` (superseded, not wrong); at any point,
contradicting evidence moves a record straight to `invalid` regardless of
its current state, because a contradiction is itself new evidence and
`ARK-REQ-0126` gives it no reason to wait for the aging pipeline.
`deprecated` cannot return to `fresh` — a superseded claim does not
un-supersede; a genuinely fresh claim is a new record. `invalid` is
terminal, matching `STATE_MACHINES.md`'s cross-cutting invariant 7 ("every
terminal state is genuinely terminal"), applied here by the same
convention though this lifecycle is not one of the reconciled 12.
Transitions not listed are refused by `assert_transition_allowed`
(`IllegalValidityTransitionError`, `ARK-ERR-0141`) before any other check
runs.

## 4. Reusable component metadata (ARK-REQ-0128)

MS §Knowledge: "Reusable components require isolated tests/security/
compatibility metadata." `ReusableComponentDescriptor` requires all three
as mandatory sub-records:

```
ComponentTestMetadata:         suite_ref, passed, failed
SecurityMetadata:      review_ref, findings_cleared
CompatibilityMetadata: contract_version, compatible_with (>= 1 entry)
```

A descriptor missing any one category fails at construction. Metadata is
**always carried and never hidden**, however unfavourable —
`is_verified_reusable` is a narrower, honest derived question (zero
failing tests and no open security finding in the metadata as carried),
not a gate on whether the metadata itself may be recorded.

## 5. Empirical outcome statistics (ARK-REQ-0394, D-026)

`aggregate(outcomes: Sequence[VerifiedOutcome]) -> tuple[EmpiricalOutcomeStats, ...]`
groups by `(model_id, task_class)` and counts attempts/successes.
**Nothing is cached** — `aggregate` is a pure function of its argument,
the same "nothing is cached at any layer" shape `control.capability` (C-13)
established; calling it twice with different input produces different
output, which is how its own test proves the absence of memoisation. Only
`VerifiedOutcome` — never `SelfReportedClaim` — can occupy the `evidence`
field, so a self-reported performance claim cannot enter the aggregate at
all, D-026's rule enforced by the identical structural mechanism as §2,
not a second copy of it.

**Not wired into routing.** `engineering.factory.execution_routing.py`'s
`VERIFIED_KNOWLEDGE` tier remains in `_STRUCTURALLY_UNAVAILABLE` after this
phase; that module's own docstring defers rewiring to "a real caller,
never by editing this file's constants," and no requirement in this
phase's denominator requires this package to be that caller. Composing
`aggregate`'s output into a live routing decision is future work for
whichever phase supplies a real execution-routing caller.

## 6. Error taxonomy

| Code | Class | Meaning |
|---|---|---|
| `ARK-ERR-0140` | `UnbackedKnowledgeClaimError` | An evidence reference's `content_address` is not a canonical content address. |
| `ARK-ERR-0141` | `IllegalValidityTransitionError` | A knowledge-validity transition is not in the declared graph (§3). |
| `ARK-ERR-0142` | `IncompleteComponentMetadataError` | A reusable component's compatibility metadata declares no compatible target. |

## 7. Deliberate boundary

This contract provides the C-28 evidence-backed knowledge record and its
derived validity lifecycle, the C-28 reusable-component metadata
descriptor, and per-model/per-task-class empirical outcome aggregation. It
does **not**: persist any record across a process restart; resolve a
`content_address` against a real, currently-stored evidence record; run a
knowledge-authority query surface the way `control.capability` runs a live
`can_perform` query; wire empirical statistics into
`engineering.factory.execution_routing`'s tier selection; enforce any PDP
operation class (no action defined here maps to one of the 14 canonical
computer-use classes — recording a value object is not a computer-use
action, the same reasoning `engineering.repair`'s C-26 evidence contract
already recorded for itself); or add a 13th machine to
`STATE_MACHINES.md`. Local AI (hardware-aware adapters, fine-tuning on
verified datasets only) is Phase 22's `engineering.localai`, named in the
same MS paragraph as Knowledge but a distinct bounded context and phase,
untouched here.
