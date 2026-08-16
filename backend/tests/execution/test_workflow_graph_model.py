"""C-20 canonical workflow graph document — construction, validity, content
addressing and semver arithmetic (Phase 17 Package 1).

Every negative control asserts the *type and reason* a graph was refused, not
merely that construction raised (the F-0017 defect applied to graphs).
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.execution.workflow.errors import (
    ConstructKindMismatch,
    DanglingEdgeReference,
    DuplicateEdgeIdentity,
    DuplicateNodeIdentity,
    EmptyGraph,
    InvalidSemverTransition,
    NonDeterministicGraphRebuild,
    NoTriggerNode,
    UnreachableNode,
)
from arkali.execution.workflow.graph_model import (
    SemverBump,
    WorkflowEdge,
    WorkflowGraphDocument,
    WorkflowNode,
    bump_semver,
)
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def vocabulary() -> GraphVocabulary:
    return GraphVocabulary.load(REPO)


def _trigger(node_id: str = "n-trigger") -> WorkflowNode:
    return WorkflowNode(node_id=node_id, kind="trigger", label="Start")


def _logic(node_id: str, construct: str) -> WorkflowNode:
    return WorkflowNode(
        node_id=node_id, kind="logic", control_construct=construct, label=construct
    )


def _data(node_id: str) -> WorkflowNode:
    return WorkflowNode(node_id=node_id, kind="data", label="Transform")


def _edge(
    edge_id: str, source: str, target: str, condition: str | None = None
) -> WorkflowEdge:
    return WorkflowEdge(
        edge_id=edge_id, source_node_id=source, target_node_id=target, condition=condition
    )


class TestAValidGraphBuilds:
    def test_trigger_to_data_builds(self, vocabulary: GraphVocabulary) -> None:
        document = WorkflowGraphDocument.build(
            vocabulary,
            "wf-1",
            nodes=[_trigger(), _data("n-data")],
            edges=[_edge("e-1", "n-trigger", "n-data")],
        )
        assert document.workflow_id == "wf-1"
        assert len(document) == 2
        assert [n.node_id for n in document.nodes()] == ["n-data", "n-trigger"]

    def test_a_logic_node_with_a_cycle_builds(self, vocabulary: GraphVocabulary) -> None:
        """LOOP/RETRY need a back-edge; cycles are not forbidden."""
        document = WorkflowGraphDocument.build(
            vocabulary,
            "wf-loop",
            nodes=[_trigger(), _logic("n-loop", "LOOP"), _data("n-body")],
            edges=[
                _edge("e-1", "n-trigger", "n-loop"),
                _edge("e-2", "n-loop", "n-body", condition="continue"),
                _edge("e-3", "n-body", "n-loop"),
            ],
        )
        assert document.content_hash.startswith("sha256:")


class TestValidityRefusals:
    def test_empty_graph_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(EmptyGraph):
            WorkflowGraphDocument.build(vocabulary, "wf-empty")

    def test_duplicate_node_id_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(DuplicateNodeIdentity, match="n-trigger"):
            WorkflowGraphDocument.build(
                vocabulary, "wf-2", nodes=[_trigger(), _trigger()],
            )

    def test_duplicate_edge_id_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(DuplicateEdgeIdentity, match="e-1"):
            WorkflowGraphDocument.build(
                vocabulary,
                "wf-3",
                nodes=[_trigger(), _data("n-data")],
                edges=[
                    _edge("e-1", "n-trigger", "n-data"),
                    _edge("e-1", "n-trigger", "n-data"),
                ],
            )

    def test_dangling_edge_source_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(DanglingEdgeReference, match="ghost"):
            WorkflowGraphDocument.build(
                vocabulary,
                "wf-4",
                nodes=[_trigger(), _data("n-data")],
                edges=[_edge("e-1", "ghost", "n-data")],
            )

    def test_dangling_edge_target_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(DanglingEdgeReference, match="ghost"):
            WorkflowGraphDocument.build(
                vocabulary,
                "wf-5",
                nodes=[_trigger(), _data("n-data")],
                edges=[_edge("e-1", "n-trigger", "ghost")],
            )

    def test_logic_node_without_construct_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(ConstructKindMismatch, match="n-logic"):
            WorkflowGraphDocument.build(
                vocabulary,
                "wf-6",
                nodes=[_trigger(), WorkflowNode(node_id="n-logic", kind="logic")],
                edges=[_edge("e-1", "n-trigger", "n-logic")],
            )

    def test_non_logic_node_with_construct_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(ConstructKindMismatch, match="n-data"):
            WorkflowGraphDocument.build(
                vocabulary,
                "wf-7",
                nodes=[
                    _trigger(),
                    WorkflowNode(node_id="n-data", kind="data", control_construct="IF"),
                ],
                edges=[_edge("e-1", "n-trigger", "n-data")],
            )

    def test_unreachable_node_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(UnreachableNode, match="n-orphan"):
            WorkflowGraphDocument.build(
                vocabulary,
                "wf-8",
                nodes=[_trigger(), _data("n-data"), _data("n-orphan")],
                edges=[_edge("e-1", "n-trigger", "n-data")],
            )

    def test_graph_with_no_trigger_refuses(self, vocabulary: GraphVocabulary) -> None:
        with pytest.raises(NoTriggerNode):
            WorkflowGraphDocument.build(vocabulary, "wf-9", nodes=[_data("n-data")])


class TestContentAddressDeterminism:
    def test_identical_content_addresses_identically_regardless_of_order(
        self, vocabulary: GraphVocabulary
    ) -> None:
        nodes = [_trigger(), _data("n-a"), _data("n-b")]
        edges = [_edge("e-1", "n-trigger", "n-a"), _edge("e-2", "n-a", "n-b")]
        forward = WorkflowGraphDocument.build(vocabulary, "wf-10", nodes=nodes, edges=edges)
        backward = WorkflowGraphDocument.build(
            vocabulary, "wf-10", nodes=list(reversed(nodes)), edges=list(reversed(edges))
        )
        assert forward.content_hash == backward.content_hash
        forward.assert_rebuild_matches(backward)

    def test_a_semantic_change_changes_the_address(
        self, vocabulary: GraphVocabulary
    ) -> None:
        base = WorkflowGraphDocument.build(
            vocabulary, "wf-11",
            nodes=[_trigger(), _data("n-a")],
            edges=[_edge("e-1", "n-trigger", "n-a")],
        )
        changed = WorkflowGraphDocument.build(
            vocabulary, "wf-11",
            nodes=[_trigger(), _data("n-a"), _data("n-b")],
            edges=[_edge("e-1", "n-trigger", "n-a"), _edge("e-2", "n-a", "n-b")],
        )
        assert base.content_hash != changed.content_hash

    def test_a_layout_only_change_also_changes_the_address(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """The full document is hashed (module docstring); layout is not
        carved out as non-semantic, since no canonical source states that
        split for the canonical revision itself.
        """
        trigger_at_origin = _trigger()
        trigger_moved = WorkflowNode(
            node_id="n-trigger", kind="trigger", label="Start", position_x=42.0
        )
        base = WorkflowGraphDocument.build(
            vocabulary, "wf-12",
            nodes=[trigger_at_origin, _data("n-a")],
            edges=[_edge("e-1", "n-trigger", "n-a")],
        )
        moved = WorkflowGraphDocument.build(
            vocabulary, "wf-12",
            nodes=[trigger_moved, _data("n-a")],
            edges=[_edge("e-1", "n-trigger", "n-a")],
        )
        assert base.content_hash != moved.content_hash

    def test_rebuild_mismatch_raises_nondeterministic_rebuild(
        self, vocabulary: GraphVocabulary
    ) -> None:
        left = WorkflowGraphDocument.build(vocabulary, "wf-13", nodes=[_trigger()])
        right = WorkflowGraphDocument.build(
            vocabulary, "wf-13",
            nodes=[_trigger(), _data("n-a")],
            edges=[_edge("e-1", "n-trigger", "n-a")],
        )
        with pytest.raises(NonDeterministicGraphRebuild):
            left.assert_rebuild_matches(right)


class TestSemverBump:
    def test_first_revision_is_always_one_zero_zero(self) -> None:
        assert bump_semver(None, SemverBump.PATCH) == "1.0.0"
        assert bump_semver(None, SemverBump.MAJOR) == "1.0.0"

    def test_patch_bump(self) -> None:
        assert bump_semver("1.2.3", SemverBump.PATCH) == "1.2.4"

    def test_minor_bump_resets_patch(self) -> None:
        assert bump_semver("1.2.3", SemverBump.MINOR) == "1.3.0"

    def test_major_bump_resets_minor_and_patch(self) -> None:
        assert bump_semver("1.2.3", SemverBump.MAJOR) == "2.0.0"

    def test_unknown_bump_kind_refuses(self) -> None:
        with pytest.raises(InvalidSemverTransition, match="REVISION"):
            bump_semver("1.0.0", "REVISION")

    def test_malformed_previous_semver_refuses(self) -> None:
        with pytest.raises(InvalidSemverTransition, match="v1"):
            bump_semver("v1", SemverBump.PATCH)
