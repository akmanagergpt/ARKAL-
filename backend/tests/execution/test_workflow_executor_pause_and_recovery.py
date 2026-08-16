"""C-20 workflow executor: pause/resume constructs and terminal error paths
(Phase 17 Package 5). ARK-REQ-0328/0329/0330/0332.

Split from `test_workflow_executor.py` at the `module <= 400 logical lines`
budget - see that file's docstring. This half covers `WAIT` (pauses the whole
execution and resumes via a signal), `RETRY` (a bounded reattempt with a
distinct give-up edge), `ERROR HANDLER` (a triggered error is a terminal
move, never a return to `RUNNING`), `HUMAN APPROVAL` (ARK-REQ-0330, the
enforced policy stop), and unknown-execution refusals.

REAL INFRASTRUCTURE ONLY - see `executor_harness.py`. Every negative control
asserts the type and reason a call was refused.
"""

from __future__ import annotations

import pytest

from arkali.control.policy.policy_errors import AutomatedActorCannotApprove
from arkali.control.policy.workflow_approval import APPROVED
from arkali.execution.workflow.execution_errors import (
    ApprovalNotEnforced,
    NoPendingApproval,
    UnknownWorkflowExecution,
)
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


def _linear_document(vocabulary: GraphVocabulary, workflow_id: str = "wf-exec"):
    return build_document(
        vocabulary, workflow_id,
        [node("n-trigger", "trigger"), node("n-data", "data")],
        [edge("e-1", "n-trigger", "n-data")],
    )


