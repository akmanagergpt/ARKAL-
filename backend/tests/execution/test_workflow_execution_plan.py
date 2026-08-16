"""C-20 derived, compiled execution plan (ADR-0004) — Phase 17 Package 3.

Proves ARK-REQ-0064 (derived caches deterministically derived, hash-bound,
invalidated), ARK-REQ-0065/ARK-REQ-0332 (a stale-hash derived representation
is never executed).
"""

from __future__ import annotations

import pytest

from arkali.execution.workflow.errors import StaleDerivedRepresentation
from arkali.execution.workflow.execution_plan import CompiledExecutionPlan
from arkali.execution.workflow.graph_model import (
    SemverBump,
    WorkflowEdge,
    WorkflowGraphDocument,
    WorkflowNode,
)
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from tests.execution.workflow_harness import (  # noqa: F401 - fixtures by import
    Reopener,
    clock,
    database_path,
    pdp,
    pep,
    reopen,
    small_document,
    vocabulary,
)


def _document(vocabulary: GraphVocabulary, workflow_id: str = "wf-1") -> WorkflowGraphDocument:
    return small_document(vocabulary, workflow_id)


class TestDerivationIsBoundAndCorrect:
    def test_bound_hash_equals_the_document_content_hash(
        self, vocabulary: GraphVocabulary
    ) -> None:
        document = _document(vocabulary)
        plan = CompiledExecutionPlan.derive(document)
        assert plan.bound_revision_hash == document.content_hash
        assert plan.workflow_id == document.workflow_id

    def test_node_and_outgoing_lookups_match_the_document(
        self, vocabulary: GraphVocabulary
    ) -> None:
        document = _document(vocabulary)
        plan = CompiledExecutionPlan.derive(document)
        assert plan.node_ids() == tuple(sorted(n.node_id for n in document.nodes()))
        for node in document.nodes():
            assert plan.node(node.node_id) == node
            assert plan.outgoing(node.node_id) == document.outgoing(node.node_id)
        assert plan.node("no-such-node") is None
        assert plan.outgoing("no-such-node") == ()

    def test_trigger_ids_match_the_document(self, vocabulary: GraphVocabulary) -> None:
        document = _document(vocabulary)
        plan = CompiledExecutionPlan.derive(document)
        assert plan.trigger_ids == document.trigger_node_ids()


class TestDerivationIsDeterministic:
    def test_identical_content_in_different_order_derives_an_identical_plan(
        self, vocabulary: GraphVocabulary
    ) -> None:
        nodes = [
            WorkflowNode(node_id="n-trigger", kind="trigger", label="Start"),
            WorkflowNode(node_id="n-a", kind="data", label="A"),
            WorkflowNode(node_id="n-b", kind="data", label="B"),
        ]
        edges = [
            WorkflowEdge(edge_id="e-1", source_node_id="n-trigger", target_node_id="n-a"),
            WorkflowEdge(edge_id="e-2", source_node_id="n-a", target_node_id="n-b"),
        ]
        forward = WorkflowGraphDocument.build(vocabulary, "wf-det", nodes=nodes, edges=edges)
        backward = WorkflowGraphDocument.build(
            vocabulary, "wf-det", nodes=list(reversed(nodes)), edges=list(reversed(edges))
        )
        plan_a = CompiledExecutionPlan.derive(forward)
        plan_b = CompiledExecutionPlan.derive(backward)
        assert plan_a.bound_revision_hash == plan_b.bound_revision_hash
        assert plan_a.node_ids() == plan_b.node_ids()
        assert plan_a.outgoing("n-trigger") == plan_b.outgoing("n-trigger")


