# C-22 — Harness task specification

**Contract family:** C-22 (`docs/canonical/CONTRACT_INVENTORY.md` row 22)
**Owner:** `engineering.agent`
**Kind:** `INT` — an interface contract. No table, no migration, no ORM record.
**Compatibility:** semver, STRICT
**Phase column:** `10`
**Verification:** `engineering.agent` — bounded-task tests

This document is a **derived description** of an implemented contract. It is not
an authority and may never be read as one. Where it disagrees with
`MS §Harness Engineering`, `BP §Harness Engineering`,
`docs/canonical/REQUIREMENT_REGISTER.md` or
`docs/canonical/AUTHORITY_MAP.yaml`, those win.

---

## 0. Scope of this revision — Phase 10 Atomic Package 1

**Delivered by Package 1**

- `harness_elements.py` — the canonical harness element list, **parsed** from
  both canonical documents at call time and reconciled between them.
- `harness_task.py` — the C-22 model: one bounded engineering task carrying
  every canonical element, with `reconcile_with_authority` proving the field set
  is still exactly what the documents declare.
- `errors.py` — the C-22/C-23 failure taxonomy, `ARK-ERR-0092`–`0094`.

**Not delivered by Package 1, and not claimed**

- **No requirement is discharged.** Phase 10's denominator is `ARK-REQ-0050`,
  `ARK-REQ-0051`, `ARK-REQ-0054`, `ARK-REQ-0055` and `ARK-REQ-0231`, and each is
  discharged only at phase acceptance.
- C-23 (context package + provenance) does not exist yet. C-22 carries a
  **reference** to a context package and nothing more; provenance recording and
  the no-secret assertion are `ARK-REQ-0055`'s and are a later package's.
- `ARK-REQ-0051` — agents cannot mutate canonical requirements or self-accept
  output — is owned by **`control.policy`**, not by this context, and is not
  enforced here. `acceptance_target` is a field a task *carries*; nothing in this
  package lets an agent decide its own.
- No agent runtime, no provider call, no dispatch and no execution of any kind.

---

## 1. The eight elements are read, never written down

`MS §Harness Engineering` states the primitive:

> The primitive is not "send a prompt"; the primitive is "execute a bounded
> engineering task".

and declares the elements as a `+`-joined sentence. `BP §Harness Engineering`
declares the same sentence in abbreviated form. **Both are canonical** — the
register sources `ARK-REQ-0054` to the Master Specification and `ARK-REQ-0231`
to the Build Protocol — so neither may be preferred over the other.

`HarnessElementAuthority.load` parses both, reconciles them **positionally**, and
refuses on any disagreement in count or order. Where the two spellings differ,
each must be a word-wise **abbreviation** of the other — a property that is
checked, not assumed — and the unabbreviated form is taken, because an
abbreviation carries strictly less information than what it abbreviates. There
is no alias table: one would be the same second-copy defect (F-0013) in a
different shape.

The element list and the element **count** appear nowhere in the shipping source.
A control proves this behaviourally rather than by text scan, by feeding the
parser declarations of four different sizes and requiring the reported count to
follow the document each time.

| Element | Field |
|---|---|
| Task Specification | `task_specification` |
| Context Package | `context_package` |
| Tools | `tools` |
| Permissions | `permissions` |
| Workspace | `workspace` |
| Environment | `environment` |
| Acceptance Target | `acceptance_target` |
| Repair Budget | `repair_budget` |

That table is a **rendering** of what the parser currently returns. The documents
are the authority.

---

## 2. Boundedness is structural, not policed

Every element is a **required field with no default**, and `extra="forbid"` means
an undeclared attribute cannot be attached at all. An unbounded `HarnessTask`
therefore cannot be constructed — there is no window in which a half-specified
task exists and no later audit that could be skipped. `ARK-REQ-0231` is satisfied
by the type.

`reconcile_with_authority` closes the remaining gap in **both** directions:

- a canonical element with no field would let a task be constructed unbounded in
  that dimension → `UnboundedHarnessTask`;
- a field with no canonical element would mean this contract invented a boundary
  the documents do not declare → `MalformedHarnessElement`;
- a field set in the wrong order → `MalformedHarnessElement`, because order is
  part of the declaration.

---

## 3. Empty is a bound; absent is not

`tools=()` declares that the task may use **no** tools, which is a real and
useful boundary. Omitting `tools` declares nothing. That distinction is the whole
reason no field carries a default: a default would collapse "explicitly none"
and "never stated" into one value, and the second is exactly what `ARK-REQ-0231`
forbids.

Scalar elements additionally refuse blank strings — a blank acceptance target is
not an acceptance target. `repair_budget` is a finite non-negative count;
**zero repairs is bounded**, and is not the same as unbounded.

The task is `frozen`. Bounds that can be widened after admission are not bounds.

---

## 4. What this contract is deliberately not the authority for

- **The element list** — `harness_elements.py` parses it from the documents.
- **Operation classes** — `AUTHORITY_MAP.yaml` assigns them to `control.policy`.
  `permissions` is carried as declared references and is **never** validated
  against a local vocabulary; a control asserts no module in this context
  contains a governed operation-class name. Storing one would be a shadow
  registry.
- **The context package** — C-23 is a separate contract; C-22 references it.
- **Repair convergence** — `AUTHORITY_MAP.yaml` assigns
  `repair_budget_and_convergence` to `engineering.repair`. C-22 carries the
  budget; it does not decide when repair has converged.

---

## 5. Where the errors live, and why

`ARK-ERR-0092`–`0094` are declared in `engineering.agent`, not in
`kernel.contracts`. That was **measured, not assumed**: placing them in
`kernel.contracts` took its public surface to **42** against a
`max_public_surface_per_context` budget of **40**, and the architecture gate
refused it. ADR-0008 makes decomposition the answer to a budget rather than an
exception, and an exception would require HUMAN GATE 8 plus an ADR and may not be
authored by the implementing actor. The abstract base is imported from
`kernel.contracts.error_base`, so this context adds no edge to `errors.py`, which
is at its own fan-in ceiling of 15. This follows the C-11, C-12, C-14, C-15,
C-19 and C-21 taxonomies before it.
