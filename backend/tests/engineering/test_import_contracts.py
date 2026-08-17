"""C-29 contract: descriptor, tier assignment, rescue-mode vocabulary.

Phase 19 Package 1. ARK-REQ-0161 ("external projects statically inspected...
assigned its correct TRUST tier and cannot be reassigned by an implementing
actor") and ARK-REQ-0162 ("three rescue modes supported").
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest
from pydantic import ValidationError

from arkali.engineering.project_import.contracts import (
    FIXED_ASSIGNER,
    FIXED_TIER,
    ImportedProjectDescriptor,
    StaticInspectionReport,
    TierAssignment,
)
from arkali.engineering.project_import.errors import TierReassignmentError
from arkali.engineering.project_import.rescue_vocabulary import (
    RescueModeVocabulary,
    UnknownRescueMode,
)
from arkali.kernel.contracts.content_address import address_of

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


def _report(source_address: str = "sha256:" + "a" * 64) -> StaticInspectionReport:
    return StaticInspectionReport(
        source_address=source_address,
        graph_kinds=("symbol", "import", "dependency"),
        graph_addresses=(("symbol", "sha256:" + "b" * 64),),
        file_count=1,
    )


class TestStaticInspectionReportIsStructurallyHonest:
    def test_executed_defaults_false(self) -> None:
        assert _report().executed is False

    def test_executed_cannot_be_constructed_true(self) -> None:
        """`Literal[False]` — not a runtime check that could be bypassed."""
        with pytest.raises(ValidationError):
            StaticInspectionReport(
                source_address="sha256:" + "a" * 64,
                graph_kinds=(),
                graph_addresses=(),
                file_count=0,
                executed=True,  # type: ignore[arg-type]
            )

    def test_malformed_source_address_refused(self) -> None:
        with pytest.raises(TierReassignmentError):
            StaticInspectionReport(
                source_address="not-a-canonical-address",
                graph_kinds=(),
                graph_addresses=(),
                file_count=0,
            )


class TestTierAssignmentIsFixedByType:
    def test_default_tier_is_trust_3(self) -> None:
        assignment = TierAssignment(inspection_ref="sha256:" + "a" * 64)
        assert assignment.tier == FIXED_TIER == "TRUST-3"
        assert assignment.assigned_by == FIXED_ASSIGNER

    def test_a_different_tier_cannot_be_constructed(self) -> None:
        """The whole ARK-REQ-0161 §12 guarantee: not a default, the only
        value the type admits."""
        with pytest.raises(ValidationError):
            TierAssignment(
                tier="TRUST-4",  # type: ignore[arg-type]
                inspection_ref="sha256:" + "a" * 64,
            )

    def test_implementing_actor_cannot_become_the_assigner(self) -> None:
        with pytest.raises(ValidationError):
            TierAssignment(
                assigned_by="implementing_actor",  # type: ignore[arg-type]
                inspection_ref="sha256:" + "a" * 64,
            )

    def test_assignment_ref_is_a_canonical_address(self) -> None:
        assignment = TierAssignment(inspection_ref="sha256:" + "a" * 64)
        assert assignment.assignment_ref.startswith("sha256:")
        assert assignment.assignment_ref == address_of(assignment.rendering())


class TestImportedProjectDescriptorBindsTierToItsInspection:
    def test_construction_succeeds_when_bound(self) -> None:
        report = _report()
        assignment = TierAssignment(inspection_ref=report.source_address)
        descriptor = ImportedProjectDescriptor(
            project_id="proj-1",
            inspection=report,
            tier_assignment=assignment,
            rescue_mode="repair_in_place",
            state="TIER_ASSIGNED",
        )
        assert descriptor.descriptor_ref.startswith("sha256:")

    def test_a_tier_assigned_against_a_different_inspection_is_refused(self) -> None:
        report = _report()
        stale_assignment = TierAssignment(inspection_ref="sha256:" + "c" * 64)
        with pytest.raises(TierReassignmentError):
            ImportedProjectDescriptor(
                project_id="proj-1",
                inspection=report,
                tier_assignment=stale_assignment,
                rescue_mode="repair_in_place",
                state="TIER_ASSIGNED",
            )

    def test_advanced_only_changes_state(self) -> None:
        report = _report()
        assignment = TierAssignment(inspection_ref=report.source_address)
        descriptor = ImportedProjectDescriptor(
            project_id="proj-1",
            inspection=report,
            tier_assignment=assignment,
            rescue_mode="repair_in_place",
            state="TIER_ASSIGNED",
        )
        advanced = descriptor.advanced(state="APPROVED_FOR_EXECUTION")
        assert advanced.state == "APPROVED_FOR_EXECUTION"
        assert advanced.inspection == descriptor.inspection
        assert advanced.tier_assignment == descriptor.tier_assignment


class TestRescueModeVocabularyIsParsedNotHardcoded:
    def test_the_live_document_declares_exactly_three_modes(self) -> None:
        vocabulary = RescueModeVocabulary.load(REPO)
        assert len(vocabulary.modes()) == 3

    def test_modes_are_the_canonical_three(self) -> None:
        vocabulary = RescueModeVocabulary.load(REPO)
        assert vocabulary.mode_ids() == (
            "repair_in_place",
            "controlled_modernization",
            "clean_rebuild_with_migration",
        )

    def test_require_mode_resolves_a_declared_mode(self) -> None:
        vocabulary = RescueModeVocabulary.load(REPO)
        assert vocabulary.require_mode("Repair in Place") == "repair_in_place"

    def test_require_mode_refuses_an_undeclared_mode(self) -> None:
        vocabulary = RescueModeVocabulary.load(REPO)
        with pytest.raises(UnknownRescueMode):
            vocabulary.require_mode("Full Rewrite From Scratch")

    def test_the_count_follows_the_document_behaviourally(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Fed a differently-sized declaration, the count follows it - proving
        the vocabulary is parsed, not a copy of today's three-item list."""
        doc = tmp_path / "docs" / "ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"
        doc.parent.mkdir(parents=True)
        doc.write_text(
            "## Import / Rescue / Research / Plugins\n"
            "Rescue modes: Alpha Mode, Beta Mode, Gamma Mode, Delta Mode.\n"
            "## Next Section\n"
            "Rescue modes: Ignored, Because, Bounded.\n",
            encoding="utf-8",
        )
        vocabulary = RescueModeVocabulary.load(tmp_path)
        assert vocabulary.mode_ids() == (
            "alpha_mode",
            "beta_mode",
            "gamma_mode",
            "delta_mode",
        )

    def test_an_absent_rescue_clause_is_refused(self, tmp_path: pathlib.Path) -> None:
        doc = tmp_path / "docs" / "ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"
        doc.parent.mkdir(parents=True)
        doc.write_text(
            "## Import / Rescue / Research / Plugins\nNothing relevant here.\n",
            encoding="utf-8",
        )
        with pytest.raises(Exception):
            RescueModeVocabulary.load(tmp_path)