class TestStalenessIsRefusedNotWarnedAbout:
    def test_a_fresh_plan_is_not_stale_and_require_fresh_does_not_raise(
        self, vocabulary: GraphVocabulary
    ) -> None:
        document = _document(vocabulary)
        plan = CompiledExecutionPlan.derive(document)
        assert plan.is_stale(document.content_hash) is False
        plan.require_fresh(document.content_hash)  # must not raise

    def test_a_semantic_change_makes_the_plan_stale(self, vocabulary: GraphVocabulary) -> None:
        original = _document(vocabulary)
        plan = CompiledExecutionPlan.derive(original)
        changed = WorkflowGraphDocument.build(
            vocabulary,
            "wf-1",
            nodes=[
                WorkflowNode(node_id="n-trigger", kind="trigger", label="Start"),
                WorkflowNode(node_id="n-data", kind="data", label="Transform"),
                WorkflowNode(node_id="n-extra", kind="data", label="Extra"),
            ],
            edges=[
                WorkflowEdge(edge_id="e-1", source_node_id="n-trigger", target_node_id="n-data"),
                WorkflowEdge(edge_id="e-2", source_node_id="n-data", target_node_id="n-extra"),
            ],
        )
        assert plan.is_stale(changed.content_hash) is True
        with pytest.raises(StaleDerivedRepresentation, match=plan.bound_revision_hash):
            plan.require_fresh(changed.content_hash)

    def test_a_layout_only_change_also_makes_the_plan_stale(
        self, vocabulary: GraphVocabulary
    ) -> None:
        """The full document is hash-bound (module docstring); a layout-only
        edit is still a change ADR-0004 requires invalidation for.
        """
        original = _document(vocabulary)
        plan = CompiledExecutionPlan.derive(original)
        moved = WorkflowGraphDocument.build(
            vocabulary,
            "wf-1",
            nodes=[
                WorkflowNode(
                    node_id="n-trigger", kind="trigger", label="Start", position_x=99.0
                ),
                WorkflowNode(node_id="n-data", kind="data", label="Transform"),
            ],
            edges=[
                WorkflowEdge(edge_id="e-1", source_node_id="n-trigger", target_node_id="n-data")
            ],
        )
        assert plan.is_stale(moved.content_hash) is True
        with pytest.raises(StaleDerivedRepresentation):
            plan.require_fresh(moved.content_hash)


class TestStalenessAgainstRealPersistedRevisions:
    """Integration evidence: a plan derived from one published revision is
    refused once a later revision is published under real persistence -
    ARK-REQ-0065/0332 proven against real infrastructure, not a fixture.
    """

    def test_a_plan_survives_across_the_revision_it_was_derived_from(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        document = _document(vocabulary)
        plan = CompiledExecutionPlan.derive(document)
        with reopen.session() as (store, session):
            record = store.publish(document, semver_bump=SemverBump.PATCH)
            session.commit()
        with reopen.session() as (store, _session):
            latest = store.require_revision("wf-1", 1)
            assert not plan.is_stale(latest.revision_hash)
            plan.require_fresh(latest.revision_hash)

    def test_a_plan_is_refused_once_a_new_revision_is_published(
        self, reopen: Reopener, vocabulary: GraphVocabulary
    ) -> None:
        document = _document(vocabulary)
        plan = CompiledExecutionPlan.derive(document)
        with reopen.session() as (store, session):
            store.publish(document, semver_bump=SemverBump.PATCH)
            session.commit()

        second = WorkflowGraphDocument.build(
            vocabulary,
            "wf-1",
            nodes=[
                WorkflowNode(node_id="n-trigger", kind="trigger", label="Start"),
                WorkflowNode(node_id="n-data", kind="data", label="Transform"),
                WorkflowNode(node_id="n-extra", kind="data", label="Extra"),
            ],
            edges=[
                WorkflowEdge(edge_id="e-1", source_node_id="n-trigger", target_node_id="n-data"),
                WorkflowEdge(edge_id="e-2", source_node_id="n-data", target_node_id="n-extra"),
            ],
        )
        with reopen.session() as (store, session):
            store.publish(second, semver_bump=SemverBump.MINOR)
            session.commit()

        with reopen.session() as (store, _session):
            latest = store.require_revision("wf-1", 2)
            assert plan.is_stale(latest.revision_hash)
            with pytest.raises(StaleDerivedRepresentation):
                plan.require_fresh(latest.revision_hash)
