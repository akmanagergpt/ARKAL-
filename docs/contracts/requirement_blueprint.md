# C-37 Requirement + Architecture Blueprint — derived contract

**Owner:** `control.specification`
**Kind:** GRAPH
**Version:** 1.0.0
**Lifecycle:** STRICT

This document records the executable Phase 15 contract derived from D-025
(`docs/build/DECISION_LOG.md`), `REQUIREMENT_REGISTER.md` Block 8
(`ARK-REQ-0381`–`0391`) and `CONTRACT_INVENTORY.md`. It does not replace those
authorities.

## Why this is a separate contract from C-04

`C-04` (`requirement_record.py`) is ARKALI's own canonical governance
requirement register — immutable `ARK-REQ-####` entries with a phase and an
owning component, the sole denominator for coverage. A human product goal is a
different kind of thing entirely: mutable across revisions, owned by no phase,
never discharged by or discharging canonical coverage. `ARK-REQ-0388` requires
the two to stay structurally distinct, so `CandidateRequirement` carries no
`req_id`, no `owning_phase`, and is never accepted by `RequirementRegister`.

## Product goal

`ProductGoal.goal_text` is the human-submitted natural-language goal, preserved
verbatim. `goal_id` is its content address — the provenance root every derived
requirement traces back to (`ARK-REQ-0382`).

## Decomposition

`decompose()` splits a goal into candidate requirement statements using two
rules only: explicit enumeration markers (`-`, `*`, `1.`, `1)`) when present,
otherwise sentence boundaries. This is Deterministic Core, not Probabilistic
Edge — it performs no semantic understanding, and none is claimed. Real
natural-language comprehension is out of scope for this contract and awaits a
future ruling that authorizes an AI-assisted Probabilistic Edge stage.

## Classification

`classify()` matches a closed keyword vocabulary against seven categories
(functional, non-functional, security, data, integration, UI, operations) plus
`UNCLASSIFIED`. A statement matching no keyword stays `UNCLASSIFIED` — the
vocabulary's eighth member, not an absence of one (`ARK-REQ-0385`).

## Acceptance criteria

`derive_acceptance_criteria()` extracts a criterion only from a statement
anchored to a modal (`must`/`shall`/`should`) carrying an explicit numeric
constraint pattern (`at least N`, `within N`, …). Everything else is left
empty and recorded as `MISSING_ACCEPTANCE_CRITERIA` on the blueprint
(`ARK-REQ-0384`).

## Architecture / capability mapping

`map_architecture()` scores every concern in the live `AuthorityMap.concerns`
by shared word tokens against the requirement's own text and category, and
returns the highest-scoring concern name or `None`. No `category -> owner`
table exists anywhere in this contract: the owner is always whatever
`AUTHORITY_MAP.yaml` currently declares for the matched concern
(`ARK-REQ-0386`).

## Ambiguity, contradiction, underspecification

Three closed, lexical, deterministic signals — never inferred semantics:

- **AMBIGUOUS** — the statement contains an alternative or to-be-determined
  marker (`tbd`, `unclear`, `maybe`, `possibly`, `unsure`, `either`, `or`).
- **UNDERSPECIFIED** — the statement is fewer than three words, or uses a
  vague qualifier (`fast`, `good`, `scalable`, …) with no accompanying digit.
- **CONTRADICTORY** — two statements assert different numeric values for the
  same recognised constraint subject (response time, uptime, capacity).

Every detected question is recorded as an `UnresolvedQuestion` on the
blueprint. None is silently resolved by invented semantics (`ARK-REQ-0383`).

## Revision identity

`RequirementBlueprint.blueprint_id` is a content address over the blueprint's
own canonical bytes — goal id, revision number, previous blueprint id, and
every requirement's id/category/concern/criteria plus every unresolved
question. Identical input at the same revision always addresses identically,
in any process, on any host. A later revision over a changed goal carries
`previous_blueprint_id`, so lineage is comparable (`ARK-REQ-0389`).

## Boundaries

- **No product code.** `derive_blueprint` performs no filesystem or process
  I/O and defines no generation, build or write operation. Product/software
  generation is Phase 16's sole responsibility (`ARK-REQ-0390`).
- **No acceptance verdict.** `RequirementBlueprint` carries no PASS/FAIL/
  ACCEPTED field of any kind. `acceptance.engine` remains the sole acceptance
  authority over any blueprint or downstream candidate (`ARK-REQ-0391`).

## Consumption

The contract is a plain, content-addressed, JSON-serializable Pydantic model
(`model_dump_json`/`model_validate_json` round-trips byte-identically). A
future Phase 16 consumer reads the JSON shape; it does not import Phase 15's
Python objects, and Phase 15 does not import Phase 16's.
