# C-11 — Provider/model record

**Owner:** `control.registry.provider` · **Producer:** registry · **Consumers:** capability, scheduler, agent, operations
**Kind:** INT · **Versioning:** **semver** · **Compatibility:** **STRICT** · **Phase:** 9
**Verified by:** `control.registry.provider` — shadow-registry gate

All fields above are the `CONTRACT_INVENTORY.md` row for C-11, not a restatement.
Where this document and the code or the canonical set disagree, they win and this
document is the defect.

## 0. Scope of this revision — Phase 9 Atomic Package 1

Package 1 delivers the **record**: what the Provider/Model Registry is the sole
authority for, and the validation that makes a record truthful.
`control.registry.provider` now holds `provider_authority` (the owned concerns
and the reference-only consumers, parsed from `AUTHORITY_MAP.yaml` at call time)
and `provider_record` (the C-11 record itself).

**No requirement is discharged by this package.** Phase 9 owns three —
`ARK-REQ-0052`, `ARK-REQ-0053` and `ARK-REQ-0219` — and each is discharged only
at phase acceptance, against evidence that exists then. Cumulative verified stays
at **80** until Phase 9 is accepted.

**Not implemented, not claimed, and not represented by an unused field:**
provider execution of any kind, HTTP or socket access, live health measurement,
cost metering, fallback *selection*, Capability Graph activation, the agent
runtime (Phase 10), the local-AI adapter (Phase 22) and the operations dashboard.
Nothing here contacts a provider, and nothing simulates one.

## 1. Compatibility semantics

**STRICT** means a consumer compiled against version *N* must not be silently
broken by *N+1*. Concerns are added by the canonical set, never by a caller:
`ProviderRecord` is `extra="forbid"`, so a record carrying an eighth concern is
refused rather than absorbed.

The contract is **INT** — an internal interface. C-12, the Project/Revision
Registry, is `DB+INT` and was persisted at Phase 5; **C-11 is not**. That
difference is governed data in the contract inventory, and it is why this package
adds no table, no migration and no ORM record. A control re-reads the inventory
row and fails if the kind ever changes, so the reasoning cannot silently expire.

## 2. The seven owned concerns

`AUTHORITY_MAP.yaml` `provider_authority.fields_owned` is the sole authority for
this list, which is parsed at call time rather than transcribed into code. It is
the machine-readable form of `MS §Provider and Agent separation`: *"The
Provider/Model Registry is the sole canonical authority for provider identity,
model identity, provider configuration, health, availability, cost metadata and
provider fallback configuration."*

| Concern | Meaning | Refused when |
|---|---|---|
| `identity` | the provider's own identifier | not a dotted lowercase identifier |
| `model_identity` | the models this provider serves | any entry is malformed |
| `configuration` | C-09 secret **references** | — (a raw value cannot be represented) |
| `health` | a state of the canonical `ProviderHealth` machine | the state is not one the machine declares |
| `availability` | free-form availability metadata | it carries a raw-secret shape |
| `cost_metadata` | free-form cost metadata | it carries a raw-secret shape |
| `fallback` | identities of providers to fall back to | malformed, or the provider names itself |

A control reconciles this table, the model's fields and the canonical map in
**all** directions, so a concern added to, removed from or renamed in the map
fails rather than drifting.

### 2.1 Health is the canonical machine's, not this record's

The `ProviderHealth` state machine was delivered at **Phase 3** and
`AUTHORITY_MAP.yaml` already assigns its authority to this context. The record
reads `DEFINITION.states` and refuses anything outside it. It declares no state,
no transition and no second machine, and a control asserts that no module in this
context except the machine itself contains a health-state literal. **The canonical
machine count stays at 12.**

### 2.2 Configuration cannot carry a secret

Provider configuration is where an API key would in practice be smuggled into a
governed record. `configuration` therefore holds C-09 `SecretReference` handles,
which by construction have nowhere to put a raw value, and the two free-form
fields are scanned for raw-secret shapes and refused. `ARK-REQ-0100` forbids any
automated actor writing, reading or exporting a raw secret; this makes that a
property of the type rather than a convention to be remembered.

Detection **refuses**; it never sanitises a value into acceptability.

### 2.3 Fallback is a reference, not a copy

`fallback` holds provider *identities*. It does not copy the fallback target's
configuration, health, availability or cost, because that would be precisely the
shadow registry `ARK-REQ-0053` forbids. Resolving a fallback is a query against
the registry, at query time.

## 3. Sole authority, and what that means for consumers

`AUTHORITY_MAP.yaml` declares `copying_permitted: false` and
`caching_permitted: false`, and names five reference-only consumers. Per
`ARK-REQ-0053`, no component may store, cache, mirror, default or re-derive these
values; all consumers resolve them from the Registry at query time.

Package 1 establishes the authority side of that rule. **Source-level enforcement
across the consumers is a later Phase 9 package** — today the `shadow_registry`
gate validates the *declaration* (owner, consumer set, copying and caching flags)
rather than consumer source, and that gap is stated here rather than papered over.

## 4. Boundary — what this contract is not the authority for

The **Capability Graph** holds `provider_refs` and resolves them at query time
(ADR-0001, ADR-0003); it stores no provider state and has no health field at all.
Activation is **Phase 9B**, so every capability query still returns
`NOT_CONFIGURED` and Phase 8 admission still refuses with
`CAPABILITY_NOT_CONFIGURED`. Package 1 changes neither.

`provider` is also one of the seven canonical **C-21 worker classes**. That is a
vocabulary entry in `execution.scheduler`, not a licence to run a provider, and a
Phase 8 control keeps the two separate. Nothing in this contract widens C-21.

`ARK-REQ-0219` forbids fabricating or simulating an external-provider result.
Package 1 produces no provider result of any kind, honest or otherwise, so there
is nothing here to fabricate.

## 5. Error taxonomy

Codes are allocated from 0088 upward; 0081–0087 belong to `execution.scheduler`.

| Code | Type | Raised when |
|---|---|---|
| `ARK-ERR-0088` | `InvalidProviderIdentity` | a provider, model or fallback identity is malformed or self-referential |
| `ARK-ERR-0089` | `RawSecretInProviderConfiguration` | free-form metadata carries a raw-secret shape |
| `ARK-ERR-0090` | `ForeignProviderConcern` | a concern the canonical map does not assign here |
| `ARK-ERR-0091` | `UnknownProviderHealthState` | a state the canonical machine does not declare |

An illegal health **transition** is not in this table: it is refused by the
canonical `ProviderHealth` machine and raises that machine's own typed error,
because this registry is not a second transition authority.

## 6. What later Phase 9 packages add

Source-level enforcement of `ARK-REQ-0053` across the five reference-only
consumers; the `ARK-REQ-0219` never-fabricate control owned by
`acceptance.engine` with its provenance and security evidence; and final
integration, traceability carrying three real claims, the C-17 report and the
machine gate — only if earned.
