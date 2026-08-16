"""C-20 canonical workflow graph persistence: workflow + immutable revisions.

Owner: `execution.workflow`.

TWO TABLES, ONE AUTHORITY. `workflow` records that a workflow id exists;
`workflow_revision` records every revision ever published for it, keyed
(`workflow_id`, `revision_number`). There is no "current graph" row that a save
overwrites - C-20 is `revision-hashed + semver`, and a mutable pointer would
make every reader's identity depend on when it looked. The latest revision is
*derived* by querying the highest `revision_number`, the same idiom
`execution.durable`'s `next_checkpoint_sequence` uses; nothing here caches it.

REVISIONS ARE IMMUTABLE. Once persisted, a revision refuses both update and
delete (`_refuse_revision_update` / `_refuse_revision_delete`) - the same
`before_update`/`before_delete` idiom `JobCheckpointRecord` uses, for the
identical reason: the executor and a reader both trust that a revision, once
published, reads back identically forever.

THE DECLARED GRAPH IS STORED AS JSON; THE HASH IS A COLUMN, NEVER THE SOURCE OF
TRUTH. `revision_hash` is recorded for a fast equality check, but
`WorkflowGraphStore` (Package 2's other module) always recomputes it from the
stored `document` on read and refuses a mismatch - the same discipline
`content_address.matches` was built for.

ENGINE-NEUTRAL (ARK-REQ-0012). `String`, `Integer`, `DateTime` and `JSON` only,
all rendered for SQLite and PostgreSQL alike.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Final

from sqlalchemy import DateTime, ForeignKey, Integer, String, event
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from arkali.execution.workflow.errors import ImmutableRevisionViolation
from arkali.kernel.persistence.base import PersistenceBase

WORKFLOW_TABLE: Final[str] = "workflow"
REVISION_TABLE: Final[str] = "workflow_revision"

IDENTITY_LENGTH: Final[int] = 64
SEMVER_LENGTH: Final[int] = 32
HASH_LENGTH: Final[int] = 128


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class WorkflowRecord(PersistenceBase):
    """That a workflow id exists. Nothing here names a "current" revision."""

    __tablename__ = WORKFLOW_TABLE

    workflow_id: Mapped[str] = mapped_column(String(IDENTITY_LENGTH), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    revisions: Mapped[list[WorkflowRevisionRecord]] = relationship(
        back_populates="workflow", cascade="save-update"
    )


class WorkflowRevisionRecord(PersistenceBase):
    """One immutable, content-addressed revision of one workflow's graph.

    `revision_number` is 1-based and derived by the store from stored rows,
    never supplied by a caller - the same discipline
    `JobExecution.attempt_count` uses for attempt numbers.
    """

    __tablename__ = REVISION_TABLE

    workflow_id: Mapped[str] = mapped_column(
        String(IDENTITY_LENGTH), ForeignKey(f"{WORKFLOW_TABLE}.workflow_id"), primary_key=True
    )
    revision_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: Author-declared MAJOR/MINOR/PATCH, deterministically bumped from the
    #: prior revision's semver by `bump_semver`. Never computed here.
    semver: Mapped[str] = mapped_column(String(SEMVER_LENGTH), nullable=False)
    #: `WorkflowGraphDocument.content_hash` at the moment this revision was
    #: created. A recorded fact, not the identity check itself - see module
    #: docstring.
    revision_hash: Mapped[str] = mapped_column(String(HASH_LENGTH), nullable=False)
    #: `WorkflowGraphDocument.to_dict()`. Rebuilt and re-validated on every
    #: read through `WorkflowGraphDocument.from_dict`; never trusted as-is.
    document: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    workflow: Mapped[WorkflowRecord] = relationship(back_populates="revisions")


def _refuse(action: str, identity: str) -> ImmutableRevisionViolation:
    return ImmutableRevisionViolation(
        f"revision {identity!r} cannot be {action}; a published canonical "
        "workflow graph revision is immutable, and the executor and every "
        "reader trust that it reads back identically forever",
        source="CONTRACT_INVENTORY.md row 46 (C-20)",
    )


@event.listens_for(WorkflowRevisionRecord, "before_update", propagate=True)
def _refuse_revision_update(
    _mapper: object, _connection: object, target: WorkflowRevisionRecord
) -> None:
    raise _refuse("modified", f"{target.workflow_id}#{target.revision_number}")


@event.listens_for(WorkflowRevisionRecord, "before_delete", propagate=True)
def _refuse_revision_delete(
    _mapper: object, _connection: object, target: WorkflowRevisionRecord
) -> None:
    raise _refuse("deleted", f"{target.workflow_id}#{target.revision_number}")
