"""The composed C-29 pipeline: REGISTERED -> WORKING_COPY_CREATED.

Phase 19 Package 4. ARK-REQ-0162 ("three rescue modes supported", evidence
integ) and ARK-REQ-0348 conditions 3, 4, 5, 6 (source preserved and
independently restorable; modifications confined to the working copy;
provenance traceable; the source project is never overwritten).
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
)
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.engineering.candidate.errors import WorkspaceIsolationError
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.engineering.project_import.pipeline import ImportPipeline
from arkali.engineering.project_import.rescue_vocabulary import RescueModeVocabulary
from arkali.engineering.project_import.static_inspection import StaticInspector
from arkali.kernel.contracts.results import HonestState
from arkali.kernel.contracts.state_machine_errors import GuardRejected

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


def _write_project(root: pathlib.Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("import os\n\ndef main():\n    return os.getcwd()\n", encoding="utf-8")
    (root / "README.md").write_text("a toy external project\n", encoding="utf-8")


def _satisfied_backends(authority: IsolationAuthority) -> tuple[BackendDescriptor, ...]:
    declared = authority.declared_backends()
    return tuple(
        BackendDescriptor(name=name, provides=provides, availability=HonestState.PASS)
        for name, provides in declared.items()
    )


@pytest.fixture()
def pipeline_with_satisfied_isolation(tmp_path: pathlib.Path) -> ImportPipeline:
    isolation_authority = IsolationAuthority.load(REPO)
    return ImportPipeline(
        inspector=StaticInspector(GraphVocabulary.load(REPO)),
        rescue_vocabulary=RescueModeVocabulary.load(REPO),
        isolation_authority=isolation_authority,
        isolation_backends=_satisfied_backends(isolation_authority),
        approval_gate=WorkflowApprovalGate.load(REPO),
        workspace_authority=WorkspaceAuthority(tmp_path / "workspaces"),
    )


@pytest.fixture()
def pipeline_with_denied_isolation(tmp_path: pathlib.Path) -> ImportPipeline:
    isolation_authority = IsolationAuthority.load(REPO)
    return ImportPipeline(
        inspector=StaticInspector(GraphVocabulary.load(REPO)),
        rescue_vocabulary=RescueModeVocabulary.load(REPO),
        isolation_authority=isolation_authority,
        isolation_backends=(),
        approval_gate=WorkflowApprovalGate.load(REPO),
        workspace_authority=WorkspaceAuthority(tmp_path / "workspaces"),
    )


class TestAllThreeRescueModesAreSupported:
    @pytest.mark.parametrize(
        "mode",
        ["Repair in Place", "Controlled Modernization", "Clean Rebuild with Migration"],
    )
    def test_each_canonical_mode_reaches_working_copy_created(
        self, tmp_path: pathlib.Path, pipeline_with_satisfied_isolation: ImportPipeline, mode: str
    ) -> None:
        source = tmp_path / "source" / mode.replace(" ", "_")
        _write_project(source)

        result = pipeline_with_satisfied_isolation.run(
            project_id=f"proj-{mode.replace(' ', '-').lower()}",
            source_root=source,
            rescue_mode=mode,
            approval_decision="APPROVED",
            approval_actor="human_reviewer",
        )

        assert result.descriptor.state == "WORKING_COPY_CREATED"
        assert result.descriptor.rescue_mode in (
            "repair_in_place", "controlled_modernization", "clean_rebuild_with_migration",
        )
        assert (result.workspace.snapshot / "app.py").is_file()


class TestSourcePreservationAndProvenance:
    def test_the_original_source_directory_is_never_written_to(
        self, tmp_path: pathlib.Path, pipeline_with_satisfied_isolation: ImportPipeline
    ) -> None:
        source = tmp_path / "source"
        _write_project(source)
        before = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}

        pipeline_with_satisfied_isolation.run(
            project_id="proj-preserve",
            source_root=source,
            rescue_mode="Repair in Place",
            approval_decision="APPROVED",
            approval_actor="human_reviewer",
        )

        after = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
        assert before == after, "rescue must never overwrite the source project (condition 6)"

    def test_the_working_copy_is_a_disjoint_directory_from_the_source(
        self, tmp_path: pathlib.Path, pipeline_with_satisfied_isolation: ImportPipeline
    ) -> None:
        source = tmp_path / "source"
        _write_project(source)
        result = pipeline_with_satisfied_isolation.run(
            project_id="proj-disjoint",
            source_root=source,
            rescue_mode="Repair in Place",
            approval_decision="APPROVED",
            approval_actor="human_reviewer",
        )
        assert not result.workspace.root.is_relative_to(source)
        assert not source.is_relative_to(result.workspace.root)

    def test_provenance_binds_the_working_copy_to_the_exact_inspection(
        self, tmp_path: pathlib.Path, pipeline_with_satisfied_isolation: ImportPipeline
    ) -> None:
        source = tmp_path / "source"
        _write_project(source)
        result = pipeline_with_satisfied_isolation.run(
            project_id="proj-provenance",
            source_root=source,
            rescue_mode="Repair in Place",
            approval_decision="APPROVED",
            approval_actor="human_reviewer",
        )
        assert (
            result.descriptor.tier_assignment.inspection_ref
            == result.descriptor.inspection.source_address
        )

    def test_a_second_import_of_the_same_workspace_id_is_refused(
        self, tmp_path: pathlib.Path, pipeline_with_satisfied_isolation: ImportPipeline
    ) -> None:
        source = tmp_path / "source"
        _write_project(source)
        pipeline_with_satisfied_isolation.run(
            project_id="proj-dup",
            source_root=source,
            rescue_mode="Repair in Place",
            approval_decision="APPROVED",
            approval_actor="human_reviewer",
        )
        with pytest.raises(WorkspaceIsolationError):
            pipeline_with_satisfied_isolation.run(
                project_id="proj-dup",
                source_root=source,
                rescue_mode="Repair in Place",
                approval_decision="APPROVED",
                approval_actor="human_reviewer",
            )


class TestUnsatisfiableIsolationRefusesTheWorkingCopy:
    def test_no_working_copy_is_ever_materialised_without_isolation(
        self, tmp_path: pathlib.Path, pipeline_with_denied_isolation: ImportPipeline
    ) -> None:
        source = tmp_path / "source"
        _write_project(source)
        with pytest.raises(Exception):
            pipeline_with_denied_isolation.run(
                project_id="proj-denied",
                source_root=source,
                rescue_mode="Repair in Place",
                approval_decision="APPROVED",
                approval_actor="human_reviewer",
            )
        assert not (tmp_path / "workspaces" / "proj-denied").exists()


class TestUnapprovedExecutionCannotReachAWorkingCopy:
    def test_the_state_machine_guard_itself_refuses_an_unset_fact(self) -> None:
        """Even bypassing the pipeline entirely: applying the transition
        directly, without the fact the gate alone may set, is refused by the
        state machine's own guard - not merely by the pipeline's call order."""
        from arkali.engineering.project_import.import_project_state_machine import build

        machine = build()
        instance = machine.start("REGISTERED")
        instance.apply("STATICALLY_INSPECTED", {})
        instance.apply("TIER_ASSIGNED", {"tier_assigned_by": "engineering.import.tier_authority"})
        instance.apply("APPROVED_FOR_EXECUTION", {"static_inspection_complete": True})
        with pytest.raises(GuardRejected):
            instance.apply("WORKING_COPY_CREATED", {})
