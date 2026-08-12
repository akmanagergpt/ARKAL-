# C-13 — Capability node + query result

**Contract family:** C-13 (`docs/canonical/CONTRACT_INVENTORY.md` row 13)
**Owner:** `control.capability`
**Kind:** `INT` — an interface contract. No table, no migration, no ORM record.
**Compatibility:** semver, STRICT
**Phase column:** `3 (schema) / 9B`
**Verification:** `control.capability` — reference-not-copy architecture test

This document is a **derived description** of an implemented contract. It is not
an authority and may never be read as one. Where it disagrees with
`docs/canonical/EXECUTION_AND_CAPABILITY.md` §1, `MS §Capability Graph`,
`ADR-0003`, `ADR-0001` or `docs/canonical/AUTHORITY_MAP.yaml`, those win.

---

## 0. Scope of this revision — Phase 9B complete (Packages 1–3)

Phase 3 delivered the **schema** half of C-13 under `ARK-REQ-0045` and
`ARK-REQ-0049`. Phase 9B delivers the **activation** half, in three atomic
packages. This revision records all three; the Package 1 scope note below is
retained verbatim as the record of what that package alone delivered.

**Delivered by Package 2 — the activated verdict**

- `CapabilityGraph.can_perform` composes Package 1's per-reference resolutions,
  the node's own `configured_state` and its graph-owned `prerequisites`
  (transitively, cycle-checked) into one determinate `CapabilityQueryResult`.
- The negative state is `NOT_CONFIGURED` and is **derived, not chosen**:
  `EXECUTION_AND_CAPABILITY.md` §4 pairs *resolving* with *not being*
  `NOT_CONFIGURED`. `FAIL` is assigned to no capability query by the canonical
  set and would be misread as success by the unchanged accepted Phase 8
  predicate; `UNSUPPORTED` is canonically another context's verdict. See
  `activated_query.py` for the full derivation.
- Proven through the real `AdmissionService`: a fully resolved configured
  capability reaches `ADMITTED`, the first time production admission can succeed
  at all. Pre-activation behaviour is byte-for-byte unchanged.

**Delivered by Package 3 — composition and acceptance**

- The composed integration evidence
  (`backend/tests/capability/test_phase_9b_journey.py`): the eight-step journey
  from governed activation phase, through pre-activation silence, the parsed
  binding, query-time resolution, determinism without caching, reference-never-
  copy, transitive prerequisites, to a real admission decision.
- `docs/acceptance/phase_9B_traceability.json` and
  `docs/acceptance/phase_9B_report.json`, and the single phase gate run.
- **No module under `backend/arkali/` was changed by Package 3.** The contract
  this document describes is the one Packages 1 and 2 built.

**What activation still does not mean.** No provider runtime, no network or
socket access, no live health, no cost metering, no fallback selection and no
external-provider result exists (D-023). Every affirmative in the evidence
composes composition-root doubles for `control.registry.provider`,
`control.policy` and `control.isolation` — the evidence-requirement authority is
the real `RequirementRegister` — because no provider runtime exists and none may
be fabricated. **No production capability has been declared configured with real
identities anywhere in this repository.** The *mechanism* is proven; a configured
production capability is not claimed.

---

### Retained: scope note as written at Package 1

**Delivered by Package 1**

- The canonical reference→authority binding, parsed from the
  `capability_node:` block in `EXECUTION_AND_CAPABILITY.md` §1 at call time
  (`reference_authority.py`).
- Query-time resolution of every external reference against its owning
  authority, through injected interfaces (`reference_resolution.py`).
- `CapabilityGraph.resolve_references`, which performs that resolution on
  demand and stores nothing.

**Not delivered by Package 1, and not claimed**

- `can_perform` is **unchanged**. It still answers `NOT_CONFIGURED` before the
  activation phase and still refuses to invent a verdict at it. Composing a set
  of resolutions into one determinate answer to "Can I perform this?" is
  Package 2.
- **No requirement is discharged.** `ARK-REQ-0046`, `ARK-REQ-0047` and
  `ARK-REQ-0048` are Phase 9B's denominator and are discharged only at phase
  acceptance. Cumulative verified is unchanged.
- Production admission still returns `CAPABILITY_NOT_CONFIGURED`
  (`EXECUTION_AND_CAPABILITY.md` §4 condition (a) against the pre-activation
  graph). That is the honest position and it is preserved deliberately.

---

## 1. The node schema is reused, never replaced

`CapabilityNode` is the Phase 3 model and is **unmodified** by this package. It
declares exactly the twelve fields of the canonical block, is frozen, and is
`extra="forbid"`, so an undeclared attribute cannot be attached at all. There is
one capability node model and one graph class in the repository; a control
asserts that no second one exists.

Reuse is load-bearing rather than tidy. A second node type or a second graph
would be a second capability authority, and
`AUTHORITY_MAP.yaml` assigns `capability_availability_answer` to exactly one
owner.

---

## 2. Which authority resolves which reference

The binding is **parsed, never transcribed**. Each reference field in the
canonical block carries a `# -> <context>` annotation naming its owner, and
`CapabilityReferenceAuthority` reads them at call time. The table below is a
rendering of what that parser currently returns; it is documentation, and the
document is the authority.

| Field | Target kind | Resolved by |
|---|---|---|
| `prerequisites` | `capability_id` | the graph's own node set |
| `permission_refs` | `policy_rule_id` | `control.policy` |
| `evidence_requirement_refs` | `ark_req_id` | `control.specification` |
| `provider_refs` | `provider_id` | `control.registry.provider` |
| `isolation_backend_probe_ref` | `probe_id` | `control.isolation` |
| `fallback_refs` | `capability_id` | the graph's own node set |

