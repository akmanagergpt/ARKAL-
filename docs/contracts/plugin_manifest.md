# C-30 Plugin Manifest — derived contract

**Owner:** `engineering.plugin`
**Producer:** third-party plugin
**Consumers:** plugin lifecycle, PDP
**Kind:** MANIFEST
**Version:** 1.0.0
**Compatibility:** PINNED

This document records the executable Phase 21 contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0117`, `ARK-REQ-0163`, `ARK-REQ-0164`,
`ARK-REQ-0165`, `ARK-REQ-0166`, `ARK-REQ-0167`), `CONTRACT_INVENTORY.md` row
C-30, MS §Import / Rescue / Research / Plugins, MS §Trust-Tiered Isolation,
and `SECURITY_ARCHITECTURE.md` §2-§3. It does not replace those authorities.

## 0. Scope of this revision

Four atomic packages, all under `backend/arkali/engineering/plugin/`:
the C-30 manifest domain contract composed with the pre-existing
`PluginLifecycle` state machine (`manifest.py`, `lifecycle_pipeline.py`);
a total, non-raising unmappable-action resolution added to the real PDP
(`control/policy/pdp.py::decide_or_deny_unmapped`); the TRUST-4 execution
gate, isolation and a per-execution human approval composed unmodified
(`trust4_execution_gate.py`); and Research, official-sources-first ordering
plus real PDP-governed network egress (`research.py`). `content_ref.py` is
a fan-in absorber, not a fifth package. **ARK-REQ-0167 (OPTIONAL, MCP-
compatible adapters) is not attempted** — `REQUIREMENT_REGISTER.md` states
plainly that optional entries never block release.

**Not implemented or claimed by this revision:** an HTTP/command surface
for installing or invoking a plugin; a real plugin execution runtime
(sandboxed process launch, MCP transport, or any other); a provider/
domain-pack registry declaring which concrete sources are "official" for a
given research task; persistence of any manifest, lifecycle instance, or
research result across a process restart; and any real network transport
(no `requests`/`httpx`/`urllib` call exists anywhere in this package). Each
is recorded as a deliberate boundary in §7, not a silent gap.

## 1. Compatibility semantics and persistence

The contract is **MANIFEST**: no table, no migration, no ORM record — the
same shape C-29's **INT** category established for content-addressed,
frozen domain objects with no DB persistence (`engineering.import.
contracts`). `PluginManifest`, `ResearchSource` and `ResearchResult` are
frozen, `extra="forbid"` value objects; a "changed" manifest is a new
object, never a mutation.

## 2. Manifest, permission and version governance (ARK-REQ-0164)

MS §Import: "Plugins/connectors/domain packs are manifest/permission/
version governed and must not crash core." `PluginManifest.version` is
validated against semver 2.0.0 at construction (`CONTRACT_INVENTORY.md` row
C-30: versioning is `semver`); a malformed version is refused before a
manifest can exist. `lifecycle_pipeline.admit_plugin` drives a real
`PluginLifecycle` instance (Phase 3, `STATE_MACHINES.md` §6, unmodified)
through `DISCOVERED → MANIFEST_VALIDATED → PERMISSIONS_DECLARED →
{APPROVED | stops}`. "Cannot crash core" begins here: an unmappable
declared permission is a named, recorded outcome
(`PluginLifecycleOutcome.unmappable_permissions`) — the machine stops at
`PERMISSIONS_DECLARED` — never a raised exception.

## 3. Permission mapping to the 14 canonical operation classes (ARK-REQ-0165)

`control.policy.operation_class.OperationClassVocabulary` remains the sole
store of the fourteen canonical classes — its own docstring already states
"Plugin manifests use this same vocabulary. There is no separate plugin
permission list." `engineering.plugin` declares no operation-class literal
of its own (proven by `test_plugin_lifecycle_pipeline.py::
TestNoSecondAuthorityIsIntroduced`); every declared permission is checked
against the live vocabulary at admission time, reusing the machine's own
pre-existing `permission_mapping_guard` on `PERMISSIONS_DECLARED →
APPROVED` rather than re-implementing the check.

## 4. Unmappable action is DENY (ARK-REQ-0166)

`SECURITY_ARCHITECTURE.md` §2: "Any action not mappable to a class is
DENY." The real PDP's existing `decide` already enforces this by raising
`UnknownOperationClass` — correct for a caller that can treat the exception
as the refusal, but a plugin action invocation cannot afford an uncaught
exception (that would itself be the ARK-REQ-0164 "crashes core" failure).
`PolicyDecisionPoint.decide_or_deny_unmapped` is a second, additive entry
point: an unmappable class resolves to a real, audited
`PolicyDecisionRecord` whose decision is read from `AUTHORITY_MAP.yaml`'s
`unmapped_action_resolution` (currently `DENY`), never hard-coded.
`decide`'s own raising behaviour, and every existing caller that depends on
it, is unchanged.

## 5. TRUST-4 human approval per execution (ARK-REQ-0117)

MS §Trust-Tiered Isolation: TRUST-3 requires approval "before first
execution" (once); TRUST-4 requires it "per execution" (every time).
`trust4_execution_gate.py` composes `control.isolation.IsolationAuthority.
resolve` and `control.policy.WorkflowApprovalGate` — both Protected Core,
both reused unmodified — the identical composition Phase 19's
`engineering.import.execution_gate` established for TRUST-3, rebound to
TRUST-4 and to a stricter binding. `WorkflowApprovalGate.
is_enforced_approval`'s existing staleness check (an approval bound to a
non-current revision hash never authorises) is reused against
`execution_binding_ref` — a fresh, content-addressed identity per attempt —
rather than a static tier-assignment ref, which is what turns "once" into
"every time": a previous execution's approval structurally cannot satisfy
the next one. Isolation is checked first so it cannot be skipped by an
approval-only path. On this real, unconfigured host TRUST-4 is honestly
`DENY` (`KERNEL_ISOLATION`/`DISPOSABILITY` `UNSUPPORTED`, proven by a real,
un-doubled backend probe — the same finding Phase 19 recorded for TRUST-3);
the ALLOW path is proven only with composition-root test doubles.

## 6. Research: official sources first, never mutates production (ARK-REQ-0163)

MS §Import: "Research uses official sources first and never directly
mutates production." `research.py` owns two structural guarantees, neither
a domain allowlist this module invents (which concrete domains are
"official" is governed data a future provider/domain-pack registry would
own — out of this phase's denominator):

1. **Official first.** `resolve_sources` stably partitions any declared
   source set into every `OFFICIAL` source (in given order) before any
   `COMMUNITY` source, proven over an exhaustive permutation sweep
   (`hypothesis` is `NOT_CONFIGURED` on this host per `BUILD_STATE.md`).
2. **Never mutates production.** `ResearchResult.mutation_applied` is
   `Literal[False]` — the same `StaticInspectionReport.executed` idiom
   Phase 19 established for a structural, type-level no-execution proof.
   `attempt_fetch` performs no real network call; it classifies the
   attempt as `NETWORK_EXTERNAL` and asks the real PDP whether it may
   proceed, through the new primitive-typed `PolicyDecisionPoint.
   decide_network_egress` (added because `policy_contract.PolicyRequest`
   sits at its fan-in ceiling of 15, so `engineering.plugin` cannot import
   it directly; a structural `Protocol` mirrors the new method instead).
   Proven against the real PDP: Local-Only denies research's own egress —
   the Verification and Delivery Contract names "research" explicitly among
   the paths whose Local-Only DENY evidence is required.

## 7. Deliberate boundary

This contract provides the C-30 plugin manifest, its semver-governed
version and its admission through the real `PluginLifecycle` machine; a
total, audited unmappable-action-is-DENY resolution in the real PDP; the
TRUST-4 execution gate bound per execution rather than per assignment; and
Research's official-sources-first ordering with real, PDP-governed network
egress. It does **not**: implement ARK-REQ-0167 (OPTIONAL, MCP-compatible
adapters — not attempted, does not block); execute, sandbox-launch, or
otherwise run any plugin's real code; perform any real network transport;
persist any manifest, lifecycle instance, or research result across a
process restart; expose an HTTP/command surface for plugin installation,
approval, or research invocation; declare which concrete domains are
"official" for any research task; modify `decide`'s existing raising
behaviour for any other caller; or add a 13th machine to
`STATE_MACHINES.md`.

## 8. Error taxonomy

| Code | Class | Meaning |
|---|---|---|
| `ARK-ERR-0147` | `PluginManifestVersionError` | A plugin manifest declared a version string that is not valid semver 2.0.0. |
| `ARK-ERR-0148` | `PluginExecutionRefusedError` | A TRUST-4 plugin execution attempt lacked satisfiable isolation, a genuine per-execution human approval, or was evaluated against the wrong trust tier. |
