# C-21 — Worker contract (class, limits, tier)

**Owner:** `execution.scheduler` · **Producer:** worker implementations · **Consumers:** scheduler
**Kind:** INT · **Versioning:** **semver** · **Compatibility:** **ADDITIVE** · **Phase:** 8
**Verified by:** `execution.scheduler` — admission tests

All fields above are the `CONTRACT_INVENTORY.md` row for C-21, not a restatement.
Where this document and the code or the canonical set disagree, they win and this
document is the defect.

## 0. Scope of this revision — Phase 8 Atomic Package 2

Package 2 adds the **admission decision** — §7 below. The declaration half from
Package 1 is unchanged: no dimension was added, removed or reinterpreted, and
`WorkerDeclaration` is byte-for-byte the same contract.

**Two halves, deliberately separate.** §2 and §3 are the *worker declaration
schema*: what a worker states about itself. §7 is *scheduler admission
semantics*: what `execution.scheduler` does with that statement. C-21's
inventory row names both — it is the worker contract, verified by *admission
tests* — but a consumer that only produces declarations depends on §2/§3 alone.

**No requirement is discharged by either package.** The register assigns Phase 8
**zero** `ARK-REQ` entries, so there is nothing to discharge and nothing is
claimed. Cumulative verified stays at 80. C-21 is evidenced as a *contract* —
this document, the controls below, and `public_contracts` in the eventual C-17
report — and no `ARK-REQ` anchor is fabricated for it.

### Scope of the earlier revision — Phase 8 Atomic Package 1

Package 1 delivered the **declaration** half of C-21: what a worker states about
itself, and the validation that makes the statement canonical. `execution
.scheduler` holds `worker_vocabulary` (the canonical classes and dimensions,
parsed) and `worker_contract` (the declaration model and the declaration
authority, PEP-governed).

**Not implemented, not claimed, and not represented by an unused field:** queue
ordering, priority, fairness, autoscaling, worker lifecycle state, scheduler
lifecycle state, retry policy, job timeout, checkpoints, provider configuration
or runtime, capability activation, and failure-domain verification. Failure-domain
isolation is `ARK-REQ-0354`, which the register assigns to **Phase 31**; it is
named here as NOT CLAIMED. ADDITIVE compatibility means a dimension can be added
later without breaking a consumer, so nothing is lost by waiting.

## 1. Compatibility semantics

**ADDITIVE** means the canonical set may add a declaration dimension, and a
consumer compiled against version *N* must keep working against *N+1*. It does
**not** mean a worker may add one: `WorkerDeclaration` is `extra="forbid"`, so a
declaration carrying a seventh dimension is refused. Dimensions are added by the
canonical document, never by a declaring worker.

The contract is **INT** — an internal interface. There is no wire format, no
table, no migration and no ORM record, and a structural control asserts that
`execution.scheduler` builds no engine, opens no session and issues no SQL.

## 2. The six declaration dimensions

`EXECUTION_AND_CAPABILITY.md` §4 is the sole authority for this list, which is
parsed at call time rather than transcribed into code. The `Field` column is the
single binding site between canonical prose and Python identifiers, and a
control reconciles this table, that binding and the parsed canonical list in
**all** directions.

| Canonical dimension | Field | Refused when |
|---|---|---|
| `class` | `worker_class` | not one of the canonical classes in §3, exactly as spelled |
| `concurrency limit` | `concurrency_limit` | less than 1 — a worker admitting no work is not a worker |
| `resource profile` | `resource_profile` | empty or blank |
| `required TRUST tier` | `required_trust_tier` | not a tier `control.isolation` declares |
| `required isolation properties` | `required_isolation_properties` | any name outside the canonical property set, or repeated |
| `heartbeat interval` | `heartbeat_interval` | not strictly positive |

### 2.1 `resource profile` has no canonical vocabulary yet

The canonical set names the dimension and does not enumerate profiles. C-21
therefore constrains only that a profile **is declared**, not which profiles
exist. Inventing a profile vocabulary here would create an authority the
canonical set does not grant, so the refusal is limited to emptiness. When a
profile vocabulary becomes canonical, this dimension gains membership validation
the way `worker_class` already has it — an additive change.

