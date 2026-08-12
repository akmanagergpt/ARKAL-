"""Phase 11 composed journey: source -> deterministic graphs -> Digital Twin.

The journey uses the real canonical vocabulary and real repository Python
source.  It does not manufacture the graph kinds whose adapters do not yet
exist: those views are represented by explicit absence declarations.
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.codeintel.code_graph import CodeGraph
from arkali.engineering.codeintel.digital_twin import DigitalTwin, TwinView
from arkali.engineering.codeintel.errors import DerivedStoreTreatedAsAuthority
from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.engineering.codeintel.python_builder import PythonGraphBuilder

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
SOURCE: Final[pathlib.Path] = REPO / "backend/arkali/engineering/codeintel"
PHASE: Final[str] = "11"


@pytest.fixture(scope="module")
def vocabulary() -> GraphVocabulary:
    return GraphVocabulary.load(REPO)


@pytest.fixture(scope="module")
def builder(vocabulary: GraphVocabulary) -> PythonGraphBuilder:
    return PythonGraphBuilder(vocabulary, SOURCE)


@pytest.fixture(scope="module")
def graphs(builder: PythonGraphBuilder) -> dict[str, CodeGraph]:
    return {kind: builder.build(kind) for kind in builder.builds()}


class TestPhase11Journey:
    def test_step_1_the_graph_and_view_sets_come_from_repository_authority(
        self, vocabulary: GraphVocabulary
    ) -> None:
        assert len(vocabulary.graph_ids()) >= 2
        assert len(vocabulary.view_ids()) >= 2

    def test_step_2_real_python_source_builds_nonempty_graphs(
        self, builder: PythonGraphBuilder, graphs: dict[str, CodeGraph]
    ) -> None:
        assert tuple(graphs) == builder.builds()
        for graph in graphs.values():
            assert graph.nodes() or graph.edges()
            assert graph.sources()

    def test_step_3_a_fresh_rebuild_matches_every_built_graph(
        self, vocabulary: GraphVocabulary, graphs: dict[str, CodeGraph]
    ) -> None:
        rebuilt = PythonGraphBuilder(vocabulary, SOURCE)
        for kind, graph in graphs.items():
            graph.assert_rebuild_matches(rebuilt.build(kind))

    def test_step_4_every_canonical_view_is_composed_once(
        self,
        vocabulary: GraphVocabulary,
        graphs: dict[str, CodeGraph],
    ) -> None:
        addresses = tuple(graph.address for graph in graphs.values())
        contributions = []
        for view in vocabulary.view_ids():
            if view == "code":
                contributions.append(
                    TwinView(
                        view=view,
                        sources=tuple(str(path.relative_to(REPO)) for path in SOURCE.rglob("*.py")),
                        artifact_addresses=addresses,
                    )
                )
            else:
                contributions.append(
                    TwinView(
                        view=view,
                        sources=("owning authority not yet composed",),
                        absent_reason="no Phase 11 adapter supplies this view",
                    )
                )
        twin = DigitalTwin.compose(vocabulary, contributions)
        assert twin.view_ids() == vocabulary.view_ids()
        assert set(twin.absent_view_ids()) == set(vocabulary.view_ids()) - {"code"}

    def test_step_5_neither_derived_store_can_become_an_authority(
        self, vocabulary: GraphVocabulary, graphs: dict[str, CodeGraph]
    ) -> None:
        with pytest.raises(DerivedStoreTreatedAsAuthority):
            next(iter(graphs.values())).resolve_authority("architecture truth")
        twin = DigitalTwin.compose(
            vocabulary,
            [
                TwinView(
                    view=view,
                    sources=("owner",),
                    absent_reason="not composed in this assertion",
                )
                for view in vocabulary.view_ids()
            ],
        )
        with pytest.raises(DerivedStoreTreatedAsAuthority):
            twin.resolve_authority("deployment truth")

    def test_step_6_the_denominator_is_derived_from_the_register(self) -> None:
        requirements = RequirementRegister.load(REPO).for_phase(PHASE)
        assert {requirement.req_id for requirement in requirements} == {
            "ARK-REQ-0066",
            "ARK-REQ-0067",
        }
        assert {requirement.owning_component for requirement in requirements} == {
            "engineering.codeintel"
        }