Capability-to-capability references are resolved by the graph at construction
and have been since Phase 3. The four external authorities are resolved at query
time, which is what §1's resolution rule requires.

---

## 3. Resolution is by interface, because the import is forbidden

`control.capability` is layer rank 1. So are `control.policy`,
`control.specification`, `control.registry.provider` and `control.isolation`.
`AUTHORITY_MAP.yaml` sets `allow_same_layer: false` and declares no sibling edge
for this context, so the import does not exist and may not be created.
`ARCHITECTURE.md` §4 rule 3 states the answer: inversion by interface.

`ReferenceResolver` is therefore a `Protocol` declared in this context, and the
composition root supplies implementations. This is the same shape
`execution.scheduler` already uses to ask *this* context its own question.

The `policy_callable_from_any_layer` exemption is **not** used. It exists for PEP
call sites, and `test_live_repository_uses_no_exempt_edge` refuses a live edge
that leans on it — the same call Phase 6 Package 2 and Phase 9 Package 1 both
made.

---

## 4. What a resolver may be asked, and what it may return

```
resolves(reference: str) -> bool
```

That is the entire question. A resolver reports whether its authority declares
the identifier. It is never asked for the value behind it, and there is no field
anywhere in this context that could hold one.

This is what makes `ARK-REQ-0047` and `ARK-REQ-0053` structural rather than
policed. Provider identity, model identity, configuration, health, availability,
cost metadata and fallback are owned by `control.registry.provider`
(`AUTHORITY_MAP.yaml` `provider_authority.fields_owned`). The Capability Graph
holds `provider_refs` and resolves them; it stores, caches, mirrors, defaults,
aliases and re-derives none of them, and the `shadow_registry` gate reads this
context's source on every run to prove it.

---

## 5. Outcomes, and the fail-closed rule

One `ReferenceResolution` per reference, carrying the canonical `HonestState`:

| Condition | State | Meaning |
|---|---|---|
| a supplied resolver answered true | `PASS` | the authority resolves this reference |
| a supplied resolver answered false | `FAIL` | the authority does not resolve it |
| no resolver supplied for that authority | `NOT_CONFIGURED` | the authority was not composed; neither granted nor denied |

**`PASS` is reachable only through a live authority's affirmative answer.** There
is no branch in which an absent, silent or unsupplied authority produces a
resolved reference. A missing resolver never defaults, a refusing resolver is
never retried into success, and an unknown reference is never assumed.

`resolve_references` **refuses** when no authorities are composed at all, rather
than returning an empty tuple. An empty answer would be indistinguishable from
"every reference resolved", which is exactly the stub `ADR-0003` forbids.

A resolver supplied for an authority the canonical schema does not name is
refused at construction.

---

## 6. Nothing is cached

`ReferenceResolvers` holds the binding authority and the resolvers. It holds no
outcome: there is no memo, no last-answer field and no lazy default, and
`CapabilityGraph` stores no resolution either. Every call re-asks every
authority, so an authority that changes its answer between two calls is observed
on the second call.

`ADR-0003` places the no-caching obligation on consumers, and a Phase 8 control
counts the authority's calls to enforce it there. A graph that cached would make
that consumer rule unenforceable from below, which is why the rule is kept here
as well.

---

## 7. Boundary — what this contract is not the authority for

- **The capability verdict.** Package 2 composes resolutions into
  `CapabilityQueryResult`. Until then `can_perform` answers as it did at Phase 3.
- **Provider state of any kind.** `control.registry.provider` (C-11, ADR-0001).
- **Policy decisions.** `control.policy` owns AUTO/ASK_USER/DENY; resolving a
  `permission_refs` entry asks whether a rule exists, never what it decides.
- **Isolation property satisfaction.** `control.isolation` owns tier
  requirements, backend properties and composition; `AUTHORITY_MAP.yaml`
  `isolation.capability_state_when_unsatisfiable` is that authority's data.
- **Admission, allocation and dispatch.** `execution.scheduler` (C-21, Phase 8).
- **Provider runtime and any external call.** No provider is contacted anywhere
  in this contract, and no external-provider result exists or is claimed.
- **Evidence graph, coverage and verdicts.** C-16, Phase 13.
- **Failure-domain isolation.** `ARK-REQ-0354`, Phase 31. NOT CLAIMED.

---

## 8. Error taxonomy

Reused from `kernel.contracts.capability_errors`, unchanged. No new error class
was added: `InvalidCapabilityReference` is already documented as "a reference
points at a capability **or authority** that does not resolve", which is the
condition this package makes reachable.

| Error | Raised when |
|---|---|
| `InvalidCapabilityReference` | resolution requested with no composed authorities; a reference field holds neither an identifier nor a tuple of them |
| `AuthoritativeSourceError` | the canonical schema block is absent, declares no field, declares no external reference, declares no capability-to-capability reference, names a context the authority map does not declare, or declares a field the node model does not carry; a resolver is supplied for an unnamed authority |
| `PrematureActivation` | unchanged from Phase 3 — `can_perform` at the activation phase, and `activate()` |

---

## 9. What remains before Phase 9B can be accepted

1. **Package 2 — the activated query.** Compose resolutions into one determinate
   `CapabilityQueryResult`, derived from canonical authority. The canonical set
   states the resolution rule but does **not** state the verdict for an
   unresolved external reference; that mapping must be derived from
   `AUTHORITY_MAP.yaml` and the honest-state rules, or the ambiguity reported
   before implementation. This package deliberately left it open rather than
   guessing.
2. **Package 3 — composition, traceability, the C-17 report and the gate.**
   `ARK-REQ-0046`, `ARK-REQ-0047` and `ARK-REQ-0048` are discharged there, and
   nowhere earlier.
