"""Command Center API — the Phase 5 vertical slice surface.

Owner: `surfaces.command` (layer rank 6). `ARCHITECTURE.md` section 3 assigns
"Command Center API + frontend" to this context, and it is the only context in
which structure check 12 permits a web application to be constructed.

DELEGATION, NOT DATA ACCESS. Every route calls `ProjectRegistry`. This module
issues no query, builds no statement and touches no mapped column directly: the
registry is the Project/Revision identity authority and the Project state
machine is the lifecycle authority, and a surface that reached past either would
become a second one. A control parses this source and fails if it does.

POLICY IS ENFORCED HERE. Rank 6 may call `control.policy` at rank 1, so this is
the legal call site the lower layers deliberately left empty. Reads request
`READ_FILE`, writes request `WRITE_WORKSPACE_FILE`; every decision lands on the
Phase 4 audit trail. `WRITE_STABLE_FILE` and `ROLLBACK_STABLE` are never
requested by this surface.

SCOPE. The minimum needed to prove the slice end to end: health, list, create,
get, one lifecycle transition, and revision creation. This is not a generic CRUD
API and deliberately offers no delete, no update and no bulk operation.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Final

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from starlette.middleware.cors import CORSMiddleware

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.registry.project.project_state_machine import (
    DEFINITION as PROJECT_MACHINE,
)
from arkali.control.registry.project.records import ProjectRecord
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.kernel.persistence.migrations import applied_revision
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.surfaces.command.contracts import (
    BROWSER_SLICE,
    CreateProjectRequest,
    CreateRevisionRequest,
    ErrorResponse,
    HealthResponse,
    LifecycleMachineResponse,
    ProjectDetailResponse,
    ProjectListResponse,
    ProjectResponse,
    RevisionResponse,
    TransitionRequest,
)
from arkali.surfaces.command.error_mapping import (
    DOMAIN_ERROR_BASE,
    code_of,
    message_of,
    status_for,
)
from arkali.surfaces.command.factory import _build_factory_router, _FactorySubmitter
from arkali.surfaces.command.jobs import build_jobs_router
from arkali.surfaces.command.operations import Wiring as OperationsWiring
from arkali.surfaces.command.operations import _build_operations_router
from arkali.surfaces.command.workflow import (
    DocumentBuilder,
    ExecutorFactory,
    GraphStoreFactory,
    build_workflow_router,
)

#: The actor this surface presents to the PDP.
ACTOR: Final[str] = "surfaces.command"
TRUST_TIER: Final[str] = "TRUST-0"
SURFACE: Final[str] = "surfaces.command.api"

READ: Final[str] = "READ_FILE"
WRITE: Final[str] = "WRITE_WORKSPACE_FILE"


@dataclass(frozen=True)
class _CommandExtensions:
    operations_wiring: OperationsWiring | None = None
    operations_repo_root: pathlib.Path | None = None
    factory_submitter: _FactorySubmitter | None = None


def _project_response(record: ProjectRecord) -> ProjectResponse:
    return ProjectResponse(
        project_id=record.project_id,
        name=record.name,
        lifecycle_state=record.lifecycle_state,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _detail(registry: ProjectRegistry, record: ProjectRecord) -> ProjectDetailResponse:
    revisions = tuple(
        RevisionResponse(
            revision_id=r.revision_id,
            sequence=r.sequence,
            created_at=r.created_at,
            provenance_ref=r.provenance_ref,
        )
        for r in registry.revisions_of(record.project_id)
    )
    return ProjectDetailResponse(
        **_project_response(record).model_dump(), revisions=revisions
    )


def create_app(
    engine: Engine,
    pdp: PolicyDecisionPoint,
    clock: Callable[[], dt.datetime] | None = None,
    workflow_wiring: tuple[DocumentBuilder, GraphStoreFactory, ExecutorFactory] | None = None,
    extensions: _CommandExtensions | None = None,
) -> FastAPI:
    """Build the Command Center API over a real engine and a real PDP.

    Engine and PDP are injected with no default, so a caller cannot obtain an
    application backed by something other than the real persistence layer and
    the real policy authority.

    `clock` is optional and reaches only the durable-job routes, which pass it
    to C-19. `workflow_wiring` is `(document_builder, graph_store_factory,
    executor_factory)` for the C-20 routes - see `workflow.py`'s module
    docstring for why these are opaque callables rather than a concrete
    `execution.workflow` type: `app.py` is at `max_contexts_touched_by_module`
    and a type import from `execution.workflow` would put it over, and
    composing `execution.workflow.executor` here directly would extend an
    already-four-hop chain (`execution.workflow → execution.durable →
    control.policy → kernel.contracts`) to five, breaching
    `max_orchestration_depth`. `None` omits the workflow routes entirely, so
    every existing caller of `create_app` is unaffected.

    `operations_wiring` is `(job_recovery_factory, executor_factory, pdp,
    probe_host)` for the C-34 Operations routes (Phase 25) - see
    `operations.py`'s own module docstring for why the PEP/PolicyRequest
    construction those factories need, and the `engineering.localai`
    host-probe import, both stay out of this module (real, measured
    `max_fan_in_per_module`/`max_contexts_touched_by_module` violations).
    `operations_repo_root` is required alongside it - both `None` together
    omit the operations routes entirely, so every existing caller of
    `create_app` is unaffected.
    """
    factory = create_session_factory(engine)
    pep = PolicyEnforcementPoint(pdp, SURFACE)
    app = FastAPI(title="ARKALI Command Center", version="0.1.0")
    # Tauri's production webview has one fixed local origin. This is not a
    # general CORS relaxation: browsers and arbitrary origins remain refused.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://tauri.localhost"],
        allow_methods=["GET", "POST"],
        allow_headers=["Accept", "Content-Type"],
        allow_credentials=False,
    )
    app.state.pep = pep

    def session_scope() -> Iterator[Session]:
        with unit_of_work(factory) as session:
            yield session

    def guard(operation: str) -> None:
        pep.require_auto(
            PolicyRequest(
                operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
            )
        )

    def refuse(error: Exception) -> HTTPException:
        """Turn a domain refusal into its mapped response, or re-raise it."""
        status = status_for(error)
        if status is None:
            raise error
        return HTTPException(
            status_code=status,
            detail=ErrorResponse(
                code=code_of(error), message=message_of(error)
            ).model_dump(),
        )

    @app.exception_handler(DOMAIN_ERROR_BASE)
    def mapped_domain_error(_request: Request, error: Exception) -> JSONResponse:
        """The mapping, reachable from anywhere a domain error can be raised.

        CLOSES F-0039. `guard()` runs *before* a route's `try`, so a real
        `PolicyDenied` escaped every handler and surfaced as HTTP 500 even
        though the table mapped it to 403. Nothing was ever wrongly permitted —
        the PEP still refused and nothing was written — but the client could
        not tell a refusal from a broken server, and the control that was
        supposed to cover this asserted `status_for(PolicyDenied(...)) == 403`,
        which proves the *table* and never the *route*.

        Registering it here rather than moving each `guard` inside a `try` fixes
        it once for every route, including ones added later, and leaves an
        unmapped error propagating exactly as before: `status_for` returning
        None still means this surface has no opinion, and inventing a status
        for it would be the failure mode the mapping exists to prevent.
        """
        status = status_for(error)
        if status is None:
            raise error
        return JSONResponse(
            status_code=status,
            content={
                "detail": ErrorResponse(
                    code=code_of(error), message=message_of(error)
                ).model_dump()
            },
        )

    # Every route declares its audience; these are the Phase 5 vertical slice
    # the browser actually drives, and the contract-drift control requires the
    # TypeScript client to cover each of them.
    router = APIRouter(prefix="/api", tags=[BROWSER_SLICE])

    @router.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        guard(READ)
        return HealthResponse(status="ready", schema_revision=applied_revision(engine))

    @router.get("/lifecycle/project", response_model=LifecycleMachineResponse)
    def project_lifecycle() -> LifecycleMachineResponse:
        """Publish the canonical machine's vocabulary, projected, never restated.

        Both values are read off the canonical definition, so this route cannot
        drift from it. The transition relation is deliberately not published:
        a client that received it could decide legality itself, which is exactly
        the second authority the slice forbids.
        """
        guard(READ)
        return LifecycleMachineResponse(
            machine=PROJECT_MACHINE.machine, states=PROJECT_MACHINE.states
        )

    @router.get("/projects", response_model=ProjectListResponse)
    def list_projects(
        session: Session = Depends(session_scope),
    ) -> ProjectListResponse:
        guard(READ)
        registry = ProjectRegistry(session)
        return ProjectListResponse(
            projects=tuple(_project_response(p) for p in registry.list_projects())
        )

    @router.post("/projects", response_model=ProjectDetailResponse, status_code=201)
    def create_project(
        body: CreateProjectRequest, session: Session = Depends(session_scope)
    ) -> ProjectDetailResponse:
        guard(WRITE)
        registry = ProjectRegistry(session)
        try:
            record = registry.create_project(body.project_id, body.name)
        except Exception as error:
            raise refuse(error) from error
        return _detail(registry, record)

    @router.get("/projects/{project_id}", response_model=ProjectDetailResponse)
    def get_project(
        project_id: str, session: Session = Depends(session_scope)
    ) -> ProjectDetailResponse:
        guard(READ)
        registry = ProjectRegistry(session)
        try:
            record = registry.require(project_id)
        except Exception as error:
            raise refuse(error) from error
        return _detail(registry, record)

    @router.post(
        "/projects/{project_id}/transitions", response_model=ProjectDetailResponse
    )
    def transition(
        project_id: str,
        body: TransitionRequest,
        session: Session = Depends(session_scope),
    ) -> ProjectDetailResponse:
        guard(WRITE)
        registry = ProjectRegistry(session)
        try:
            registry.transition(project_id, body.target)
            record = registry.require(project_id)
        except Exception as error:
            raise refuse(error) from error
        return _detail(registry, record)

    @router.post(
        "/projects/{project_id}/revisions",
        response_model=ProjectDetailResponse,
        status_code=201,
    )
    def create_revision(
        project_id: str,
        body: CreateRevisionRequest,
        session: Session = Depends(session_scope),
    ) -> ProjectDetailResponse:
        guard(WRITE)
        registry = ProjectRegistry(session)
        try:
            registry.create_revision(project_id, body.revision_id, body.provenance_ref)
            record = registry.require(project_id)
        except Exception as error:
            raise refuse(error) from error
        return _detail(registry, record)

    app.include_router(router)
    # The durable-job routes are built in their own module and handed the same
    # session scope, the same policy guard and the same refusal mapping the
    # routes above use, so there is one enforcement path on this surface rather
    # than two. They live there because this module already touches three
    # bounded contexts, which is the whole budget.
    app.include_router(build_jobs_router(session_scope, guard, refuse, pep, clock))
    # The C-20 workflow routes are additive and optional at this composition
    # root: a caller that supplies no wiring gets exactly the pre-Phase-17
    # application, unchanged - no existing caller of `create_app` is required
    # to know about `execution.workflow` to keep working.
    if workflow_wiring is not None:
        document_builder, graph_store_factory, executor_factory = workflow_wiring
        app.include_router(
            build_workflow_router(
                session_scope, guard, refuse,
                document_builder, graph_store_factory, executor_factory,
            )
        )
    # The C-34 Operations routes (Phase 25) are additive and optional at this
    # composition root, the identical shape `workflow_wiring` already
    # established: a caller that supplies none gets the pre-Phase-25
    # application unchanged.
    if (extensions is not None and extensions.operations_wiring is not None
            and extensions.operations_repo_root is not None):
        app.include_router(
            _build_operations_router(
                session_scope, guard, refuse, engine, extensions.operations_repo_root,
                extensions.operations_wiring,
            )
        )
    if extensions is not None and extensions.factory_submitter is not None:
        app.include_router(
            _build_factory_router(
                session_scope, guard, WRITE, extensions.factory_submitter
            )
        )
    return app
