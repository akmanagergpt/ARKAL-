"""Command Center API request/response contracts.

Owner: `surfaces.command` — AUTHORITY_MAP.yaml concern
`command_center_presentation`. `ARCHITECTURE.md` section 3 names this context
"Command Center API + frontend".

NO SECOND DOMAIN MODEL. These are transport shapes, not a rival Project model.
Every field is projected from `control.registry.project`'s records, and the
lifecycle state is carried as the value the canonical Project machine recorded -
this module declares no state, no transition and no validation of either.

NOTHING INTERNAL CROSSES THE BOUNDARY. No SQLAlchemy object, no filesystem path,
no database URL and no stack trace is representable here: every field is a
scalar the caller supplied or the registry recorded.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Every route this surface serves declares its AUDIENCE as an OpenAPI tag, and
#: the contract-drift control reads it off the live document.
#:
#: ADDED IN PACKAGE 4, closing F-0037. Until Phase 7 every backend route was
#: also a browser-slice route, so "the client covers every route the backend
#: serves" was a true and useful statement. Package 4 adds routes for
#: `ARK-REQ-0027`, which is owned by `execution.durable` with `arch, integ`
#: evidence and no `e2e` — no Phase 7 requirement is owned by a surface context,
#: so no frontend obligation exists. The premise expired; the invariant behind
#: it did not.
#:
#: Declaring the audience in the application rather than listing exceptions in a
#: test keeps the control derived: a route added later with no audience, or with
#: one nobody declared, FAILS rather than being quietly excused.
BROWSER_SLICE: Final[str] = "browser-slice"
BACKEND_ONLY: Final[str] = "backend-only"

#: The complete audience vocabulary. Read by the control, so it cannot drift.
ROUTE_AUDIENCES: Final[frozenset[str]] = frozenset({BROWSER_SLICE, BACKEND_ONLY})


class TransportModel(BaseModel):
    """Base for every shape crossing this boundary.

    ONE INSTANT, ONE RENDERING (F-0038). Every persisted timestamp in this
    repository is UTC, but SQLite has no timezone type, so a row read back off
    the disk returns a *naive* datetime while the same row still live in the
    session is *aware*. The two serialise differently — `...07Z` against
    `...07` — so one durable record had two wire representations depending on
    nothing the caller could see or control. A client comparing, caching or
    hashing a reference saw drift with no domain meaning behind it.

    Normalising here rather than in each projection is deliberate: a route
    added later cannot forget, and the rule sits with the boundary it governs.
    The value is never *converted* — a naive column is already UTC by contract
    (`kernel.persistence`), so this attaches the timezone it always had and
    changes no instant.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    @field_validator("*", mode="after")
    @classmethod
    def _stamp_utc(cls, value: Any) -> Any:
        if isinstance(value, dt.datetime) and value.tzinfo is None:
            return value.replace(tzinfo=dt.UTC)
        return value


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)


class CreateRevisionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision_id: str = Field(min_length=1, max_length=64)
    provenance_ref: str | None = Field(default=None, max_length=200)


class TransitionRequest(BaseModel):
    """A requested lifecycle move. The target is not validated here.

    Whether the move is legal is the Project state machine's answer, and asking
    this model to check it would create a second relation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: str = Field(min_length=1, max_length=40)


class RevisionResponse(TransportModel):
    revision_id: str
    sequence: int
    created_at: dt.datetime
    provenance_ref: str | None


class ProjectResponse(TransportModel):
    project_id: str
    name: str
    lifecycle_state: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ProjectDetailResponse(ProjectResponse):
    revisions: tuple[RevisionResponse, ...] = ()


class ProjectListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    projects: tuple[ProjectResponse, ...] = ()


class LifecycleMachineResponse(BaseModel):
    """The declared state *vocabulary* of a canonical machine - never its relation.

    ADDED IN PACKAGE 4B, for a demonstrated contract defect rather than for
    convenience. The frontend must offer a lifecycle action without holding a
    transition map, and the only alternatives were to hard-code the state names
    in TypeScript - the shadow authority the slice forbids - or to make the user
    type a state by hand. So the surface publishes the machine's own vocabulary.

    `states` is NOT permission. Which of these is reachable from the project's
    current state is the Project machine's answer, given only when the move is
    attempted. A client that renders all of them and lets the backend refuse is
    behaving correctly; a client that filters them has invented a second
    relation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: str
    states: tuple[str, ...]


class HealthResponse(BaseModel):
    """Readiness for the slice: is the persistence layer actually reachable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    schema_revision: str | None


class EnqueueJobRequest(BaseModel):
    """What a producer must supply to enqueue one durable job.

    ADDED IN PACKAGE 4 for `ARK-REQ-0027`. These are the three C-19 identities
    and the job's opaque input, and nothing else. There is deliberately no
    field for a lifecycle state, an owner, a priority, a queue, a worker class,
    a deadline or a retry bound: the initial state is derived from the canonical
    machine, the admission terms are recorded by C-19, and everything else on
    that list is scheduling, which is C-21 at Phase 8.

    `payload` is opaque here. This surface does not interpret it, does not
    validate it against a job type's schema and does not execute anything in
    it — the runtime that eventually executes a job type owns its meaning.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    job_id: str = Field(min_length=1, max_length=64)
    job_type: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=1, max_length=200)
    payload: dict[str, object] = Field(default_factory=dict)


class JobReferenceResponse(TransportModel):
    """A durable reference the caller can come back with.

    The whole point of `ARK-REQ-0027` is that this is what an HTTP request
    returns *instead of* the work's result. It carries the identity to ask
    about later and the lifecycle state C-19 recorded, projected as a value.

    NOTHING EXECUTIONAL CROSSES THIS BOUNDARY. No attempt number, owner,
    heartbeat, deadline, retry count, worker, queue position or scheduling
    metadata is representable here — partly because exposing them would invite
    a client to reason about execution, and partly because several of them
    describe decisions Phase 7 is not entitled to make.
    """

    job_id: str
    job_type: str
    idempotency_key: str
    lifecycle_state: str
    created_at: dt.datetime


class _JobCheckpointResponse(TransportModel):
    """One real checkpoint C-19 already persisted for a job — deliberately
    a SEPARATE shape from `JobReferenceResponse`, never a field added to
    it: that class's own contract refuses execution detail, and a
    checkpoint's `payload` is exactly that. Read-only, and never a second
    progress-state store — `payload` is projected unchanged from
    `JobCheckpointRecord`, whatever the producing worker put there
    (ARKALI COMMAND CENTER — DEF-009 FLOW A CONVERGENCE AUTHORIZATION,
    item 9).
    """

    sequence: int
    payload: dict[str, object]
    recorded_at: dt.datetime


class _StartChangeRequest(BaseModel):
    """One real natural-language Managed Product change request (D-030
    V1) — the whole transport shape "Değişikliği Başlat" needs. Private:
    `surfaces.command`'s aggregated public-symbol budget is already at its
    ceiling, matching `_JobCheckpointResponse`'s own precedent."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_text: str = Field(min_length=1, max_length=4000)


class _ChangePromotionResponse(TransportModel):
    """The new `ProjectRevisionRecord` a real "Kabul Et" produced — never
    the job reference (that stays `JobReferenceResponse`, unchanged)."""

    revision_id: str
    provenance_ref: str


class ErrorResponse(BaseModel):
    """A refusal the client can act on.

    `code` is the canonical error code, so a client branches on a stable value
    rather than on message text. `message` is the domain error's own message and
    never a rendered exception, so no traceback or source path is exposed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
