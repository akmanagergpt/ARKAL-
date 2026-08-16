"""C-37 contract/schema tests (ARK-REQ-0382, 0387, 0388, 0389, 0390, 0391)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arkali.control.specification.blueprint_contracts import (
    CandidateRequirement,
    ProductGoal,
    RequirementBlueprint,
    RequirementCategory,
    UnresolvedQuestion,
    UnresolvedQuestionKind,
)
from arkali.control.specification.requirement_record import RequirementRecord


class TestProductGoalProvenance:
    def test_goal_id_is_a_content_address_of_the_verbatim_text(self) -> None:
        goal = ProductGoal(goal_text="Build a task tracker.")
        assert goal.goal_id.startswith("sha256:")

    def test_identical_text_yields_identical_goal_id(self) -> None:
        assert (
            ProductGoal(goal_text="Same text.").goal_id
            == ProductGoal(goal_text="Same text.").goal_id
        )

    def test_different_text_yields_different_goal_id(self) -> None:
        assert (
            ProductGoal(goal_text="Text A.").goal_id
            != ProductGoal(goal_text="Text B.").goal_id
        )

    def test_empty_goal_text_is_refused_by_the_model(self) -> None:
        with pytest.raises(ValidationError):
            ProductGoal(goal_text="")


class TestCandidateRequirementIsStructurallyDistinctFromArkReq:
    """ARK-REQ-0388: user requirements never carry canonical governance shape."""

    def test_candidate_requirement_carries_no_ark_req_id_field(self) -> None:
        assert "req_id" not in CandidateRequirement.model_fields
        assert "owning_phase" not in CandidateRequirement.model_fields

    def test_candidate_requirement_and_requirement_record_are_different_types(
        self,
    ) -> None:
        candidate = CandidateRequirement(
            index=0, statement="Users must log in.",
            category=RequirementCategory.SECURITY,
        )
        assert not isinstance(candidate, RequirementRecord)

    def test_requirement_id_is_content_addressed_and_stable(self) -> None:
        candidate = CandidateRequirement(
            index=2, statement="Same statement.", category=RequirementCategory.DATA,
        )
        other = CandidateRequirement(
            index=2, statement="Same statement.", category=RequirementCategory.DATA,
        )
        assert candidate.requirement_id == other.requirement_id
        assert candidate.requirement_id.startswith("sha256:")


class TestRequirementBlueprintRevisionIdentity:
    """ARK-REQ-0381, 0389: deterministic content-addressed revision lineage."""

    def _blueprint(self, *, revision: int = 1, previous: str | None = None) -> RequirementBlueprint:
        return RequirementBlueprint(
            goal=ProductGoal(goal_text="Build a task tracker."),
            requirements=(
                CandidateRequirement(
                    index=0, statement="Users must log in.",
                    category=RequirementCategory.SECURITY,
                ),
            ),
            revision=revision,
            previous_blueprint_id=previous,
        )

    def test_identical_blueprints_address_identically(self) -> None:
        assert self._blueprint().blueprint_id == self._blueprint().blueprint_id

    def test_a_later_revision_addresses_differently_even_with_the_same_content(
        self,
    ) -> None:
        first = self._blueprint(revision=1)
        second = self._blueprint(revision=2, previous=first.blueprint_id)
        assert first.blueprint_id != second.blueprint_id
        assert second.previous_blueprint_id == first.blueprint_id

    def test_first_revision_starts_at_one_with_no_predecessor(self) -> None:
        blueprint = self._blueprint()
        assert blueprint.revision == 1
        assert blueprint.previous_blueprint_id is None

    def test_a_fully_resolved_blueprint_has_no_unresolved_questions(self) -> None:
        assert self._blueprint().is_fully_resolved

    def test_a_blueprint_with_unresolved_questions_reports_unresolved(self) -> None:
        blueprint = RequirementBlueprint(
            goal=ProductGoal(goal_text="Build something."),
            requirements=(
                CandidateRequirement(
                    index=0, statement="It should be fast.",
                    category=RequirementCategory.UNCLASSIFIED,
                ),
            ),
            unresolved=(
                UnresolvedQuestion(
                    subject_index=0, kind=UnresolvedQuestionKind.UNDERSPECIFIED,
                    detail="vague qualifier with no number",
                ),
            ),
        )
        assert not blueprint.is_fully_resolved
        assert len(blueprint.unresolved) == 1


class TestRequirementBlueprintCarriesNoVerdictField:
    """ARK-REQ-0391: no acceptance verdict field exists on the blueprint at all."""

    def test_no_status_pass_fail_or_accepted_field_exists(self) -> None:
        forbidden = {"status", "verdict", "pass", "fail", "accepted", "rejected"}
        fields = set(RequirementBlueprint.model_fields)
        assert not (fields & forbidden), fields & forbidden

    def test_model_is_frozen_against_attribute_assignment(self) -> None:
        blueprint = RequirementBlueprint(
            goal=ProductGoal(goal_text="Build something."),
            requirements=(),
        )
        with pytest.raises(ValidationError):
            blueprint.revision = 99

    def test_model_forbids_extra_fields(self) -> None:
        with pytest.raises(ValidationError):
            RequirementBlueprint(
                goal=ProductGoal(goal_text="Build something."),
                requirements=(),
                extra_field="not allowed",
            )
