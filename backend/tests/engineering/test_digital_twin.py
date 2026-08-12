"""Phase 11 Package 3: the Digital Twin composes every specified view."""

from __future__ import annotations

import pathlib
from typing import Final

import pytest
from pydantic import ValidationError

from arkali.engineering.codeintel.digital_twin import DigitalTwin, TwinView
from arkali.engineering.codeintel.errors import (
    DerivedStoreTreatedAsAuthority,
    IncompleteDigitalTwin,
    UnknownTwinView,
)
from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.kernel.contracts.content_address import address_of

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


def contribution(view: str, *, absent: bool = False) -> TwinView:
    if absent:
        return TwinView(
            view=view,
            sources=(f"authority:{view}",),
            absent_reason="owning source is not configured",
        )
    return TwinView(
        view=view,
        sources=(f"authority:{view}",),
        artifact_addresses=(address_of(view.encode()),),
    )


def all_contributions(vocabulary: GraphVocabulary) -> list[TwinView]:
    return [contribution(view) for view in vocabulary.view_ids()]


class TestCanonicalComposition:
    def test_composes_exactly_the_views_read_from_the_architecture(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        twin = DigitalTwin.compose(vocabulary, all_contributions(vocabulary))
        assert twin.view_ids() == vocabulary.view_ids()
        assert len(twin) == len(vocabulary.view_ids())

    def test_normalises_names_and_preserves_canonical_order(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        contributions = [contribution(name) for name in reversed(vocabulary.views())]
        assert DigitalTwin.compose(vocabulary, contributions).view_ids() == (
            vocabulary.view_ids()
        )

    @pytest.mark.parametrize("count", [2, 4, 12])
    def test_the_composed_count_follows_the_vocabulary(self, count: int) -> None:
        ids = tuple(f"view_{index}" for index in range(count))
        vocabulary = GraphVocabulary(("a", "b"), ids, "in-memory authority")
        twin = DigitalTwin.compose(vocabulary, [contribution(view) for view in ids])
        assert len(twin) == count


class TestHonestCoverage:
    def test_a_missing_view_is_refused_not_silently_defaulted(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        with pytest.raises(IncompleteDigitalTwin, match="omits specified view"):
            DigitalTwin.compose(vocabulary, all_contributions(vocabulary)[:-1])

    def test_an_unknown_view_is_refused(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        with pytest.raises(UnknownTwinView):
            DigitalTwin.compose(vocabulary, [*all_contributions(vocabulary), contribution("vibes")])

    def test_a_duplicate_view_is_refused(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        contributions = all_contributions(vocabulary)
        with pytest.raises(IncompleteDigitalTwin, match="more than once"):
            DigitalTwin.compose(vocabulary, [*contributions, contributions[0]])

    def test_an_unavailable_view_is_declared_absent_never_returned_empty(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        contributions = all_contributions(vocabulary)
        contributions[0] = contribution(vocabulary.view_ids()[0], absent=True)
        twin = DigitalTwin.compose(vocabulary, contributions)
        assert twin.absent_view_ids() == (vocabulary.view_ids()[0],)

    def test_a_view_with_no_material_and_no_absence_is_invalid(self) -> None:
        with pytest.raises(ValidationError, match="artifact addresses"):
            TwinView(view="code", sources=("source.py",))

    def test_a_view_cannot_claim_material_and_absence_together(self) -> None:
        with pytest.raises(ValidationError, match="never neither or both"):
            TwinView(
                view="code",
                sources=("source.py",),
                artifact_addresses=(address_of(b"code"),),
                absent_reason="not configured",
            )

    def test_a_derived_view_without_a_source_is_invalid(self) -> None:
        with pytest.raises(ValidationError, match="must name its source"):
            TwinView(
                view="code", sources=(), artifact_addresses=(address_of(b"code"),)
            )

    def test_a_noncanonical_artifact_address_is_invalid(self) -> None:
        with pytest.raises(ValidationError, match="canonical content addresses"):
            TwinView(view="code", sources=("source.py",), artifact_addresses=("code",))

    def test_the_twin_never_answers_as_an_authority(self) -> None:
        vocabulary = GraphVocabulary.load(REPO)
        twin = DigitalTwin.compose(vocabulary, all_contributions(vocabulary))
        with pytest.raises(DerivedStoreTreatedAsAuthority, match="owning source"):
            twin.resolve_authority("deployment truth")