### 2.2 The tier and the properties are not composed here

A tier already implies required properties, and a worker separately declares the
properties it requires; §4 lists both as distinct dimensions. Asking whether the
two **compose** is the isolation half of admission and belongs to Package 2.
What Package 1 checks is only that each declared property exists in the canonical
set — the forged-capability check applied to the requiring side, mirroring the
check `control.isolation` already applies to a backend's *provided* properties.

### 2.3 The heartbeat interval is a declaration, not a mechanism

C-21's heartbeat interval is a value a worker states. It is **not** C-19's
persisted execution heartbeat, its ownership record, or its liveness sweep.
Nothing in `execution.scheduler` emits, stores, expires or watches a heartbeat,
and nothing here reads or writes a durable job. Every assertion about the
interval is a comparison; no control sleeps.

## 3. The seven canonical worker classes

Read from `EXECUTION_AND_CAPABILITY.md` §4 and preserved in canonical spelling.
Case, separators and word order are exact: `Agent`, `build_test`, `local-ai` and
`computer use` are all refused, because a second spelling is a second vocabulary.

| Class |
|---|
| `agent` |
| `provider` |
| `build/test` |
| `browser` |
| `sandbox` |
| `local-AI` |
| `computer-use` |

A declaration is keyed by its class, and a second declaration for the same class
is refused: identity is not one of the six dimensions, so keying by class is what
the canonical set permits, and a duplicate would make the read answer with
whichever arrived last. A fleet of many workers per class is **not** C-21 and is
not built here.

## 4. Governed access

Every operation that reads canonical worker data passes an **injected PEP with no
default**, under `READ_FILE` — the class `evidence.audit` and `execution.durable`
already use for governed reads. No new operation class is invented, and
`unmapped_action_resolution: DENY` means none could be.

The decision is taken **before** the read, so a DENY prevents it rather than
annotating it: a denied `declare` records nothing, and `declared_classes()`
stays empty. The canonical documents are re-read on every governed operation and
never cached between calls, which is the same call-time-parsing rule the
requirement register, the governance state and the isolation authority follow.

`declared_classes()` is deliberately **ungoverned**: it reads the object's own
memory and opens no canonical document, so guarding it would claim an
enforcement that performs no governed operation.

## 5. Boundary — what this contract is not the authority for

`execution.scheduler` and `execution.durable` are both layer rank 3,
`allow_same_layer` is false, and `AUTHORITY_MAP.yaml` declares **no** sibling
edge between them in either direction. Neither imports the other, and controls
on both sides assert it.

C-19 remains the sole authority for durable job identity, lifecycle state,
execution attempts, heartbeat ownership, retry accounting, timeout, cancellation,
pause/resume, crash recovery, checkpoints, idempotency and dead-letter semantics.
C-21 duplicates, inspects and mutates none of them, and Package 1 reads no C-19
record at all.

`control.isolation` remains the sole authority for the five TRUST tiers and the
seven isolation properties; `execution.scheduler` asks it rather than holding a
copy, which is legal because rank 3 may depend on rank 1. An unknown tier raises
that context's own `TrustTierViolation`, unchanged — re-raising it as a scheduler
error would make this context look like a second tier authority.

The Capability Graph is schema-only until **Phase 9B**. Before activation every
capability query returns `NOT_CONFIGURED`, which §1 of the canonical document
calls a determinate answer rather than a stub. Package 2 must honour that and may
correctly be unable to admit any job; Package 1 does not query capabilities at
all.

## 6. Error taxonomy

Codes are allocated from 0081 upward; 0070–0080 belong to `execution.durable`.

| Code | Type | Raised when |
|---|---|---|
| `ARK-ERR-0081` | `UnknownWorkerClass` | a class outside the canonical seven |
| `ARK-ERR-0082` | `InvalidWorkerDeclaration` | a dimension is absent, empty or out of bounds |
| `ARK-ERR-0083` | `ForgedIsolationRequirement` | a required property the canonical set does not define |
| `ARK-ERR-0084` | `DuplicateWorkerDeclaration` | a class is declared twice |
| `ARK-ERR-0085` | `UndeclaredWorkerClass` | a canonical class with no declaration is required |
| `ARK-ERR-0087` | `InvalidResourceAvailability` | an availability snapshot reports an impossible value |

