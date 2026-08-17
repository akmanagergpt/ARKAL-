"""The Import/Rescue pipeline: composes existing authorities, owns none.

Owner: engineering.import.

A COMPOSITION CONVENIENCE, NOT A NEW AUTHORITY. Every step below delegates to
a primitive this package or an existing accepted authority already owns:
`StaticInspector` (this package, composing `engineering.codeintel`),
`assign_tier` (this package), `execution_gate.assert_execution_approved`
(this package, composing `control.isolation` and `control.policy`
unmodified), and `WorkspaceAuthority` (`engineering.candidate`, reused
unmodified). This module owns only the ORDER those calls happen in and the
`ImportProject` state-machine instance that makes that order structurally
enforced rather than a convention a caller could skip.

NO EXECUTION ENGINE. This is the descriptor-and-tier-assignment pipeline C-29
names — it drives `ImportProject` from `REGISTERED` to `WORKING_COPY_CREATED`
and materialises an isolated copy of the source. It does not run, transform,
repair, modernise or rebuild anything inside that copy; the three rescue
modes are recorded as a selection on the resulting descriptor
(ARK-REQ-0162), not executed as three different algorithms. Executing a
repair/modernisation/rebuild strategy against the working copy is Golden
Repair territory (Phase 30) and is not claimed here, the same boundary
Phase 14 drew around `RepairPipelinePath` and Phase 16 drew around
`product_generation.py`.

WHY ISOLATION BACKENDS AND THE APPROVAL GATE ARE CONSTRUCTOR ARGUMENTS, NOT
LIVE PROBES. The same composition-root shape Phase 9B established: a caller
supplies the real, host-probed backends (`control.isolation.backend_probe.
probe_all`) in production, or injected doubles in a test proving the ALLOW
path exists without claiming this host has TRUST-3 capability it does not
(`BUILD_STATE.md`: TRUST-2/3/4 UNSUPPORTED on this host, as of Phase 19).

WHY THE WORKSPACE AUTHORITY IS TYPED STRUCTURALLY, NOT IMPORTED CONCRETELY.
`engineering.candidate`'s own chain into `kernel.contracts`
(`engineering.candidate -> evidence.artifact -> control.policy ->
kernel.contracts`) was already measured at 4 of 4 — the orchestration-depth
ceiling — as of Phase 16 (`docs/build/BUILD_STATE.md`). A direct
`from arkali.engineering.candidate.workspace import ...` here would make
`engineering.import` a new predecessor of that already-at-ceiling chain,
extending it to 5. Phase 16 answered the identical shape of problem in
`product_generation.py` with a structural `Protocol` matching the exact
method the caller needs instead of the concrete class; `_WorkspaceTarget`
and `_WorkspaceHandle` below do the same for `WorkspaceAuthority.allocate`
and its `CandidateWorkspace` result. The real objects still satisfy these
shapes unmodified — nothing here is a double standing in for missing
capability, only a typing seam that keeps this module out of the measured
graph. No `engineering.import -> engineering.candidate` sibling edge is
declared, because no production import creates that edge; a caller
(composition root or test) constructs the real `WorkspaceAuthority` and
passes it in.

WHY THE INSPECTOR IS A CONSTRUCTOR ARGUMENT, NOT BUILT FROM A VOCABULARY
HERE. `max_contexts_touched_by_module` bounds this module's own external
dependencies at 3; composing `StaticInspector` (which itself carries the
`engineering.import -> engineering.codeintel` edge) here directly would push
this module to 4 (isolation, policy, candidate's Protocol notwithstanding,
codeintel). Accepting an already-constructed `StaticInspector` keeps that
one remaining edge in `static_inspection.py`, where it is declared.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Protocol

from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
)
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.engineering.project_import.contracts import ImportedProjectDescriptor
from arkali.engineering.project_import.execution_gate import assert_execution_approved
from arkali.engineering.project_import.import_project_state_machine import build as build_machine
from arkali.engineering.project_import.rescue_vocabulary import RescueModeVocabulary
from arkali.engineering.project_import.static_inspection import StaticInspector
from arkali.engineering.project_import.tier_authority import assign_tier

TRUST_3 = "TRUST-3"


class _WorkspaceHandle(Protocol):
    """Structural shape of an allocated workspace — matches
    `engineering.candidate.workspace.CandidateWorkspace`, unimported."""

    root: pathlib.Path
    snapshot: pathlib.Path


class _WorkspaceTarget(Protocol):
    """Structural shape of `engineering.candidate.workspace.WorkspaceAuthority`,
    unimported. See the module docstring for why."""

    def allocate(
        self,
        *,
        workspace_id: str,
        task_id: str,
        agent_id: str,
        stable_snapshot: pathlib.Path,
    ) -> _WorkspaceHandle: ...


@dataclass(frozen=True)
class ImportPipelineResult:
    """The C-29 descriptor plus the isolated workspace it was materialised
    into. `descriptor` is content-addressed and JSON-renderable;
    `workspace` is not part of the C-29 contract itself (`engineering.
    candidate` owns that identity) and is returned only so a caller can
    locate the working copy it just asked for."""

    descriptor: ImportedProjectDescriptor
    workspace: _WorkspaceHandle


class ImportPipeline:
    """Drives one project through `REGISTERED -> WORKING_COPY_CREATED`."""

    def __init__(
        self,
        *,
        inspector: StaticInspector,
        rescue_vocabulary: RescueModeVocabulary,
        isolation_authority: IsolationAuthority,
        isolation_backends: tuple[BackendDescriptor, ...],
        approval_gate: WorkflowApprovalGate,
        workspace_authority: _WorkspaceTarget,
    ) -> None:
        self._inspector = inspector
        self._rescue_vocabulary = rescue_vocabulary
        self._isolation_authority = isolation_authority
        self._isolation_backends = isolation_backends
        self._approval_gate = approval_gate
        self._workspace_authority = workspace_authority

    def run(
        self,
        *,
        project_id: str,
        source_root: pathlib.Path,
        rescue_mode: str,
        approval_decision: str,
        approval_actor: str,
    ) -> ImportPipelineResult:
        """Run the full C-29 journey, or raise. Never returns a partial result:
        every guard and every gate is real, so a caller either receives a
        genuinely `WORKING_COPY_CREATED` result or an exception naming
        exactly which condition was not met."""
        mode_id = self._rescue_vocabulary.require_mode(rescue_mode)

        machine = build_machine()
        instance = machine.start("REGISTERED")

        # REGISTERED -> STATICALLY_INSPECTED: the inspection is real work,
        # performed before the transition is recorded, not merely claimed.
        inspection = self._inspector.inspect(source_root)
        instance.apply("STATICALLY_INSPECTED", {})

        # STATICALLY_INSPECTED -> TIER_ASSIGNED: `tier_assignment_guard`
        # refuses unless the assigner is not "implementing_actor";
        # `assign_tier` can only ever name the fixed authority.
        tier_assignment = assign_tier(inspection)
        instance.apply(
            "TIER_ASSIGNED", {"tier_assigned_by": tier_assignment.assigned_by}
        )

        # TIER_ASSIGNED -> APPROVED_FOR_EXECUTION: `static_inspection_guard`
        # re-checks the inspection genuinely completed.
        instance.apply("APPROVED_FOR_EXECUTION", {"static_inspection_complete": True})

        # The TRUST-3 execution gate: isolation AND human approval, neither
        # substituting for the other. Raises RescueBoundaryViolationError on
        # any failure - there is no path that reaches the next line without
        # both being genuinely satisfied.
        resolution = self._isolation_authority.resolve(
            TRUST_3, self._isolation_backends
        )
        assert_execution_approved(
            isolation_resolution=resolution,
            approval_gate=self._approval_gate,
            decision=approval_decision,
            actor=approval_actor,
            approval_binding_hash=tier_assignment.assignment_ref,
            tier_assignment_ref=tier_assignment.assignment_ref,
        )

        # APPROVED_FOR_EXECUTION -> WORKING_COPY_CREATED:
        # `execution_approval_guard` only reads this fact; everything above
        # is what makes it trustworthy.
        instance.apply("WORKING_COPY_CREATED", {"execution_approved": True})

        # The working copy: an isolated, disjoint directory tree copied from
        # `source_root`. `source_root` itself is only ever read from here -
        # never opened for writing - so it cannot be overwritten by this
        # pipeline (ARK-REQ-0348 condition 6), and the copy remains
        # independently restorable to it (condition 3).
        workspace = self._workspace_authority.allocate(
            workspace_id=project_id,
            task_id="import",
            agent_id="engineering.import",
            stable_snapshot=source_root,
        )

        descriptor = ImportedProjectDescriptor(
            project_id=project_id,
            inspection=inspection,
            tier_assignment=tier_assignment,
            rescue_mode=mode_id,
            state=instance.state,
        )
        return ImportPipelineResult(descriptor=descriptor, workspace=workspace)


__all__ = ["ImportPipeline", "ImportPipelineResult"]
