"""The C-20 workflow surface — graph revisions and executions.

Owner: `surfaces.command`. Phase 17 Package 6.

NO STATIC IMPORT OF `execution.workflow`, ANYWHERE IN THIS MODULE. Composing
`execution.workflow.executor` (rank 3) already reaches, through the
pre-declared `execution.workflow → execution.durable` sibling edge,
`execution.durable → control.policy → kernel.contracts` - a real, accepted,
four-hop chain. Adding `surfaces.command` (rank 6) as a static importer in
front of it measures as a fifth hop and breaches
`max_orchestration_depth` (4) - a genuine budget hit, not a paperwork one.
ADR-0008 makes decomposition the answer: every collaborator this module
touches is typed as a structural `Protocol` (`GraphStoreLike`,
`ExecutorLike`) and received as an already-built factory, the same
`WorkspaceTarget` idiom Phase 16 used to avoid extending an already-saturated
chain. The REAL `WorkflowGraphStore`/`WorkflowExecutor` objects still do the
work; they are constructed by the composition root that calls
`build_workflow_router` (a script or a test fixture, outside
`backend/arkali/` and outside the measured graph), never by this module.

DELEGATION, NOT DATA ACCESS. Every route calls the injected store or executor
Protocol. This module issues no query, builds no statement and touches no
mapped column, and validates no graph itself - `document_builder` (also
injected) is the sole point where a declared graph becomes a real,
validated `WorkflowGraphDocument`.

REVISION IDENTITY IS NEVER ACCEPTED FROM THE CALLER. `PublishWorkflowRevisionRequest`
carries only the declared graph and the author's semver bump; `revision_number`
and `revision_hash` are always derived by the store, never trusted from the
wire - the same discipline Phase 5's routes already apply to a Project's
lifecycle state.

BROWSER_SLICE AS OF PACKAGE 7. The Studio UI (`frontend/src/features/workflow`)
calls every route below through `ArkaliApiClient`, added in the same commit
that flips this tag - `test_contract_drift.py` requires every `BROWSER_SLICE`
route to already be called, and refuses a `BACKEND_ONLY` route the client
calls, so the two edits are inseparable.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator
from typing import Any, Protocol

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from arkali.surfaces.command.contracts import BROWSER_SLICE
from arkali.surfaces.command.workflow_contracts import (
    ApproveExecutionRequest,
    PublishWorkflowRevisionRequest,
    StartExecutionRequest,
    WorkflowEdgeShape,
    WorkflowExecutionDetailResponse,
    WorkflowExecutionResponse,
    WorkflowNodeExecutionResponse,
    WorkflowNodeShape,
    WorkflowRevisionDetailResponse,
    WorkflowRevisionListResponse,
    WorkflowRevisionResponse,
)

SessionScope = Callable[[], Iterator[Session]]
Guard = Callable[[str], None]
Refuse = Callable[[Exception], Exception]


class _RevisionLike(Protocol):
    workflow_id: str
    revision_number: int
    semver: str
    revision_hash: str
    created_at: dt.datetime


class _DocumentLike(Protocol):
    def nodes(self) -> Any: ...
    def edges(self) -> Any: ...


class _ExecutionLike(Protocol):
    execution_id: str
    workflow_id: str
    revision_number: int
    bound_revision_hash: str
    lifecycle_state: str
    pending_approval_node_id: str | None
    created_at: dt.datetime
    updated_at: dt.datetime


class _NodeExecutionLike(Protocol):
    sequence: int
    node_id: str
    kind: str
    control_construct: str | None
    revision_hash: str
    outcome: str
    job_id: str | None
    recorded_at: dt.datetime


class GraphStoreLike(Protocol):
    def publish(self, document: Any, *, semver_bump: str) -> _RevisionLike: ...
    def latest(self, workflow_id: str) -> _RevisionLike | None: ...
    def require_workflow(self, workflow_id: str) -> Any: ...
    def require_revision(self, workflow_id: str, revision_number: int) -> _RevisionLike: ...
    def history(self, workflow_id: str) -> tuple[_RevisionLike, ...]: ...
    def document_of(self, record: _RevisionLike) -> _DocumentLike: ...


class ExecutorLike(Protocol):
    def start(
        self, execution_id: str, workflow_id: str, *, revision_number: int | None = None
    ) -> _ExecutionLike: ...
    def require(self, execution_id: str) -> _ExecutionLike: ...
    def evidence(self, execution_id: str) -> tuple[_NodeExecutionLike, ...]: ...
    def resume_after_signal(self, execution_id: str) -> _ExecutionLike: ...
    def approve(
        self, execution_id: str, *, node_id: str, actor: str, decision: str,
        approved_revision_hash: str,
    ) -> _ExecutionLike: ...


#: Builds a real, validated canonical document from plain data - never from a
#: `surfaces.command` type, so the composition root that implements this
#: needs no import in either direction.
DocumentBuilder = Callable[[str, list[dict[str, Any]], list[dict[str, Any]]], Any]
GraphStoreFactory = Callable[[Session], GraphStoreLike]
ExecutorFactory = Callable[[Session], ExecutorLike]


def _revision_response(record: _RevisionLike) -> WorkflowRevisionResponse:
    return WorkflowRevisionResponse(
        workflow_id=record.workflow_id,
        revision_number=record.revision_number,
        semver=record.semver,
        revision_hash=record.revision_hash,
        created_at=record.created_at,
    )


def _revision_detail(
    record: _RevisionLike, document: _DocumentLike
) -> WorkflowRevisionDetailResponse:
    return WorkflowRevisionDetailResponse(
        **_revision_response(record).model_dump(),
        nodes=tuple(
            WorkflowNodeShape(
                node_id=n.node_id, kind=n.kind, control_construct=n.control_construct,
                label=n.label, parameters=n.parameters,
                position_x=n.position_x, position_y=n.position_y,
            )
            for n in document.nodes()
        ),
        edges=tuple(
            WorkflowEdgeShape(
                edge_id=e.edge_id, source_node_id=e.source_node_id,
                target_node_id=e.target_node_id, condition=e.condition,
            )
            for e in document.edges()
        ),
    )


def _execution_response(record: _ExecutionLike) -> WorkflowExecutionResponse:
    return WorkflowExecutionResponse(
        execution_id=record.execution_id,
        workflow_id=record.workflow_id,
        revision_number=record.revision_number,
        bound_revision_hash=record.bound_revision_hash,
        lifecycle_state=record.lifecycle_state,
        pending_approval_node_id=record.pending_approval_node_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _execution_detail(
    record: _ExecutionLike, evidence: tuple[_NodeExecutionLike, ...]
) -> WorkflowExecutionDetailResponse:
    return WorkflowExecutionDetailResponse(
        **_execution_response(record).model_dump(),
        evidence=tuple(
            WorkflowNodeExecutionResponse(
                sequence=e.sequence, node_id=e.node_id, kind=e.kind,
                control_construct=e.control_construct, revision_hash=e.revision_hash,
                outcome=e.outcome, job_id=e.job_id, recorded_at=e.recorded_at,
            )
            for e in evidence
        ),
    )


def build_workflow_router(
    session_scope: SessionScope,
    guard: Guard,
    refuse: Refuse,
    document_builder: DocumentBuilder,
    graph_store_factory: GraphStoreFactory,
    executor_factory: ExecutorFactory,
) -> APIRouter:
    """The C-20 workflow routes, over collaborators the composition root
    supplies - never constructed here. See the module docstring for why."""
    router = APIRouter(prefix="/api", tags=[BROWSER_SLICE])

    @router.post(
        "/workflows/{workflow_id}/revisions",
        response_model=WorkflowRevisionDetailResponse,
        status_code=201,
    )
    def publish_revision(
        workflow_id: str,
        body: PublishWorkflowRevisionRequest,
        session: Session = Depends(session_scope),
    ) -> WorkflowRevisionDetailResponse:
        guard("WRITE_WORKSPACE_FILE")
        store = graph_store_factory(session)
        try:
            document = document_builder(
                workflow_id,
                [n.model_dump() for n in body.nodes],
                [e.model_dump() for e in body.edges],
            )
            record = store.publish(document, semver_bump=body.semver_bump)
        except Exception as error:
            raise refuse(error) from error
        return _revision_detail(record, document)

    @router.get("/workflows/{workflow_id}", response_model=WorkflowRevisionDetailResponse)
    def get_latest_revision(
        workflow_id: str, session: Session = Depends(session_scope)
    ) -> WorkflowRevisionDetailResponse:
        guard("READ_FILE")
        store = graph_store_factory(session)
        try:
            store.require_workflow(workflow_id)
            record = store.latest(workflow_id) or store.require_revision(workflow_id, 1)
            document = store.document_of(record)
        except Exception as error:
            raise refuse(error) from error
        return _revision_detail(record, document)

    @router.get(
        "/workflows/{workflow_id}/revisions",
        response_model=WorkflowRevisionListResponse,
    )
    def list_revisions(
        workflow_id: str, session: Session = Depends(session_scope)
    ) -> WorkflowRevisionListResponse:
        guard("READ_FILE")
        store = graph_store_factory(session)
        try:
            history = store.history(workflow_id)
        except Exception as error:
            raise refuse(error) from error
        return WorkflowRevisionListResponse(
            revisions=tuple(_revision_response(r) for r in history)
        )

    @router.get(
        "/workflows/{workflow_id}/revisions/{revision_number}",
        response_model=WorkflowRevisionDetailResponse,
    )
    def get_revision(
        workflow_id: str, revision_number: int, session: Session = Depends(session_scope)
    ) -> WorkflowRevisionDetailResponse:
        guard("READ_FILE")
        store = graph_store_factory(session)
        try:
            record = store.require_revision(workflow_id, revision_number)
            document = store.document_of(record)
        except Exception as error:
            raise refuse(error) from error
        return _revision_detail(record, document)

    @router.post(
        "/workflows/{workflow_id}/executions",
        response_model=WorkflowExecutionDetailResponse,
        status_code=201,
    )
    def start_execution(
        workflow_id: str,
        body: StartExecutionRequest,
        session: Session = Depends(session_scope),
    ) -> WorkflowExecutionDetailResponse:
        guard("WRITE_WORKSPACE_FILE")
        service = executor_factory(session)
        try:
            record = service.start(
                body.execution_id, workflow_id, revision_number=body.revision_number
            )
            evidence = service.evidence(body.execution_id)
        except Exception as error:
            raise refuse(error) from error
        return _execution_detail(record, evidence)

    @router.get(
        "/workflows/{workflow_id}/executions/{execution_id}",
        response_model=WorkflowExecutionDetailResponse,
    )
    def get_execution(
        workflow_id: str, execution_id: str, session: Session = Depends(session_scope)
    ) -> WorkflowExecutionDetailResponse:
        guard("READ_FILE")
        service = executor_factory(session)
        try:
            record = service.require(execution_id)
            evidence = service.evidence(execution_id)
        except Exception as error:
            raise refuse(error) from error
        return _execution_detail(record, evidence)

    @router.post(
        "/workflows/{workflow_id}/executions/{execution_id}/signal",
        response_model=WorkflowExecutionDetailResponse,
    )
    def signal_execution(
        workflow_id: str, execution_id: str, session: Session = Depends(session_scope)
    ) -> WorkflowExecutionDetailResponse:
        guard("WRITE_WORKSPACE_FILE")
        service = executor_factory(session)
        try:
            record = service.resume_after_signal(execution_id)
            evidence = service.evidence(execution_id)
        except Exception as error:
            raise refuse(error) from error
        return _execution_detail(record, evidence)

    @router.post(
        "/workflows/{workflow_id}/executions/{execution_id}/approve",
        response_model=WorkflowExecutionDetailResponse,
    )
    def approve_execution(
        workflow_id: str,
        execution_id: str,
        body: ApproveExecutionRequest,
        session: Session = Depends(session_scope),
    ) -> WorkflowExecutionDetailResponse:
        guard("WRITE_WORKSPACE_FILE")
        service = executor_factory(session)
        try:
            record = service.approve(
                execution_id,
                node_id=body.node_id,
                actor=body.actor,
                decision=body.decision,
                approved_revision_hash=body.approved_revision_hash,
            )
            evidence = service.evidence(execution_id)
        except Exception as error:
            raise refuse(error) from error
        return _execution_detail(record, evidence)

    return router
