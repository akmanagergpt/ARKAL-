"""C-20 workflow execution state and per-node execution evidence.

Owner: `execution.workflow`.

ONE EXECUTION, ONE ROW, MUTABLE BY THE MACHINE. Unlike a graph revision
(immutable once published), a `WorkflowExecutionRecord` tracks a running
process and is expected to change: `lifecycle_state` follows the canonical
`WorkflowExecution` machine (Phase 3, `workflow_execution_state_machine.py`),
`frontier` is the pending-node queue a resumable walk needs to survive a
pause or a process restart, `loop_counts`/`merge_arrivals` are the bounded
per-node bookkeeping `LOOP`/`RETRY` and `MERGE` need. None of this is a
second lifecycle authority: every state written here is a value the machine
already accepted via `evaluate`, never chosen by this module.

NODE EXECUTION EVIDENCE IS APPEND-ONLY. `WorkflowNodeExecutionRecord` is one
row per node visit - `sequence` lets the same node id appear more than once
(a `LOOP` body visited three times is three rows), derived from stored rows
the same way `JobCheckpointRecord.sequence` is. Every row carries the
`revision_hash` the execution was bound to at the moment that node ran - the
per-node proof ARK-REQ-0328 needs that the executor consumed the canonical
revision, node by node, not merely once at the start.

ENGINE-NEUTRAL (ARK-REQ-0012). `String`, `Integer`, `DateTime` and `JSON`
only.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from arkali.execution.workflow.records import utc_now
from arkali.kernel.persistence.base import PersistenceBase

EXECUTION_TABLE: Final[str] = "workflow_execution"
NODE_EXECUTION_TABLE: Final[str] = "workflow_node_execution"

IDENTITY_LENGTH: Final[int] = 64
STATE_LENGTH: Final[int] = 32
HASH_LENGTH: Final[int] = 128
KIND_LENGTH: Final[int] = 32
OUTCOME_LENGTH: Final[int] = 200


class WorkflowExecutionRecord(PersistenceBase):
    """One execution of one workflow graph revision."""

    __tablename__ = EXECUTION_TABLE

    execution_id: Mapped[str] = mapped_column(String(IDENTITY_LENGTH), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(IDENTITY_LENGTH), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    #: `WorkflowGraphDocument.content_hash` at the revision this execution is
    #: bound to. Re-verified against the store on every step, never trusted
    #: as a standing fact.
    bound_revision_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    #: A state the canonical `WorkflowExecution` machine already accepted.
    lifecycle_state: Mapped[str] = mapped_column(String(STATE_LENGTH), nullable=False)
    #: Pending node ids, in visit order. Empty once the walk is exhausted.
    frontier: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    #: `LOOP`/`RETRY` node id -> iterations taken so far.
    loop_counts: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False, default=dict)
    #: `MERGE` node id -> source node ids that have already arrived.
    merge_arrivals: Mapped[dict[str, list[str]]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    #: Set only while `WAITING_APPROVAL`; names the node the approval must
    #: match. `NoPendingApproval` refuses an approval that names anything else.
    pending_approval_node_id: Mapped[str | None] = mapped_column(
        String(IDENTITY_LENGTH), nullable=True
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    node_executions: Mapped[list[WorkflowNodeExecutionRecord]] = relationship(
        back_populates="execution", cascade="save-update"
    )


class WorkflowNodeExecutionRecord(PersistenceBase):
    """One node visit's execution evidence. Append-only."""

    __tablename__ = NODE_EXECUTION_TABLE

    execution_id: Mapped[str] = mapped_column(
        String(IDENTITY_LENGTH),
        ForeignKey(f"{EXECUTION_TABLE}.execution_id"),
        primary_key=True,
    )
    #: 1-based, derived from stored rows - the `JobCheckpointRecord.sequence`
    #: idiom, so a `LOOP` body visited N times leaves N distinct rows.
    sequence: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[str] = mapped_column(String(IDENTITY_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(KIND_LENGTH), nullable=False)
    control_construct: Mapped[str | None] = mapped_column(String(KIND_LENGTH), nullable=True)
    #: The canonical revision hash bound at the moment THIS node ran -
    #: per-node proof of ARK-REQ-0328, not a single execution-level claim.
    revision_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    outcome: Mapped[str] = mapped_column(String(OUTCOME_LENGTH), nullable=False)
    #: The durable job this node ran as, for a node kind that dispatches one.
    #: `None` for a pure control-flow evaluation (a `logic` node's construct).
    job_id: Mapped[str | None] = mapped_column(String(IDENTITY_LENGTH), nullable=True)
    recorded_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    execution: Mapped[WorkflowExecutionRecord] = relationship(back_populates="node_executions")
