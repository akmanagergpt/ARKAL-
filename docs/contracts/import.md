# C-29 Imported Project Descriptor + Tier Assignment — derived contract

**Owner:** `engineering.import`
**Producer:** import pipeline
**Consumers:** `isolation`, `candidate`
**Kind:** INT
**Version:** 1.0.0
**Compatibility:** STRICT

This document records the executable Phase 19 contract derived from
`REQUIREMENT_REGISTER.md` (`ARK-REQ-0115`, `ARK-REQ-0116`, `ARK-REQ-0161`,
`ARK-REQ-0162`, `ARK-REQ-0348`), `CONTRACT_INVENTORY.md` row C-29, MS
§Trust-Tiered Isolation, MS §Import / Rescue / Research / Plugins, VDC
§Import / Reverse Engineering / Rescue, and `STATE_MACHINES.md` §12 Import
Project. It does not replace those authorities.

## 0. Scope of this revision

One atomic package under `backend/arkali/engineering/project_import/`
(physical root; ERR-001), composing existing authorities rather than
duplicating any of them: `errors.py`, `rescue_vocabulary.py`,
`contracts.py`, `static_inspection.py`, `tier_authority.py`,
`execution_gate.py`, `pipeline.py`, and one additive guard on the
pre-existing `import_project_state_machine.py`. **Not implemented or
claimed by this revision:** a repair/modernisation/rebuild execution
engine for any of the three rescue modes, an HTTP/command surface, a Research
capability (MS names Import/Rescue/Research/Plugins in one section; this
contract is Import/Rescue only, matching the Phase 19 register denominator),
and TRUST-4 (internet-sourced executable content) — the register's Phase 19
denominator names only TRUST-3.

## 1. Compatibility semantics and persistence

**INT**, matching the C-11/C-13/C-23/C-28 precedent: no table, no
migration, no ORM record. `StaticInspectionReport`, `TierAssignment` and
`ImportedProjectDescriptor` are frozen, `extra="forbid"` pydantic value
objects, content-addressed via `kernel.contracts.content_address` — the
same primitive C-14, C-23, C-24 and C-28 already use. Durable,
cross-process storage of an import record is not claimed here; a future
phase that needs it composes `kernel.persistence` itself.

## 2. Static inspection before execution (ARK-REQ-0115, ARK-REQ-0161)

MS §Trust-Tiered Isolation: "TRUST-3 ... static inspection before any
execution." MS §Import: "External projects are statically inspected before
execution." `StaticInspector.inspect(root)` reuses
`engineering.codeintel.PythonGraphBuilder` unmodified (a declared sibling
edge, `engineering.import -> engineering.codeintel`, added with written
rationale in `AUTHORITY_MAP.yaml`) — AST-only, never importing or executing
the target. `source_address` is a content address over the sorted
`(relative_path, sha256(bytes))` listing of every file under the root, so
two inspections of byte-identical trees address identically regardless of
filesystem enumeration order. `StaticInspectionReport.executed` is
`Literal[False]` — a type-level guarantee, not a runtime flag a caller could
set — proven by a landmine fixture whose only defect is a side effect at
import time, never triggered by inspection (`sec` evidence), and by
determinism controls over inspections of identical and differing content
(`prop` evidence).

## 3. TRUST tier assignment, fixed and non-reassignable (ARK-REQ-0161)

MS §Trust-Tiered Isolation names `TRUST-3` for "imported/untrusted
projects" unconditionally. `tier_authority.assign_tier(inspection)` takes
no tier parameter — the entire proof that a tier "cannot be reassigned by
an implementing actor" (`STATE_MACHINES.md` §12) is that no code path in
this package can produce any other value. `TierAssignment.tier` and
`.assigned_by` are each a single-member `Literal` type; constructing either
field with any other value is a `pydantic.ValidationError`, not a check
that could be skipped. `TierAssignment.inspection_ref` binds the assignment
to the exact `StaticInspectionReport.source_address` it was made against,
and `ImportedProjectDescriptor` refuses construction if the two do not
match — an assignment cannot silently carry over to a different snapshot.

