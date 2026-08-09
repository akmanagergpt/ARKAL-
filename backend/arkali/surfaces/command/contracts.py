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

from pydantic import BaseModel, ConfigDict, Field


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


class RevisionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    revision_id: str
    sequence: int
    created_at: dt.datetime
    provenance_ref: str | None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    project_id: str
    name: str
    lifecycle_state: str
    created_at: dt.datetime
    updated_at: dt.datetime


class ProjectDetailResponse(ProjectResponse):
    model_config = ConfigDict(frozen=True, extra="forbid")

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


class ErrorResponse(BaseModel):
    """A refusal the client can act on.

    `code` is the canonical error code, so a client branches on a stable value
    rather than on message text. `message` is the domain error's own message and
    never a rendered exception, so no traceback or source path is exposed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
