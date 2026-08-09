"""C-12 project / revision records.

Owner: `control.registry.project` — AUTHORITY_MAP.yaml concern
`project_and_revision_identity`. ARCHITECTURE.md section 5 names this context the
sole authority for "Project and revision identity".

WHAT THIS OWNS AND WHAT IT DOES NOT. It owns identity: which projects exist,
which revisions exist, and which project a revision belongs to. It does not own:

  * the project lifecycle relation - that is the Project state machine, and
    `registry.py` delegates every transition to it rather than restating one
    here. `lifecycle_state` is a recorded value, not a second transition table;
  * content-addressed revision identity and provenance - the dependency matrix
    assigns that to `evidence.artifact` at Phase 6. `provenance_ref` is a
    nullable reference to a record that does not exist yet, never a hash
    computed here;
  * candidate assembly (`engineering.candidate`, Phase 12) and stable promotion
    (`lifecycle.release`), neither of which is Phase 5.

IDENTITY IS ENFORCED BY THE DATABASE. Uniqueness and referential integrity are
real constraints, not pre-insert queries: a check-then-insert loses to a
concurrent writer, and SQLite enforces foreign keys only because Package 1
turned them on. Python-level validation exists as well, but it is the second
line, never the only one.

ENGINE-NEUTRAL (ARK-REQ-0012). Declarative mapping only - `String`, `Integer`,
`Boolean`, `DateTime`, `JSON`, and constraints SQLAlchemy renders for SQLite and
PostgreSQL alike. No PRAGMA, no raw SQL, no dialect branch. The engine itself is
built only by `kernel.persistence`.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from arkali.control.registry.project.errors import ImmutableRevisionViolation
from arkali.control.registry.project.project_state_machine import DEFINITION
from arkali.kernel.persistence.base import PersistenceBase

PROJECT_TABLE: Final[str] = "project"
REVISION_TABLE: Final[str] = "project_revision"

#: The state a project starts in. Read from the machine's declared relation -
#: the single state with no incoming transition - so the registry cannot
#: nominate an initial state the machine does not recognise.
INITIAL_STATE: Final[str] = next(
    state for state in DEFINITION.states
    if all(target != state for _, target in DEFINITION.transitions)
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class ProjectRecord(PersistenceBase):
    """A project's identity and its recorded lifecycle state.

    Mutable by design: the Project machine declares four non-terminal states and
    the record follows it. Every change goes through `ProjectRegistry`.
    """

    __tablename__ = PROJECT_TABLE

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    lifecycle_state: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    revisions: Mapped[list[ProjectRevisionRecord]] = relationship(
        back_populates="project", cascade="save-update"
    )


class ProjectRevisionRecord(PersistenceBase):
    """An immutable revision of a project.

    `ARCHITECTURE.md` section 7 states that revisions are immutable and that a
    change creates a new one. Immutability is enforced below by refusing any
    update to a persisted row, so the invariant does not depend on callers
    choosing not to write.
    """

    __tablename__ = REVISION_TABLE
    __table_args__ = (
        UniqueConstraint("project_id", "sequence", name="uq_revision_project_sequence"),
    )

    revision_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey(f"{PROJECT_TABLE}.project_id"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    #: Reference to the provenance record that `evidence.artifact` will own from
    #: Phase 6. Held as a reference so no second provenance authority is created.
    provenance_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)

    project: Mapped[ProjectRecord] = relationship(back_populates="revisions")


@event.listens_for(ProjectRevisionRecord, "before_update", propagate=True)
def _refuse_revision_update(_mapper: object, _connection: object,
                            target: ProjectRevisionRecord) -> None:
    """A persisted revision cannot be modified, only superseded by a new one."""
    raise ImmutableRevisionViolation(
        f"revision {target.revision_id!r} is immutable; a change creates a new "
        "revision (ARCHITECTURE.md section 7)",
        source="docs/canonical/ARCHITECTURE.md section 7",
    )
