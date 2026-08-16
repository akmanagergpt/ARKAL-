"""C-20 workflow API request/response contracts.

Owner: `surfaces.command`. Phase 17 Package 6.

SEPARATE FROM `contracts.py` BY DECOMPOSITION, NOT BY ACCIDENT.
`contracts.py` already carries 10 of the 20 `max_public_symbols_per_module`
budget for the Project/Job shapes; the eleven C-20 shapes below would have
taken it to 21. ADR-0008 makes decomposition the answer to a budget rather
than an exception - the `workflow_error_mapping.py` split, applied a second
time in the same package.

NO SECOND DOMAIN MODEL. These are transport shapes, projected field-for-field
from `execution.workflow`'s real value objects and records - this module
imports none of them (see `workflow.py`'s module docstring for why) and
declares no graph-validity rule, no revision derivation and no execution
semantics of its own.
"""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from arkali.surfaces.command.contracts import TransportModel


class WorkflowNodeShape(BaseModel):
    """One C-20 node, over the wire. Field-for-field with
    `execution.workflow.graph_model.WorkflowNode` - projected, not a second
    domain model: this surface never validates a construct against the
    canonical vocabulary itself, `WorkflowGraphDocument.build` does.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=32)
    control_construct: str | None = Field(default=None, max_length=32)
    label: str = Field(default="untitled", max_length=200)
    parameters: dict[str, object] = Field(default_factory=dict)
    position_x: float = 0.0
    position_y: float = 0.0


class WorkflowEdgeShape(BaseModel):
    """One C-20 edge, over the wire."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    edge_id: str = Field(min_length=1, max_length=64)
    source_node_id: str = Field(min_length=1, max_length=64)
    target_node_id: str = Field(min_length=1, max_length=64)
    condition: str | None = Field(default=None, max_length=64)


class PublishWorkflowRevisionRequest(BaseModel):
    """A declared graph plus the author's semver bump. `WorkflowGraphStore`
    derives the revision number and recomputes the content hash; neither is
    accepted from the caller."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    nodes: tuple[WorkflowNodeShape, ...] = ()
    edges: tuple[WorkflowEdgeShape, ...] = ()
    semver_bump: str = Field(default="PATCH", max_length=8)


class WorkflowRevisionResponse(TransportModel):
    workflow_id: str
    revision_number: int
    semver: str
    revision_hash: str
    created_at: dt.datetime


class WorkflowRevisionDetailResponse(WorkflowRevisionResponse):
    nodes: tuple[WorkflowNodeShape, ...] = ()
    edges: tuple[WorkflowEdgeShape, ...] = ()


class WorkflowRevisionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revisions: tuple[WorkflowRevisionResponse, ...] = ()


class StartExecutionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str = Field(min_length=1, max_length=64)
    revision_number: int | None = None


class ApproveExecutionRequest(BaseModel):
    """A submitted HUMAN APPROVAL decision.

    `approved_revision_hash` is the revision the human's decision was based
    on; `WorkflowExecutor.approve` refuses it unless it matches the
    execution's bound revision - ARK-REQ-0330's stale-approval refusal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str = Field(min_length=1, max_length=64)
    actor: str = Field(min_length=1, max_length=200)
    decision: str = Field(min_length=1, max_length=32)
    approved_revision_hash: str = Field(min_length=1, max_length=128)


class WorkflowNodeExecutionResponse(TransportModel):
    sequence: int
    node_id: str
    kind: str
    control_construct: str | None
    revision_hash: str
    outcome: str
    job_id: str | None
    recorded_at: dt.datetime


class WorkflowExecutionResponse(TransportModel):
    execution_id: str
    workflow_id: str
    revision_number: int
    bound_revision_hash: str
    lifecycle_state: str
    pending_approval_node_id: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class WorkflowExecutionDetailResponse(WorkflowExecutionResponse):
    evidence: tuple[WorkflowNodeExecutionResponse, ...] = ()
