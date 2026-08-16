"""C-20 workflow executor: real execution evidence for every node kind and
control construct (Phase 17 Package 5). ARK-REQ-0328/0329/0330/0332.

REAL INFRASTRUCTURE ONLY - see `executor_harness.py`. Every negative control
asserts the type and reason a call was refused.

Split from `test_workflow_executor_pause_and_recovery.py` at the
`module <= 400 logical lines` budget (`scripts/check_repository_structure.py`
scopes this to every tracked module, tests included) - this file covers
linear dispatch and the stateless branching/fan-out/join constructs; the
sibling file covers `WAIT`/`RETRY`/`ERROR HANDLER`/`HUMAN APPROVAL` (the
constructs with persisted counters or a pause) and unknown-execution
refusals.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from arkali.execution.durable.records import DurableJobRecord
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from tests.execution.executor_harness import (  # noqa: F401 - fixtures by import
    ExecutorReopener,
    approval_gate,
    build_document,
    clock,
    database_path,
    edge,
    node,
    pdp,
    publish,
    reopen,
    vocabulary,
)

NON_LOGIC_KINDS = (
    "trigger", "AI", "agent", "engineering", "data", "integration",
    "approval", "release", "notification",
)


def _linear_document(vocabulary: GraphVocabulary, workflow_id: str = "wf-exec"):
    return build_document(
        vocabulary, workflow_id,
        [node("n-trigger", "trigger"), node("n-data", "data")],
        [edge("e-1", "n-trigger", "n-data")],
    )


class TestALinearExecutionRunsToCompletion:
    def test_a_two_node_graph_succeeds_with_real_job_evidence(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = _linear_document(vocabulary)
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-1", "wf-exec")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
            assert record.frontier == []
        with reopen.session() as (executor, _store, session):
            evidence = executor.evidence("exec-1")
            assert [e.node_id for e in evidence] == ["n-trigger", "n-data"]
            for row in evidence:
                assert row.outcome == "DISPATCHED"
                assert row.job_id is not None
                # ARK-REQ-0328: every node's evidence is bound to the exact
                # canonical revision this execution consumed.
                assert row.revision_hash == record.bound_revision_hash
                job = session.execute(
                    select(DurableJobRecord).where(DurableJobRecord.job_id == row.job_id)
                ).scalar_one()
                assert job.lifecycle_state == "SUCCEEDED"


class TestEveryNonLogicKindDispatchesAsARealDurableJob:
    @pytest.mark.parametrize("kind", NON_LOGIC_KINDS)
    def test_kind_produces_dispatched_evidence(
        self, kind: str, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        workflow_id = f"wf-kind-{kind.lower()}"
        nodes = [node("n-trigger", "trigger")]
        edges: list = []
        if kind != "trigger":
            nodes.append(node("n-x", kind))
            edges.append(edge("e-1", "n-trigger", "n-x"))
        document = build_document(vocabulary, workflow_id, nodes, edges)
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start(f"exec-{kind.lower()}", workflow_id)
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            evidence = executor.evidence(f"exec-{kind.lower()}")
            kinds_seen = {e.kind for e in evidence}
            assert kind in kinds_seen
            for row in evidence:
                if row.kind == kind:
                    assert row.job_id is not None
                    assert row.outcome == "DISPATCHED"


class TestIfElseSwitch:
    def test_if_true_takes_the_true_edge(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-if",
            [
                node("n-trigger", "trigger"),
                node("n-if", "logic", construct="IF", parameters={"value": True}),
                node("n-true", "data"),
                node("n-false", "data"),
            ],
            [
                edge("e-1", "n-trigger", "n-if"),
                edge("e-2", "n-if", "n-true", condition="true"),
                edge("e-3", "n-if", "n-false", condition="false"),
            ],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-if", "wf-if")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            visited = {e.node_id for e in executor.evidence("exec-if")}
            assert "n-true" in visited
            assert "n-false" not in visited

    def test_switch_falls_back_to_default(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-switch",
            [
                node("n-trigger", "trigger"),
                node("n-switch", "logic", construct="SWITCH", parameters={"value": "zzz"}),
                node("n-a", "data"),
                node("n-default", "data"),
            ],
            [
                edge("e-1", "n-trigger", "n-switch"),
                edge("e-2", "n-switch", "n-a", condition="a"),
                edge("e-3", "n-switch", "n-default", condition="default"),
            ],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-switch", "wf-switch")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            visited = {e.node_id for e in executor.evidence("exec-switch")}
            assert visited == {"n-trigger", "n-switch", "n-default"}


class TestLoopIsBounded:
    def test_loop_repeats_then_exits(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-loop",
            [
                node("n-trigger", "trigger"),
                node("n-loop", "logic", construct="LOOP", parameters={"max_iterations": 3}),
                node("n-body", "data"),
                node("n-after", "data"),
            ],
            [
                edge("e-1", "n-trigger", "n-loop"),
                edge("e-2", "n-loop", "n-body", condition="continue"),
                edge("e-3", "n-body", "n-loop"),
                edge("e-4", "n-loop", "n-after", condition="exit"),
            ],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-loop", "wf-loop")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            evidence = executor.evidence("exec-loop")
            body_visits = [e for e in evidence if e.node_id == "n-body"]
            assert len(body_visits) == 3
            loop_visits = [e for e in evidence if e.node_id == "n-loop"]
            assert len(loop_visits) == 4  # 3 continues + 1 exit
            assert loop_visits[-1].outcome == "LOOP:exit(3)"


class TestParallelFansOut:
    def test_parallel_reaches_every_branch(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-parallel",
            [
                node("n-trigger", "trigger"),
                node("n-parallel", "logic", construct="PARALLEL"),
                node("n-a", "data"),
                node("n-b", "data"),
            ],
            [
                edge("e-1", "n-trigger", "n-parallel"),
                edge("e-2", "n-parallel", "n-a"),
                edge("e-3", "n-parallel", "n-b"),
            ],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-parallel", "wf-parallel")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            visited = {e.node_id for e in executor.evidence("exec-parallel")}
            assert {"n-a", "n-b"} <= visited


class TestMergeJoinsAllIncoming:
    def test_merge_waits_for_both_branches(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-merge",
            [
                node("n-trigger", "trigger"),
                node("n-parallel", "logic", construct="PARALLEL"),
                node("n-a", "data"),
                node("n-b", "data"),
                node("n-merge", "logic", construct="MERGE"),
                node("n-after", "data"),
            ],
            [
                edge("e-1", "n-trigger", "n-parallel"),
                edge("e-2", "n-parallel", "n-a"),
                edge("e-3", "n-parallel", "n-b"),
                edge("e-4", "n-a", "n-merge"),
                edge("e-5", "n-b", "n-merge"),
                edge("e-6", "n-merge", "n-after"),
            ],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-merge", "wf-merge")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            evidence = executor.evidence("exec-merge")
            merge_visits = [e for e in evidence if e.node_id == "n-merge"]
            assert len(merge_visits) == 1
            assert any(e.node_id == "n-after" for e in evidence)