An unknown TRUST tier is **not** in this table: it raises
`control.isolation`'s `TrustTierViolation`, because that context owns the
vocabulary.

## 7. Scheduler admission semantics

This section describes what `execution.scheduler` **does** with a declaration.
It is not part of the declaration schema: a worker producing a §2 declaration
conforms to C-21 whether or not it is ever submitted for admission.

`EXECUTION_AND_CAPABILITY.md` §4 is the sole authority: a job is admitted only
when **(a)** its capability resolves other than `NOT_CONFIGURED`, **(b)** an
isolation composition satisfies its tier, and **(c)** resource budget is
available. **All three are required.** There is no fourth condition.

| Outcome | Meaning |
|---|---|
| `ADMITTED` | all three canonical conditions hold |
| `CAPABILITY_NOT_CONFIGURED` | condition (a) — the capability did not resolve |
| `ISOLATION_UNSATISFIED` | condition (b) — the declared tier or a declared property is not satisfiable |
| `RESOURCE_UNAVAILABLE` | condition (c) — the concurrency limit is reached or the profile is unavailable |

Exactly one member per condition, plus the one way all three can hold. The
decision is a returned value, not a lifecycle: it has no transitions and no
persistence, and `execution.scheduler` still declares no state machine.

### 7.1 The capability predicate is the canonical one, not a stricter one

Condition (a) is implemented as `state is not NOT_CONFIGURED`, which is §4's
wording exactly. It is deliberately **not** narrowed to `state is PASS`: that
would be a rule the canonical set does not state, and inventing a stricter rule
is as much an invention as a weaker one. Post-activation resolution semantics
belong to **Phase 9B**, which owns the graph.

### 7.2 Before Phase 9B, production admission cannot succeed

§1 delivers the Capability Graph schema at Phase 3 and activates it at **Phase
9B**; before activation every query returns `NOT_CONFIGURED`, "a determinate
answer, never a stub, default or assumption". Production admission therefore
returns `CAPABILITY_NOT_CONFIGURED` for every request, and **that is designed
behaviour, not a stub**. The mechanism is real and complete; the answer is
honest.

The `ADMITTED` path is exercised only with a test-only resolver implementing the
same question. A control asserts that no module under `backend/arkali/` outside
`control.capability` answers `can_perform`, so that resolver cannot be
substituted into production.

### 7.3 No cached capability verdict

§1 names `execution.scheduler` (Phase 8) as a consumer that must handle
`NOT_CONFIGURED` **and must not cache capability verdicts**. The evaluator
therefore holds the *resolver* and never a result: it has exactly one attribute,
no memoisation and no "last answer", and every evaluation is a fresh question.
A control counts the authority's calls rather than the caller's, because calling
twice proves nothing about whether the authority was asked twice.

### 7.4 Evaluating admission changes nothing

Admission is a **test**, not an allocation. Nothing is reserved, claimed,
assigned, dispatched, queued, prioritised or started; no capacity is consumed;
no durable job is read or written. Evaluating the same request twice returns the
same answer and leaves the availability snapshot untouched. Availability is a
frozen input supplied per evaluation, not a resource universe this context owns.

### 7.5 A policy denial is not an admission outcome

Every admission evaluation passes the same injected PEP under `READ_FILE`, and
the decision is taken **before** any condition is evaluated. A denial raises
`PolicyDenied` and is never reclassified as a capability, isolation or resource
verdict: the three outcomes mean the canonical conditions were evaluated and one
did not hold, while a denial means the evaluation was not permitted at all.

### 7.6 Evaluation order is implementation behaviour

§4 states a conjunction and defines no order. The implementation evaluates
capability, then isolation, then resource, and short-circuits — a deterministic
choice that affects only *which* refusal is reported when more than one condition
fails, never *whether* a request is admitted. The conjunction, not the order, is
what is canonical.

## 8. What Package 3 adds

Final integration and evidence, a zero-requirement traceability record
(`claims: []` against an empty denominator), the C-17 report and the machine
gate — only if earned.
