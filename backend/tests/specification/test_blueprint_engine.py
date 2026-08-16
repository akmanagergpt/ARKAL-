"""Deterministic derivation + ambiguity/contradiction negative controls
(ARK-REQ-0381, 0383, 0384, 0385, 0386)."""

from __future__ import annotations

import pathlib

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.blueprint_contracts import (
    RequirementCategory,
    UnresolvedQuestionKind,
)
from arkali.control.specification.blueprint_engine import (
    classify,
    decompose,
    derive_acceptance_criteria,
    derive_blueprint,
    map_architecture,
)
from arkali.control.specification.blueprint_errors import MalformedProductGoalError

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def authority_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


class TestDecomposition:
    def test_sentence_boundaries_split_a_prose_goal(self) -> None:
        statements = decompose("Users must log in. The system must be fast.")
        assert statements == ("Users must log in.", "The system must be fast.")

    def test_enumeration_markers_take_precedence_over_sentences(self) -> None:
        goal = "- Users must log in.\n- The system must scale.\n- Data must persist."
        statements = decompose(goal)
        assert len(statements) == 3
        assert statements[0] == "Users must log in."

    def test_decomposition_is_deterministic(self) -> None:
        goal = "Users must log in. The system must be fast."
        assert decompose(goal) == decompose(goal)


class TestClassification:
    @pytest.mark.parametrize(
        ("statement", "expected"),
        [
            ("Users must authenticate securely.", RequirementCategory.SECURITY),
            ("Orders must persist in the database.", RequirementCategory.DATA),
            ("The API must expose an external endpoint.", RequirementCategory.INTEGRATION),
            ("The dashboard must show a status page.", RequirementCategory.UI),
            ("Backups must be monitored during deployment.", RequirementCategory.OPERATIONS),
            ("The system must have high availability.", RequirementCategory.NON_FUNCTIONAL),
            ("Widgets must exist.", RequirementCategory.UNCLASSIFIED),
        ],
    )
    def test_keyword_classification(self, statement: str, expected: RequirementCategory) -> None:
        assert classify(statement) is expected

    def test_classification_is_deterministic(self) -> None:
        statement = "Users must authenticate securely."
        assert classify(statement) is classify(statement)


class TestAcceptanceCriteriaDerivation:
    def test_a_quantified_modal_statement_yields_a_criterion(self) -> None:
        criteria = derive_acceptance_criteria("The system must respond within 200ms.")
        assert criteria == ("within 200ms",)

    def test_a_statement_with_no_modal_yields_nothing(self) -> None:
        assert derive_acceptance_criteria("The system is fast.") == ()

    def test_a_modal_statement_with_no_number_yields_nothing(self) -> None:
        assert derive_acceptance_criteria("The system must be fast.") == ()


class TestArchitectureMapping:
    def test_a_security_statement_resolves_to_a_live_concern(
        self, authority_map: AuthorityMap
    ) -> None:
        concern = map_architecture(
            "Users must authenticate securely.", RequirementCategory.SECURITY, authority_map
        )
        assert concern is not None
        assert concern in {c.concern for c in authority_map.concerns}

    def test_an_unmatched_statement_resolves_to_none_rather_than_a_guess(
        self, authority_map: AuthorityMap
    ) -> None:
        concern = map_architecture(
            "Widgets must exist.", RequirementCategory.UNCLASSIFIED, authority_map
        )
        assert concern is None

    def test_mapping_never_invents_an_owner_not_in_the_live_map(
        self, authority_map: AuthorityMap
    ) -> None:
        """No category->owner table exists in this module; every returned
        concern must be a concern the live authority map actually declares."""
        live_concerns = {c.concern for c in authority_map.concerns}
        for statement, category in (
            ("Users must authenticate securely.", RequirementCategory.SECURITY),
            ("Orders must persist in the database.", RequirementCategory.DATA),
            ("The API must expose an external endpoint.", RequirementCategory.INTEGRATION),
        ):
            concern = map_architecture(statement, category, authority_map)
            if concern is not None:
                assert concern in live_concerns


class TestDeriveBlueprintNegativeControls:
    def test_empty_goal_text_is_refused(self, authority_map: AuthorityMap) -> None:
        with pytest.raises(MalformedProductGoalError):
            derive_blueprint("   ", authority_map)

    def test_a_short_vague_statement_is_flagged_underspecified(
        self, authority_map: AuthorityMap
    ) -> None:
        blueprint = derive_blueprint("It should be fast.", authority_map)
        kinds = {q.kind for q in blueprint.unresolved}
        assert UnresolvedQuestionKind.UNDERSPECIFIED in kinds

    def test_a_tbd_marker_is_flagged_ambiguous(self, authority_map: AuthorityMap) -> None:
        blueprint = derive_blueprint("The provider is TBD for now.", authority_map)
        kinds = {q.kind for q in blueprint.unresolved}
        assert UnresolvedQuestionKind.AMBIGUOUS in kinds

    def test_contradictory_numeric_constraints_are_flagged_not_silently_resolved(
        self, authority_map: AuthorityMap
    ) -> None:
        goal = (
            "The system must respond within 200ms. "
            "The system must respond within 500ms."
        )
        blueprint = derive_blueprint(goal, authority_map)
        contradictions = [
            q for q in blueprint.unresolved
            if q.kind is UnresolvedQuestionKind.CONTRADICTORY
        ]
        assert contradictions, blueprint.unresolved
        assert contradictions[0].subject_index == 1

    def test_agreeing_numeric_constraints_are_not_flagged_contradictory(
        self, authority_map: AuthorityMap
    ) -> None:
        goal = (
            "The system must respond within 200ms. "
            "The system must respond within 200ms."
        )
        blueprint = derive_blueprint(goal, authority_map)
        contradictions = [
            q for q in blueprint.unresolved
            if q.kind is UnresolvedQuestionKind.CONTRADICTORY
        ]
        assert not contradictions

    def test_nothing_is_silently_invented_for_an_unresolved_statement(
        self, authority_map: AuthorityMap
    ) -> None:
        """The engine never fabricates acceptance criteria it cannot derive."""
        blueprint = derive_blueprint("It should be fast.", authority_map)
        assert blueprint.requirements[0].acceptance_criteria == ()


class TestDeterministicRepeatability:
    def test_identical_goal_and_map_state_yield_identical_blueprint_id(
        self, authority_map: AuthorityMap
    ) -> None:
        goal = "Users must authenticate securely. The system must respond within 200ms."
        first = derive_blueprint(goal, authority_map)
        second = derive_blueprint(goal, authority_map)
        assert first.blueprint_id == second.blueprint_id
        assert first.requirements == second.requirements
        assert first.unresolved == second.unresolved
