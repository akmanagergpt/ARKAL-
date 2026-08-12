"""C-24: the graph set, and rebuild determinism (ARK-REQ-0066).

Phase 11 Package 2. `CONTRACT_INVENTORY.md` row 24 names **rebuild determinism**
as this contract's evidence responsibility, so it is the property most of these
controls are about. The rest enforce the two structural rules `ARCHITECTURE.md`
§11 states: only the specified graph kinds exist, and the store is derived and
never an authority.
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.engineering.codeintel.code_graph import CodeGraph, GraphEdge, GraphNode
from arkali.engineering.codeintel.errors import (
    DerivedStoreTreatedAsAuthority,
    NonDeterministicRebuild,
    UnknownGraphKind,
)
from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.engineering.codeintel.python_builder import PythonGraphBuilder
from arkali.kernel.contracts.content_address import is_address

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
SOURCE_ROOT: Final[pathlib.Path] = REPO / "backend/arkali/engineering/codeintel"


@pytest.fixture(scope="module")
def vocabulary() -> GraphVocabulary:
    return GraphVocabulary.load(REPO)


@pytest.fixture(scope="module")
def builder() -> PythonGraphBuilder:
    """Module scope, not class scope: pytest deprecates a class-scoped fixture
    defined as an instance method, and the builder is stateless anyway."""
    return PythonGraphBuilder(GraphVocabulary.load(REPO), SOURCE_ROOT)


def node(identifier: str = "a.py::Thing", source: str = "a.py") -> GraphNode:
    return GraphNode(identifier=identifier, source=source)


def edge(origin: str = "a.py", target: str = "b", source: str = "a.py") -> GraphEdge:
    return GraphEdge(origin=origin, target=target, source=source)


def graph(vocabulary: GraphVocabulary, kind: str = "symbol", **kw: object) -> CodeGraph:
    return CodeGraph.build(vocabulary, kind, **kw)  # type: ignore[arg-type]


class TestOnlySpecifiedGraphKindsExist:
    def test_every_canonical_kind_can_be_built(
        self, vocabulary: GraphVocabulary
    ) -> None:
        for kind in vocabulary.graphs():
            assert graph(vocabulary, kind).kind == vocabulary.require_graph(kind)

    def test_an_unspecified_kind_cannot_be_built(
        self, vocabulary: GraphVocabulary
    ) -> None:
        with pytest.raises(UnknownGraphKind, match="not a canonical graph kind"):
            graph(vocabulary, "gossip")

    def test_the_kind_is_stored_in_canonical_identifier_form(
        self, vocabulary: GraphVocabulary
    ) -> None:
        assert graph(vocabulary, "frontend-contract").kind == "frontend_contract"


class TestRebuildDeterminism:
    """CONTRACT_INVENTORY.md row 24 names this as C-24's verification."""

    def test_the_address_is_a_canonical_content_address(
        self, vocabulary: GraphVocabulary
    ) -> None:
        assert is_address(graph(vocabulary, nodes=[node()]).address)

    def test_identical_facts_address_identically(
        self, vocabulary: GraphVocabulary
    ) -> None:
        first = graph(vocabulary, nodes=[node(), node("a.py::Other")])
        second = graph(vocabulary, nodes=[node(), node("a.py::Other")])
        assert first.address == second.address
        first.assert_rebuild_matches(second)

    def test_insertion_order_cannot_reach_the_address(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """The core of determinism: normalisation, not caller tidiness."""
        forward = graph(vocabulary, nodes=[node("a"), node("b"), node("c")])
        reversed_ = graph(vocabulary, nodes=[node("c"), node("b"), node("a")])
        assert forward.address == reversed_.address
        forward.assert_rebuild_matches(reversed_)

    def test_duplicate_insertion_cannot_reach_the_address(
        self, vocabulary: GraphVocabulary
    ) -> None:
        once = graph(vocabulary, nodes=[node()])
        twice = graph(vocabulary, nodes=[node(), node()])
        assert once.address == twice.address

    @pytest.mark.parametrize(
        "change",
        [{"identifier": "a.py::Different"}, {"source": "other.py"}],
    )
    def test_any_change_to_any_node_changes_the_address(
        self, vocabulary: GraphVocabulary, change: dict[str, str]
    ) -> None:
        base = graph(vocabulary, nodes=[node()])
        altered = graph(vocabulary, nodes=[node(**change)])
        assert base.address != altered.address

    def test_an_edge_change_changes_the_address(
        self, vocabulary: GraphVocabulary
    ) -> None:
        base = graph(vocabulary, edges=[edge()])
        altered = graph(vocabulary, edges=[edge(target="c")])
        assert base.address != altered.address

    def test_edge_direction_is_part_of_the_identity(
        self, vocabulary: GraphVocabulary
    ) -> None:
        forward = graph(vocabulary, edges=[edge(origin="a", target="b")])
        backward = graph(vocabulary, edges=[edge(origin="b", target="a")])
        assert forward.address != backward.address

    def test_two_kinds_with_identical_facts_address_differently(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """The kind is part of what a graph IS, not a label on it."""
        assert (
            graph(vocabulary, "symbol", nodes=[node()]).address
            != graph(vocabulary, "import", nodes=[node()]).address
        )

    def test_a_differing_rebuild_is_refused_rather_than_reported(
        self, vocabulary: GraphVocabulary
    ) -> None:
        base = graph(vocabulary, nodes=[node()])
        with pytest.raises(NonDeterministicRebuild, match="rebuild determinism"):
            base.assert_rebuild_matches(graph(vocabulary, nodes=[node("changed")]))

    def test_a_rebuild_of_a_different_kind_is_refused(
        self, vocabulary: GraphVocabulary
    ) -> None:
        with pytest.raises(NonDeterministicRebuild, match="kind"):
            graph(vocabulary, "symbol").assert_rebuild_matches(
                graph(vocabulary, "import")
            )


class TestTheStoreIsDerivedAndNeverAnAuthority:
    def test_being_asked_for_authority_always_refuses(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """ARCHITECTURE.md §11: derived store, never an authority."""
        for concern in ("provider_health", "policy_decision", "anything at all"):
            with pytest.raises(DerivedStoreTreatedAsAuthority, match="derived store"):
                graph(vocabulary).resolve_authority(concern)

    def test_the_refusal_points_at_the_owning_authorities(
        self, vocabulary: GraphVocabulary
    ) -> None:
        with pytest.raises(DerivedStoreTreatedAsAuthority, match="owning authorities"):
            graph(vocabulary).resolve_authority("provider_health")

    def test_every_node_and_edge_records_its_source(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """A derived store must be able to point back rather than be believed."""
        built = graph(
            vocabulary,
            nodes=[node(source="a.py")],
            edges=[edge(source="b.py")],
        )
        assert built.sources() == ("a.py", "b.py")

    def test_a_node_without_a_source_cannot_exist(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            GraphNode(identifier="x", source="  ")


class TestThePythonBuilderOverRealSource:
    def test_it_reports_exactly_what_it_builds(
        self, builder: PythonGraphBuilder, vocabulary: GraphVocabulary
    ) -> None:
        assert builder.builds() == ("symbol", "import", "dependency")
        assert set(builder.builds()) | set(builder.unbuilt()) == set(
            vocabulary.graph_ids()
        )

    def test_an_unbuilt_kind_is_refused_not_returned_empty(
        self, builder: PythonGraphBuilder
    ) -> None:
        """An empty graph is indistinguishable from 'nothing found'."""
        for kind in builder.unbuilt():
            with pytest.raises(UnknownGraphKind, match="does not produce it"):
                builder.build(kind)

    def test_it_finds_real_symbols_imports_and_dependencies(
        self, builder: PythonGraphBuilder
    ) -> None:
        """Non-vacuous: a builder that found nothing would prove nothing."""
        assert len(builder.build("symbol").nodes()) > 0
        assert len(builder.build("import").edges()) > 0
        assert len(builder.build("dependency").edges()) > 0

    def test_rebuilding_from_the_same_source_is_deterministic(
        self, builder: PythonGraphBuilder
    ) -> None:
        """C-24's verification, over real repository source."""
        for kind in builder.builds():
            first = builder.build(kind)
            second = PythonGraphBuilder(
                GraphVocabulary.load(REPO), SOURCE_ROOT
            ).build(kind)
            first.assert_rebuild_matches(second)

    def test_a_changed_file_changes_the_address(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        """Determinism must not be achieved by ignoring the input."""
        (tmp_path / "m.py").write_text("import os\n\n\ndef f():\n    pass\n", "utf-8")
        before = PythonGraphBuilder(vocabulary, tmp_path).build("symbol")
        (tmp_path / "m.py").write_text("import os\n\n\ndef g():\n    pass\n", "utf-8")
        after = PythonGraphBuilder(vocabulary, tmp_path).build("symbol")
        assert before.address != after.address

    def test_the_dependency_graph_is_coarser_than_the_import_graph(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        """`a.b.c` and `a.b.d` are two imports but one dependency."""
        (tmp_path / "m.py").write_text("import a.b.c\nimport a.b.d\n", "utf-8")
        builder = PythonGraphBuilder(vocabulary, tmp_path)
        assert {e.target for e in builder.build("import").edges()} == {"a.b.c", "a.b.d"}
        assert {e.target for e in builder.build("dependency").edges()} == {"a"}

    def test_it_neither_imports_nor_executes_what_it_reads(
        self, tmp_path: pathlib.Path, vocabulary: GraphVocabulary
    ) -> None:
        """Syntax only: an unimportable module still contributes its symbols."""
        (tmp_path / "broken.py").write_text(
            "import definitely_not_installed_xyz\n\n\nclass Thing:\n    pass\n", "utf-8"
        )
        built = PythonGraphBuilder(vocabulary, tmp_path).build("symbol")
        assert any("Thing" in n.identifier for n in built.nodes())
