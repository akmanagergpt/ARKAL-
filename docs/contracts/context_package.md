# C-23 — Context package + provenance

**Contract family:** C-23 (`docs/canonical/CONTRACT_INVENTORY.md` row 23)
**Owner:** `engineering.agent`
**Kind:** `INT` — an interface contract. No table, no migration, no ORM record.
**Compatibility:** semver, STRICT
**Phase column:** `10`
**Verification:** `engineering.agent` — **no-secret assertion**

This document is a **derived description** of an implemented contract. It is not
an authority and may never be read as one. Where it disagrees with
`MS §Context Compiler`, `docs/canonical/REQUIREMENT_REGISTER.md` or
`docs/canonical/AUTHORITY_MAP.yaml`, those win.

---

## 0. Scope of this revision — Phase 10 Atomic Package 2

**Delivered by Package 2**

- `context_kinds.py` — the admissible context kinds, **parsed** from
  `MS §Context Compiler` at call time.
- `context_package.py` — `ContextItem` and `ContextPackage`: only admissible
  kinds, provenance required per item, the C-09 no-secret guard applied to every
  string, and a canonical `context_hash`.

**Not delivered by Package 2, and not claimed**

- **No requirement is discharged.** Phase 10's denominator is five and each is
  discharged only at phase acceptance.
- **No Context Compiler exists.** This is the compiler's output *contract*.
  Nothing here selects context, reads a repository, ranks relevance or decides
  what a model should see; `ContextPackage.compiled` validates what a caller
  supplies.
- `ARK-REQ-0050` and `ARK-REQ-0051` are not addressed. `ARK-REQ-0051` is owned
  by **`control.policy`** and will not be discharged from this context.
- No provider call, no dispatch, no execution.

---

## 1. "Only relevant" is a closed vocabulary, not a judgement

`MS §Context Compiler` is one sentence:

> ARKALI sends only relevant files, symbols, contracts, tests, ADRs, failures
> and verified knowledge to a model. Context provenance is recorded.

That sentence **enumerates** the admissible kinds, so relevance is not something
this contract decides — it is a closed vocabulary the canonical document
declares, and anything outside it is refused. `ContextKindAuthority` parses the
enumeration at call time, anchored to the canonical verb phrase so ordinary prose
in the section cannot be mistaken for it.

The kind list and its **count** appear nowhere in the shipping source, proven
behaviourally by feeding the parser vocabularies of three different sizes. An
absent section, a section with no enumeration, and a single-kind enumeration are
each refused: a relevance rule with nothing to exclude would pass vacuously.

| Kind | Identifier |
|---|---|
| files | `files` |
| symbols | `symbols` |
| contracts | `contracts` |
| tests | `tests` |
| ADRs | `adrs` |
| failures | `failures` |
| verified knowledge | `verified_knowledge` |

A **rendering** of what the parser currently returns. The document is the
authority.

---

## 2. Provenance is per item, and required

`ARK-REQ-0055`'s second clause is "Context provenance is recorded". A
package-level note records nothing useful — the question a reader has is *which*
file, symbol or failure a particular claim came from. `origin` is therefore a
required field on every `ContextItem` with no default, and blank is refused. An
item without provenance cannot be constructed.

Items are frozen. Provenance that can be edited after the fact is not provenance.

---

## 3. The no-secret assertion is C-09's, reused

`CONTRACT_INVENTORY.md` row 23 names the **no-secret assertion** as this
contract's verification. It is implemented by calling
`control.policy.secret_reference.assert_no_raw_secret`, whose own docstring names
the context package as one of the sinks raw values must never reach.
`engineering.agent` is layer rank 4 and `control.policy` is rank 1, so the import
is a legal downward edge, and `policy_callable_from_any_layer` permits the call
besides.

The guard is **reused, never reimplemented**. Copying its shape pattern here
would create a second authority for what a secret looks like and the two would
drift — the same defect the provider reference-only rule exists to prevent,
applied to secrets. A control reads this context's source and fails if a
raw-secret pattern appears in it.

Every string the package carries is scanned, derived from the model rather than
field by field, so a field added later is scanned the day it appears. The sink
name is reported so a negative control can assert **which** boundary refused
rather than that something somewhere raised (F-0017).

---

## 4. `context_hash` is the interlock with C-14

The accepted Phase 6 `ArtifactProvenanceRecord` already carries a `context_hash`
field: an artifact's provenance is meant to bind to the exact context its
producer saw. `ContextPackage.context_hash` computes that value using
`kernel.contracts.content_address` — the same canonical addressing C-14 uses —
over a deterministic rendering of the package.

Identical content addresses identically; any change to any item's kind,
identifier or origin changes the address; and **order is part of the context**,
because a different order is a different context to a model.

---

## 5. What this contract is deliberately not the authority for

- **The admissible kinds** — `context_kinds.py` parses them from the document.
- **Whether a payload may be sent at all** — `control.policy`'s question.
- **Artifact storage and evidence** — C-14 and C-15 own those. A context package
  writes neither; one that did would be a second evidence writer.
- **The harness elements** — C-22 and `harness_elements.py`. C-22 carries a
  context package identifier and C-23 carries a task identifier; neither embeds
  the other.
