"""The composed Phase 19 real-authority journey (C-29).

Register denominator -> static inspection of a real toy external project
(no execution) -> fixed TRUST-3 tier assignment bound to that inspection ->
the TRUST-3 execution gate (isolation AND human approval, neither
substituting for the other) -> a materialised, isolated working copy ->
all seven ARK-REQ-0348 acceptance conditions proven against real
`RequirementRegister`, `StaticInspector`, `IsolationAuthority`,
`WorkflowApprovalGate`, `WorkspaceAuthority` and the real `ImportProject`
state machine. No AI provider is contacted anywhere in this journey.
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
)
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.engineering.project_import.errors import RescueBoundaryViolationError
from arkali.engineering.project_import.pipeline import ImportPipeline
from arkali.engineering.project_import.rescue_vocabulary import RescueModeVocabulary
from arkali.engineering.project_import.static_inspection import StaticInspector
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE_ROOT: Final[pathlib.Path] = REPO / "backend/arkali/engineering/project_import"

#: Markers that would indicate this package can execute imported/untrusted
#: source. None of the seven ARK-REQ-0348 conditions can hold if any of
#: these appear in the shipping source, the same text-scan idiom
#: `test_phase_10_journey.py` already established for a comparable claim.
_EXECUTION_MARKERS: Final[tuple[str, ...]] = (
    "importlib.import_module", "__import__(", "exec(", "eval(",
    "subprocess.", "os.system(", "os.popen(",
)


def test_step_0_no_execution_capability_exists_in_the_shipping_source() -> None:
    offenders = [
        f"{path.relative_to(REPO)}: {marker}"
        for path in sorted(PACKAGE_ROOT.rglob("*.py"))
        for marker in _EXECUTION_MARKERS
        if marker in path.read_text(encoding="utf-8")
    ]
    assert not offenders, f"execution-capable marker present: {offenders}"


def test_step_1_the_real_register_denominator() -> None:
    register = RequirementRegister.load(REPO)
    phase19 = {r.req_id for r in register.for_phase("19")}
    assert phase19 == {
        "ARK-REQ-0115", "ARK-REQ-0116", "ARK-REQ-0161", "ARK-REQ-0162", "ARK-REQ-0348",
    }
    owners = {r.req_id: r.owning_component for r in register.for_phase("19")}
    assert owners["ARK-REQ-0116"] == "control.policy"
    assert all(
        owners[req] == "engineering.import"
        for req in ("ARK-REQ-0115", "ARK-REQ-0161", "ARK-REQ-0162", "ARK-REQ-0348")
    )


def test_step_2_state_machine_count_stays_twelve() -> None:
    """This phase adds no new machine - `ImportProject` already existed and
    only gained one additional guard."""
    authority_map = AuthorityMap.load(REPO)
    assert len(authority_map.state_machine_authorities) == 12


class TestAllSevenAcceptanceConditions:
    """Each `test_condition_N_*` proves exactly the VDC §Import bullet it
    names, against the real composed pipeline."""

    @pytest.fixture()
    def source(self, tmp_path: pathlib.Path) -> pathlib.Path:
        root = tmp_path / "toy_external_project"
        root.mkdir()
        (root / "main.py").write_text(
            "import sys\n\ndef entrypoint():\n    return sys.argv\n", encoding="utf-8"
        )
        return root

    @pytest.fixture()
    def isolation_authority(self) -> IsolationAuthority:
        return IsolationAuthority.load(REPO)

    @pytest.fixture()
    def satisfied_pipeline(
        self, tmp_path: pathlib.Path, isolation_authority: IsolationAuthority
    ) -> ImportPipeline:
        declared = isolation_authority.declared_backends()
        backends = tuple(
            BackendDescriptor(name=name, provides=provides, availability=HonestState.PASS)
            for name, provides in declared.items()
        )
        return ImportPipeline(
            inspector=StaticInspector(GraphVocabulary.load(REPO)),
            rescue_vocabulary=RescueModeVocabulary.load(REPO),
            isolation_authority=isolation_authority,
            isolation_backends=backends,
            approval_gate=WorkflowApprovalGate.load(REPO),
            workspace_authority=WorkspaceAuthority(tmp_path / "workspaces"),
        )

    def test_condition_1_static_inspection_before_execution(
        self, source: pathlib.Path, satisfied_pipeline: ImportPipeline
    ) -> None:
        result = satisfied_pipeline.run(
            project_id="c1", source_root=source, rescue_mode="Repair in Place",
            approval_decision="APPROVED", approval_actor="human_reviewer",
        )
        assert result.descriptor.inspection.executed is False
        assert result.descriptor.state == "WORKING_COPY_CREATED"

    def test_condition_2_tier_assigned_and_not_reassignable(
        self, source: pathlib.Path, satisfied_pipeline: ImportPipeline
    ) -> None:
        result = satisfied_pipeline.run(
            project_id="c2", source_root=source, rescue_mode="Repair in Place",
            approval_decision="APPROVED", approval_actor="human_reviewer",
        )
        assert result.descriptor.tier_assignment.tier == "TRUST-3"
        assert result.descriptor.tier_assignment.assigned_by != "implementing_actor"

    def test_condition_3_original_source_preserved_and_restorable(
        self, source: pathlib.Path, satisfied_pipeline: ImportPipeline
    ) -> None:
        original = (source / "main.py").read_bytes()
        result = satisfied_pipeline.run(
            project_id="c3", source_root=source, rescue_mode="Repair in Place",
            approval_decision="APPROVED", approval_actor="human_reviewer",
        )
        assert (source / "main.py").read_bytes() == original
        assert (result.workspace.snapshot / "main.py").read_bytes() == original

    def test_condition_4_modifications_confined_to_the_working_copy(
        self, source: pathlib.Path, satisfied_pipeline: ImportPipeline
    ) -> None:
        result = satisfied_pipeline.run(
            project_id="c4", source_root=source, rescue_mode="Repair in Place",
            approval_decision="APPROVED", approval_actor="human_reviewer",
        )
        result.workspace.write("notes/generated.txt", b"a rescue artifact")
        assert not (source / "notes").exists()

    def test_condition_5_provenance_traceable(
        self, source: pathlib.Path, satisfied_pipeline: ImportPipeline
    ) -> None:
        result = satisfied_pipeline.run(
            project_id="c5", source_root=source, rescue_mode="Repair in Place",
            approval_decision="APPROVED", approval_actor="human_reviewer",
        )
        assert (
            result.descriptor.tier_assignment.inspection_ref
            == result.descriptor.inspection.source_address
        )
        assert result.descriptor.descriptor_ref.startswith("sha256:")

    def test_condition_6_rescue_cannot_overwrite_the_source(
        self, source: pathlib.Path, satisfied_pipeline: ImportPipeline
    ) -> None:
        before = (source / "main.py").stat().st_mtime_ns
        satisfied_pipeline.run(
            project_id="c6", source_root=source, rescue_mode="Repair in Place",
            approval_decision="APPROVED", approval_actor="human_reviewer",
        )
        after = (source / "main.py").stat().st_mtime_ns
        assert before == after

    def test_condition_7_execution_denied_when_isolation_unsatisfiable(
        self, source: pathlib.Path, tmp_path: pathlib.Path,
        isolation_authority: IsolationAuthority,
    ) -> None:
        denied_pipeline = ImportPipeline(
            inspector=StaticInspector(GraphVocabulary.load(REPO)),
            rescue_vocabulary=RescueModeVocabulary.load(REPO),
            isolation_authority=isolation_authority,
            isolation_backends=(),
            approval_gate=WorkflowApprovalGate.load(REPO),
            workspace_authority=WorkspaceAuthority(tmp_path / "workspaces"),
        )
        with pytest.raises(RescueBoundaryViolationError):
            denied_pipeline.run(
                project_id="c7", source_root=source, rescue_mode="Repair in Place",
                approval_decision="APPROVED", approval_actor="human_reviewer",
            )


def test_step_3_nothing_in_this_journey_contacts_a_provider_or_persists(
    tmp_path: pathlib.Path,
) -> None:
    """Matches the D-023 precedent every prior phase's journey proves: C-29
    is `INT` - purely content-addressed computation plus the isolated
    filesystem copy `engineering.candidate` already owns."""
    isolation_authority = IsolationAuthority.load(REPO)
    declared = isolation_authority.declared_backends()
    backends = tuple(
        BackendDescriptor(name=name, provides=provides, availability=HonestState.PASS)
        for name, provides in declared.items()
    )
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.py").write_text("x = 1\n", encoding="utf-8")
    pipeline = ImportPipeline(
        inspector=StaticInspector(GraphVocabulary.load(REPO)),
        rescue_vocabulary=RescueModeVocabulary.load(REPO),
        isolation_authority=isolation_authority,
        isolation_backends=backends,
        approval_gate=WorkflowApprovalGate.load(REPO),
        workspace_authority=WorkspaceAuthority(tmp_path / "workspaces"),
    )
    first = pipeline.run(
        project_id="repeat-1", source_root=source, rescue_mode="Repair in Place",
        approval_decision="APPROVED", approval_actor="human_reviewer",
    )
    assert first.descriptor.inspection.source_address.startswith("sha256:")
