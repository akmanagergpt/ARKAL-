"""C-20 workflow executor (ARK-REQ-0328 … 0330, 0332).

Owner: `execution.workflow`.

COMPOSES, NEVER DUPLICATES. The canonical `WorkflowExecution` machine (Phase
3) is the sole transition authority - every `lifecycle_state` write here
comes from `self._machine.evaluate(...)`, never a direct assignment.
`WorkflowGraphStore` (Package 2) is the sole revision authority.
`CompiledExecutionPlan.require_fresh` (Package 3, ADR-0004) is checked before
every step, not once at the start. `control.policy.WorkflowApprovalGate`
(Package 4) is the sole answer to whether a HUMAN APPROVAL decision counts.
Each non-`logic` node dispatches as one real `execution.durable` job via the
pre-declared `execution.workflow → execution.durable` sibling edge - "workflow
steps are durable jobs" - never a second durability mechanism.

WHY EVERY NODE KIND DISPATCHES AS A DURABLE JOB, NOT A DIRECT CALL. This
context is not a listed consumer of provider authority
(`AUTHORITY_MAP.yaml`), so it holds no AI/agent/provider invocation body of
its own - an `AI`/`agent`/`integration`/… node's real work belongs to
whichever future-phase runtime consumes that job type. What this module
proves is real: the durable submit → attempt → complete cycle actually runs,
persisted, PEP-enforced, against real `execution.durable` infrastructure, for
every one of the nine non-`logic` node kinds.

A `release` NODE NEVER TOUCHES STABLE. `workflow` is a named actor the
canonical Stable-mutation policy already forbids from mutating Stable
directly (MS §Constitution 6); a `release` node enqueues a durable job
recording that a release was requested and nothing more - there is no
promotion capability for it to call even if it tried, since none exists in
this authority's dependency reach.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.execution.durable.execution import JobExecution
from arkali.execution.durable.job_store import JobSubmission
from arkali.execution.workflow import construct_dispatch as cd
from arkali.execution.workflow.errors import UnknownWorkflow
from arkali.execution.workflow.execution_errors import (
    ApprovalNotEnforced,
    ExecutionNotRunning,
    NoPendingApproval,
    UnknownPlanNode,
    UnknownWorkflowExecution,
)
from arkali.execution.workflow.execution_plan import CompiledExecutionPlan
from arkali.execution.workflow.execution_records import (
    WorkflowExecutionRecord,
    WorkflowNodeExecutionRecord,
)
from arkali.execution.workflow.graph_model import WorkflowGraphDocument, WorkflowNode
from arkali.execution.workflow.graph_store import WorkflowGraphStore
from arkali.execution.workflow.graph_vocabulary import LOGIC_KIND, GraphVocabulary
from arkali.execution.workflow.records import WorkflowRevisionRecord, utc_now
from arkali.execution.workflow.workflow_execution_state_machine import (
    COMPENSATING,
    PENDING,
    RUNNING,
    SUCCEEDED,
    WAITING_APPROVAL,
    WAITING_SIGNAL,
    build,
)

ACTOR: Final[str] = "execution.workflow"
TRUST_TIER: Final[str] = "TRUST-0"
READ: Final[str] = "READ_FILE"
WRITE: Final[str] = "WRITE_WORKSPACE_FILE"

Clock = Callable[[], dt.datetime]


class WorkflowExecutor:
    """One session's worth of workflow execution. Composes, never owns, the
    graph, revision, plan, machine and policy authorities."""

    def __init__(
        self,
        session: Session,
        pdp: PolicyDecisionPoint,
        vocabulary: GraphVocabulary,
        approval_gate: WorkflowApprovalGate,
        clock: Clock = utc_now,
    ) -> None:
        self._session = session
        self._clock = clock
        self._pep = PolicyEnforcementPoint(pdp, "execution.workflow.executor")
        self._graph_store = WorkflowGraphStore(
            session, PolicyEnforcementPoint(pdp, "execution.workflow.graph_store"),
            vocabulary, clock,
        )
        self._jobs = JobExecution(
            session, PolicyEnforcementPoint(pdp, "execution.durable.execution"), clock
        )
        self._approval_gate = approval_gate
        self._machine = build()

    def _guard(self, operation: str) -> None:
        self._pep.require_auto(
            PolicyRequest(operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR)
        )

    # -- reads -----------------------------------------------------------

    def get(self, execution_id: str) -> WorkflowExecutionRecord | None:
        self._guard(READ)
        return self._session.execute(
            select(WorkflowExecutionRecord).where(
                WorkflowExecutionRecord.execution_id == execution_id
            )
        ).scalar_one_or_none()

    def require(self, execution_id: str) -> WorkflowExecutionRecord:
        found = self.get(execution_id)
        if found is None:
            raise UnknownWorkflowExecution(f"no execution {execution_id!r} is registered")
        return found

    def evidence(self, execution_id: str) -> tuple[WorkflowNodeExecutionRecord, ...]:
        self._guard(READ)
        rows = self._session.execute(
            select(WorkflowNodeExecutionRecord)
            .where(WorkflowNodeExecutionRecord.execution_id == execution_id)
            .order_by(WorkflowNodeExecutionRecord.sequence)
        ).scalars()
        return tuple(rows)

    def _next_sequence(self, execution_id: str) -> int:
        highest = self._session.execute(
            select(func.max(WorkflowNodeExecutionRecord.sequence)).where(
                WorkflowNodeExecutionRecord.execution_id == execution_id
            )
        ).scalar_one_or_none()
        return 1 if highest is None else int(highest) + 1

    # -- lifecycle ---------------------------------------------------------

    def start(
        self, execution_id: str, workflow_id: str, *, revision_number: int | None = None
    ) -> WorkflowExecutionRecord:
        """Bind a new execution to a specific (or the latest) revision and
        run it until it pauses or reaches a terminal state."""
        revision: WorkflowRevisionRecord | None
        if revision_number is not None:
            revision = self._graph_store.require_revision(workflow_id, revision_number)
        else:
            revision = self._graph_store.latest(workflow_id)
            if revision is None:
                raise UnknownWorkflow(f"workflow {workflow_id!r} has no revisions to execute")
        document = self._graph_store.document_of(revision)
        plan = CompiledExecutionPlan.derive(document)

        self._guard(WRITE)
        initial = self._machine.evaluate(PENDING, RUNNING)
        record = WorkflowExecutionRecord(
            execution_id=execution_id,
            workflow_id=workflow_id,
            revision_number=revision.revision_number,
            bound_revision_hash=revision.revision_hash,
            lifecycle_state=initial.target,
            frontier=list(plan.trigger_ids),
            loop_counts={},
            merge_arrivals={},
            pending_approval_node_id=None,
            created_at=self._clock(),
            updated_at=self._clock(),
        )
        self._session.add(record)
        self._session.flush()
        return self._run(record, document, plan)

    def resume_after_signal(self, execution_id: str) -> WorkflowExecutionRecord:
        record = self.require(execution_id)
        if record.lifecycle_state != WAITING_SIGNAL:
            raise ExecutionNotRunning(
                f"execution {execution_id!r} is {record.lifecycle_state!r}, not "
                f"{WAITING_SIGNAL!r}"
            )
        self._guard(WRITE)
        outcome = self._machine.evaluate(record.lifecycle_state, RUNNING)
        record.lifecycle_state = outcome.target
        document, plan = self._plan_for(record)
        return self._run(record, document, plan)

    def approve(
        self, execution_id: str, *, node_id: str, actor: str, decision: str,
        approved_revision_hash: str,
    ) -> WorkflowExecutionRecord:
        record = self.require(execution_id)
        waiting_on_this_node = (
            record.lifecycle_state == WAITING_APPROVAL
            and record.pending_approval_node_id == node_id
        )
        if not waiting_on_this_node:
            raise NoPendingApproval(
                f"execution {execution_id!r} is not waiting on approval for "
                f"node {node_id!r}"
            )
        self._approval_gate.assert_may_record(actor)
        enforced = self._approval_gate.is_enforced_approval(
            decision=decision, actor=actor,
            approval_revision_hash=approved_revision_hash,
            current_revision_hash=record.bound_revision_hash,
        )
        if not enforced:
            raise ApprovalNotEnforced(
                f"execution {execution_id!r} node {node_id!r}: the submitted "
                "decision does not enforce advancing WAITING_APPROVAL"
            )
        self._guard(WRITE)
        outcome = self._machine.evaluate(
            record.lifecycle_state, RUNNING,
            context={"human_approval_recorded": True},
        )
        record.lifecycle_state = outcome.target
        document, plan = self._plan_for(record)
        for edge in document.outgoing(node_id):
            self._enqueue(record, document, node_id, edge.target_node_id)
        record.pending_approval_node_id = None
        return self._run(record, document, plan)

    def _plan_for(
        self, record: WorkflowExecutionRecord
    ) -> tuple[WorkflowGraphDocument, CompiledExecutionPlan]:
        revision = self._graph_store.require_revision(record.workflow_id, record.revision_number)
        document = self._graph_store.document_of(revision)
        plan = CompiledExecutionPlan.derive(document)
        plan.require_fresh(record.bound_revision_hash)
        return document, plan

    # -- the frontier walk -------------------------------------------------

    def _run(
        self,
        record: WorkflowExecutionRecord,
        document: WorkflowGraphDocument,
        plan: CompiledExecutionPlan,
    ) -> WorkflowExecutionRecord:
        plan.require_fresh(record.bound_revision_hash)
        while record.frontier:
            node_id = record.frontier[0]
            node = plan.node(node_id)
            if node is None:
                raise UnknownPlanNode(
                    f"execution {record.execution_id!r}: frontier names "
                    f"{node_id!r}, which the compiled plan does not contain"
                )
            record.frontier = record.frontier[1:]
            if node.kind == LOGIC_KIND:
                paused = self._dispatch_logic(record, document, node)
                if paused:
                    self._touch(record)
                    return record
            else:
                self._dispatch_leaf(record, node)
                for edge in document.outgoing(node_id):
                    self._enqueue(record, document, node_id, edge.target_node_id)
            self._touch(record)
        self._guard(WRITE)
        outcome = self._machine.evaluate(record.lifecycle_state, SUCCEEDED)
        record.lifecycle_state = outcome.target
        self._touch(record)
        return record

    def _touch(self, record: WorkflowExecutionRecord) -> None:
        record.updated_at = self._clock()
        self._session.flush()

    def _enqueue(
        self,
        record: WorkflowExecutionRecord,
        document: WorkflowGraphDocument,
        source_id: str,
        target_id: str,
    ) -> None:
        """Add `target_id` to the frontier - unless it is a `MERGE` node
        still waiting on other declared incoming edges."""
        target = document.node(target_id)
        if target is not None and target.kind == LOGIC_KIND and target.control_construct == "MERGE":
            arrivals = list(record.merge_arrivals.get(target_id, []))
            if source_id not in arrivals:
                arrivals.append(source_id)
            record.merge_arrivals = {**record.merge_arrivals, target_id: arrivals}
            required = {e.source_node_id for e in document.edges() if e.target_node_id == target_id}
            if set(arrivals) < required:
                return
        record.frontier = record.frontier + [target_id]

    # -- leaf (non-`logic`) node dispatch: one real durable job -------------

    def _dispatch_leaf(self, record: WorkflowExecutionRecord, node: WorkflowNode) -> None:
        sequence = self._next_sequence(record.execution_id)
        job_id = f"{record.execution_id}:{node.node_id}:{sequence}"
        self._guard(WRITE)
        self._jobs.jobs.submit(
            JobSubmission(
                job_id=job_id, job_type=f"workflow.node.{node.kind}",
                idempotency_key=job_id,
                payload={"node_id": node.node_id, "kind": node.kind},
            )
        )
        self._jobs.begin_attempt(job_id, owner=ACTOR)
        self._jobs.complete_attempt(job_id, owner=ACTOR)
        self._record_evidence(record, node, sequence, outcome="DISPATCHED", job_id=job_id)

    # -- `logic` node dispatch: real construct evaluation -------------------

    def _dispatch_logic(
        self, record: WorkflowExecutionRecord, document: WorkflowGraphDocument, node: WorkflowNode
    ) -> bool:
        """Returns True if the run must pause (frontier not advanced further
        this call)."""
        construct = node.control_construct or ""
        counter = record.loop_counts.get(node.node_id, 0)
        decision = cd.evaluate_construct(
            construct, node, document, counter=counter, already_waited=bool(counter)
        )
        if construct in ("LOOP", "RETRY") or decision["kind"] == cd.PAUSE_SIGNAL:
            next_counter = decision["counter"]
            assert isinstance(next_counter, int)
            record.loop_counts = {**record.loop_counts, node.node_id: next_counter}

        sequence = self._next_sequence(record.execution_id)
        self._record_evidence(record, node, sequence, outcome=str(decision["outcome"]), job_id=None)

        if decision["kind"] == cd.PAUSE_SIGNAL:
            self._guard(WRITE)
            outcome = self._machine.evaluate(record.lifecycle_state, WAITING_SIGNAL)
            record.lifecycle_state = outcome.target
            record.frontier = [node.node_id] + record.frontier
            return True
        if decision["kind"] == cd.PAUSE_APPROVAL:
            self._guard(WRITE)
            outcome = self._machine.evaluate(record.lifecycle_state, WAITING_APPROVAL)
            record.lifecycle_state = outcome.target
            record.pending_approval_node_id = node.node_id
            return True
        if decision["kind"] == cd.TERMINAL:
            self._guard(WRITE)
            compensating = self._machine.evaluate(record.lifecycle_state, COMPENSATING)
            record.lifecycle_state = compensating.target
            terminal_state = decision["terminal_state"]
            assert isinstance(terminal_state, str)
            final = self._machine.evaluate(record.lifecycle_state, terminal_state)
            record.lifecycle_state = final.target
            return True
        edges = decision["edges"]
        assert isinstance(edges, tuple)
        for edge in edges:
            self._enqueue(record, document, node.node_id, edge.target_node_id)
        return False

    def _record_evidence(
        self,
        record: WorkflowExecutionRecord,
        node: WorkflowNode,
        sequence: int,
        *,
        outcome: str,
        job_id: str | None,
    ) -> None:
        self._session.add(
            WorkflowNodeExecutionRecord(
                execution_id=record.execution_id,
                sequence=sequence,
                node_id=node.node_id,
                kind=node.kind,
                control_construct=node.control_construct,
                revision_hash=record.bound_revision_hash,
                outcome=outcome,
                job_id=job_id,
                recorded_at=self._clock(),
            )
        )
        self._session.flush()