## 4. Three rescue modes (ARK-REQ-0162)

MS §Import: "Rescue modes: Repair in Place, Controlled Modernization, Clean
Rebuild with Migration." `RescueModeVocabulary` parses this sentence at
call time from the live Master Specification — the same
specification-referenced-set idiom `engineering.codeintel.GraphVocabulary`
established for the graph/view sets — never a hard-coded tuple. The number
three is asserted nowhere in shipping source; a behavioural control feeds
the parser declarations of different sizes and the reported set follows
the document each time. `ImportPipeline.run(rescue_mode=...)` resolves the
caller's spelling to the canonical identifier via `require_mode` and
records it on the resulting descriptor. **Executing** a rescue strategy
(repairing, modernising or rebuilding the working copy's content) is not
claimed here — that is Golden Repair territory (Phase 30), the same
boundary Phase 14 drew around `RepairPipelinePath` and Phase 16 drew around
`product_generation.py`. This package proves all three modes are
selectable and each genuinely reaches `WORKING_COPY_CREATED` (`integ`
evidence, `test_import_pipeline.py::TestAllThreeRescueModesAreSupported`).

## 5. TRUST-3 execution gate: isolation AND human approval (ARK-REQ-0116)

MS §Trust-Tiered Isolation: TRUST-3 requires the TRUST-2 property set plus
`KERNEL_ISOLATION`, and human approval "yes, before first execution." VDC
condition 7: "execution is DENY where the tier's required security
properties cannot be established." `execution_gate.
assert_execution_approved` composes two existing Protected Core authorities
unmodified — `control.isolation.IsolationAuthority.resolve` and
`control.policy.workflow_approval.WorkflowApprovalGate` — and raises unless
**both** hold: `IsolationResolution.execution_decision == "ALLOW"` (checked
first, so it can never be bypassed by an approval-only path), **and**
`WorkflowApprovalGate.is_enforced_approval` returns `True` for the supplied
decision/actor/hash triple.

**Why `WorkflowApprovalGate` is reused rather than a new
`control.policy` module built.** Despite its name, the mechanism it
implements is domain-agnostic: refuse an automated actor (the governed
`stable_mutation.prohibited_actors` list) recording its own approval, and
refuse an approval bound to a revision hash that is no longer current.
Nothing in either rule is specific to a workflow graph. This module binds
the "revision" it compares to `TierAssignment.assignment_ref` instead of a
workflow-graph revision — the identical shape survives the rename, and
building a second approval-record contract would be exactly the
duplicated-authority defect this build's governance repeatedly refuses.
ARK-REQ-0116's owner, `control.policy`, is therefore satisfied by
composing its own already-accepted authority; **no file under
`backend/arkali/control/` is modified by this phase**, so Phase 19 does not
carry the Protected Core stronger verification profile.

**On this real, unconfigured host, TRUST-3 is honestly DENY.**
`BUILD_STATE.md`: "TRUST-2/3/4 UNSUPPORTED on this host
(`NET_EGRESS_CONTROL`, `KERNEL_ISOLATION` unavailable)." A real,
un-doubled probe (`control.isolation.backend_probe.probe_all`) against
this host is asserted to DENY (`test_import_execution_gate.py::
test_this_real_host_denies_trust_3_honestly`); the ALLOW path is proven
separately with composition-root test doubles claiming `PASS` for every
declared backend, the identical shape Phase 9B used to prove its
activation mechanism "end to end" without claiming real production
capability. No capability is declared configured on this host by this
phase.

## 6. Source preservation, working-copy confinement, and provenance (ARK-REQ-0348 conditions 3, 4, 5, 6)

`ImportPipeline.run` reuses `engineering.candidate.workspace.
WorkspaceAuthority.allocate` to materialise the working copy — composed
through a structural `Protocol` (`_WorkspaceTarget`/`_WorkspaceHandle` in
`pipeline.py`), **not** a direct import of the concrete class. `
engineering.candidate`'s own chain into `kernel.contracts`
(`engineering.candidate -> evidence.artifact -> control.policy ->
kernel.contracts`) was already measured at 4 of 4 — the orchestration-depth
ceiling — as of Phase 16; a direct import here would make
`engineering.import` a new predecessor of that already-at-ceiling chain,
extending it to 5. The Protocol keeps this package out of the measured
graph while the real object still satisfies the shape unmodified — the
identical answer Phase 16's `product_generation.py` gave the same shape of
problem. **No `engineering.import -> engineering.candidate` sibling edge is
declared**, because no production import creates that edge.

`WorkspaceAuthority.allocate` only ever reads `source_root` (via
`shutil.copytree`) and never opens it for writing, so the original project
cannot be overwritten by this pipeline (condition 6) and the copy at
`workspace.snapshot` remains byte-identical and independently restorable to
it (condition 3) — proven directly, not merely asserted, by hashing the
source tree before and after a run. Any further write
(`CandidateWorkspace.write`) is confined to `workspace.root`, disjoint from
`source_root` (condition 4). `TierAssignment.inspection_ref ==
StaticInspectionReport.source_address` is the traceable provenance link
from the original artifact (the inspected source) to the tier-assigned,
approved candidate (condition 5); `ImportedProjectDescriptor.descriptor_ref`
content-addresses the whole bound record.

## 7. The `ImportProject` state machine (`STATE_MACHINES.md` §12)

The machine (`REGISTERED -> STATICALLY_INSPECTED -> TIER_ASSIGNED ->
APPROVED_FOR_EXECUTION -> WORKING_COPY_CREATED`; any -> `REJECTED`)
pre-dates Phase 19 and already carried two guards
(`tier_assignment_guard`, `static_inspection_guard`) proving two of the
seven VDC conditions structurally. Phase 19 adds exactly one more:
`execution_approval_guard` on `APPROVED_FOR_EXECUTION ->
WORKING_COPY_CREATED`, reading only a boolean context fact —
`execution_approved` — the identical shape the two pre-existing guards
already use. The guard itself never consults `control.policy` or
`control.isolation` (that would be a second, ungoverned path to the same
decision); `execution_gate.assert_execution_approved` is what may set that
fact true, and it raises before any other path can. `STATE_MACHINES.md`'s
reconciled count stays 12 — no new machine is added, only a third guard on
an existing one.

## 8. Error taxonomy

| Code | Class | Meaning |
|---|---|---|
| `ARK-ERR-0143` | `UnverifiedStaticInspectionError` | Static inspection was attempted against a root that does not exist, or a tier/approval step ran without a genuinely completed inspection. |
| `ARK-ERR-0144` | `TierReassignmentError` | A tier assignment, static-inspection-report address, or their binding is malformed or mismatched. |
| `ARK-ERR-0145` | `RescueBoundaryViolationError` | TRUST-3 execution was attempted while isolation is unsatisfiable, or without a genuinely enforced human approval. |
| `ARK-ERR-0146` | `UnknownRescueMode` | A caller named a rescue mode the live Master Specification does not declare. |

## 9. Deliberate boundary

This contract provides the C-29 imported-project descriptor, its fixed and
non-reassignable TRUST-3 tier assignment, static inspection with a
structural no-execution proof, the three-rescue-mode selection, the
composed TRUST-3 execution gate (isolation and human approval, real on
this host, doubled only for the ALLOW-path proof), and a genuinely
isolated, provenance-traceable working copy. It does **not**: execute,
repair, modernise or rebuild anything inside the working copy; persist any
record across a process restart; expose an HTTP/command surface; implement
Research (the other half of MS §Import / Rescue / Research / Plugins, out
of this phase's register denominator); implement TRUST-4 (internet-sourced
executable content); modify any file under `backend/arkali/control/`
(ARK-REQ-0116 is satisfied by composing `WorkflowApprovalGate` unmodified);
or add an eleventh sibling edge, a new state machine, or a fourth entry to
`max_orchestration_depth`'s measured chain.