class TestWaitPausesForASignal:
    def test_wait_pauses_then_resumes_via_signal(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-wait",
            [
                node("n-trigger", "trigger"),
                node("n-wait", "logic", construct="WAIT"),
                node("n-after", "data"),
            ],
            [edge("e-1", "n-trigger", "n-wait"), edge("e-2", "n-wait", "n-after")],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-wait", "wf-wait")
            session.commit()
            assert record.lifecycle_state == "WAITING_SIGNAL"
        with reopen.session() as (executor, _store, session):
            record = executor.resume_after_signal("exec-wait")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            visited = {e.node_id for e in executor.evidence("exec-wait")}
            assert "n-after" in visited


class TestRetryIsBounded:
    def test_retry_exhausts_then_takes_the_exhausted_edge(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-retry",
            [
                node("n-trigger", "trigger"),
                node(
                    "n-retry", "logic", construct="RETRY",
                    parameters={"succeeded": False, "max_attempts": 2},
                ),
                node("n-gave-up", "data"),
            ],
            [
                edge("e-1", "n-trigger", "n-retry"),
                edge("e-2", "n-retry", "n-retry", condition="retry"),
                edge("e-3", "n-retry", "n-gave-up", condition="exhausted"),
            ],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-retry", "wf-retry")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            evidence = executor.evidence("exec-retry")
            retry_visits = [e for e in evidence if e.node_id == "n-retry"]
            assert len(retry_visits) == 3  # 2 retries + 1 exhausted
            assert retry_visits[-1].outcome == "RETRY:exhausted(2)"
            assert any(e.node_id == "n-gave-up" for e in evidence)


class TestErrorHandler:
    def test_passthrough_when_not_triggered(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-errok",
            [
                node("n-trigger", "trigger"),
                node("n-eh", "logic", construct="ERROR HANDLER", parameters={"triggered": False}),
                node("n-after", "data"),
            ],
            [edge("e-1", "n-trigger", "n-eh"), edge("e-2", "n-eh", "n-after", condition="ok")],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-errok", "wf-errok")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"

    def test_triggered_and_recoverable_ends_cancelled(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-errcancel",
            [
                node("n-trigger", "trigger"),
                node(
                    "n-eh", "logic", construct="ERROR HANDLER",
                    parameters={"triggered": True, "recoverable": True},
                ),
            ],
            [edge("e-1", "n-trigger", "n-eh")],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-errcancel", "wf-errcancel")
            session.commit()
            assert record.lifecycle_state == "CANCELLED"

    def test_triggered_and_unrecoverable_ends_failed(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        document = build_document(
            vocabulary, "wf-errfail",
            [
                node("n-trigger", "trigger"),
                node(
                    "n-eh", "logic", construct="ERROR HANDLER",
                    parameters={"triggered": True, "recoverable": False},
                ),
            ],
            [edge("e-1", "n-trigger", "n-eh")],
        )
        with reopen.session() as (executor, store, session):
            publish(store, document)
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-errfail", "wf-errfail")
            session.commit()
            assert record.lifecycle_state == "FAILED"


class TestHumanApprovalIsAnEnforcedPolicyStop:
    """ARK-REQ-0330."""

    def _approval_document(self, vocabulary: GraphVocabulary):
        return build_document(
            vocabulary, "wf-approval",
            [
                node("n-trigger", "trigger"),
                node("n-approval", "logic", construct="HUMAN APPROVAL"),
                node("n-after", "data"),
            ],
            [edge("e-1", "n-trigger", "n-approval"), edge("e-2", "n-approval", "n-after")],
        )

    def test_pauses_at_waiting_approval(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (executor, store, session):
            publish(store, self._approval_document(vocabulary))
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-approval-1", "wf-approval")
            session.commit()
            assert record.lifecycle_state == "WAITING_APPROVAL"
            assert record.pending_approval_node_id == "n-approval"

    def test_the_workflow_actor_cannot_approve_itself(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (executor, store, session):
            publish(store, self._approval_document(vocabulary))
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-approval-2", "wf-approval")
            session.commit()
        with reopen.session() as (executor, _store, _session):
            with pytest.raises(AutomatedActorCannotApprove):
                executor.approve(
                    "exec-approval-2", node_id="n-approval", actor="workflow",
                    decision=APPROVED, approved_revision_hash=record.bound_revision_hash,
                )

    def test_a_stale_revision_hash_is_refused(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (executor, store, session):
            publish(store, self._approval_document(vocabulary))
            session.commit()
        with reopen.session() as (executor, _store, session):
            executor.start("exec-approval-3", "wf-approval")
            session.commit()
        with reopen.session() as (executor, _store, session):
            with pytest.raises(ApprovalNotEnforced):
                executor.approve(
                    "exec-approval-3", node_id="n-approval", actor="human",
                    decision=APPROVED, approved_revision_hash="sha256:" + "0" * 64,
                )

    def test_a_rejection_is_refused_and_stays_waiting(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (executor, store, session):
            publish(store, self._approval_document(vocabulary))
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-approval-4", "wf-approval")
            session.commit()
            bound = record.bound_revision_hash
        with reopen.session() as (executor, _store, session):
            with pytest.raises(ApprovalNotEnforced):
                executor.approve(
                    "exec-approval-4", node_id="n-approval", actor="human",
                    decision="REJECTED", approved_revision_hash=bound,
                )
        with reopen.session() as (executor, _store, _session):
            assert executor.require("exec-approval-4").lifecycle_state == "WAITING_APPROVAL"

    def test_a_real_human_approval_advances_and_completes(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (executor, store, session):
            publish(store, self._approval_document(vocabulary))
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-approval-5", "wf-approval")
            session.commit()
            bound = record.bound_revision_hash
        with reopen.session() as (executor, _store, session):
            record = executor.approve(
                "exec-approval-5", node_id="n-approval", actor="human",
                decision=APPROVED, approved_revision_hash=bound,
            )
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            visited = {e.node_id for e in executor.evidence("exec-approval-5")}
            assert "n-after" in visited

    def test_approving_without_a_pending_approval_is_refused(
        self, reopen: ExecutorReopener, vocabulary: GraphVocabulary
    ) -> None:
        with reopen.session() as (executor, store, session):
            publish(store, _linear_document(vocabulary, "wf-noapproval"))
            session.commit()
        with reopen.session() as (executor, _store, session):
            record = executor.start("exec-noapproval", "wf-noapproval")
            session.commit()
            assert record.lifecycle_state == "SUCCEEDED"
        with reopen.session() as (executor, _store, _session):
            with pytest.raises(NoPendingApproval):
                executor.approve(
                    "exec-noapproval", node_id="n-data", actor="human",
                    decision=APPROVED, approved_revision_hash=record.bound_revision_hash,
                )


class TestUnknownExecutionRefusals:
    def test_require_raises_unknown_execution(self, reopen: ExecutorReopener) -> None:
        with reopen.session() as (executor, _store, _session):
            with pytest.raises(UnknownWorkflowExecution, match="ghost"):
                executor.require("ghost")
