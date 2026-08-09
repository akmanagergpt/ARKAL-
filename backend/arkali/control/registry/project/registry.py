"""C-12 Project / Revision Registry service.

Owner: `control.registry.project`.

THE STATE MACHINE IS THE ONLY TRANSITION AUTHORITY. `transition` builds the
canonical machine and calls `evaluate`, which raises on every rejection. There
is no transition table, no allowed-target set and no state comparison in this
module - a control asserts that, so a second authority cannot be reintroduced
quietly. The machine's typed rejections (`ForbiddenTransition`,
`IllegalTransition`, `TerminalStateEscape`, `UnknownState`) propagate unchanged,
so a caller can assert the precise reason.

NO POLICY IMPORT. Whether an actor may create or transition a project is a
`control.policy` decision. The F-0028 repair made that edge canonically legal,
but the call site that would carry the decision is a higher-layer surface which
does not exist yet. Fabricating it here would create the future surface in the
wrong context, so the registry contract stays clean and the decision stays with
the caller.

NO SECRET MATERIAL. The record carries identity, lifecycle state, timestamps and
a provenance reference. Nothing here accepts or stores credentials.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arkali.control.registry.project.errors import (
    DuplicateIdentity,
    InvalidProjectIdentity,
    UnknownProject,
)
from arkali.control.registry.project.project_state_machine import build
from arkali.control.registry.project.records import (
    INITIAL_STATE,
    ProjectRecord,
    ProjectRevisionRecord,
    utc_now,
)
from arkali.kernel.contracts.state_machine import TransitionOutcome


class ProjectRegistry:
    """Persistent Project/Revision Registry over one session.

    Transaction boundaries belong to the caller's `unit_of_work`; this service
    never commits, so a caller cannot obtain a partially committed registry.
    """

    def __init__(self, session: Session) -> None:
        self._session = session
        self._machine = build()

    @property
    def machine_name(self) -> str:
        """The lifecycle authority this registry defers to."""
        return self._machine.machine

    def get(self, project_id: str) -> ProjectRecord | None:
        return self._session.execute(
            select(ProjectRecord).where(ProjectRecord.project_id == project_id)
        ).scalar_one_or_none()

    def require(self, project_id: str) -> ProjectRecord:
        found = self.get(project_id)
        if found is None:
            raise UnknownProject(f"no project {project_id!r} is registered")
        return found

    def create_project(self, project_id: str, name: str) -> ProjectRecord:
        """Register a project in the machine's declared initial state.

        The duplicate check below is a courtesy that yields a typed error; the
        guarantee is the primary key and the unique constraint on `name`, which
        hold even when two writers race past this check.
        """
        if not project_id.strip() or not name.strip():
            raise InvalidProjectIdentity("project identity and name must be non-empty")
        if self.get(project_id) is not None:
            raise DuplicateIdentity(f"project {project_id!r} is already registered")
        record = ProjectRecord(
            project_id=project_id, name=name, lifecycle_state=INITIAL_STATE
        )
        self._session.add(record)
        self._session.flush()
        return record

    def transition(self, project_id: str, target: str) -> TransitionOutcome:
        """Move a project's lifecycle state through the canonical machine.

        The machine decides. This method records the result; it never decides
        whether the move is legal, and it raises before touching the row.
        """
        record = self.require(project_id)
        outcome = self._machine.evaluate(record.lifecycle_state, target)
        record.lifecycle_state = target
        record.updated_at = utc_now()
        self._session.flush()
        return outcome

    def next_sequence(self, project_id: str) -> int:
        """The next revision ordinal for a project, derived from stored rows."""
        highest = self._session.execute(
            select(func.max(ProjectRevisionRecord.sequence)).where(
                ProjectRevisionRecord.project_id == project_id
            )
        ).scalar_one_or_none()
        return 1 if highest is None else int(highest) + 1

    def create_revision(
        self, project_id: str, revision_id: str, provenance_ref: str | None = None
    ) -> ProjectRevisionRecord:
        """Append an immutable revision to an existing project.

        The foreign key is what actually guarantees the project exists; the
        lookup here exists to raise a typed error rather than a driver error.
        """
        self.require(project_id)
        if not revision_id.strip():
            raise InvalidProjectIdentity("revision identity must be non-empty")
        if self.revision(revision_id) is not None:
            raise DuplicateIdentity(f"revision {revision_id!r} is already registered")
        record = ProjectRevisionRecord(
            revision_id=revision_id,
            project_id=project_id,
            sequence=self.next_sequence(project_id),
            provenance_ref=provenance_ref,
        )
        self._session.add(record)
        self._session.flush()
        return record

    def revision(self, revision_id: str) -> ProjectRevisionRecord | None:
        return self._session.execute(
            select(ProjectRevisionRecord).where(
                ProjectRevisionRecord.revision_id == revision_id
            )
        ).scalar_one_or_none()

    def revisions_of(self, project_id: str) -> tuple[ProjectRevisionRecord, ...]:
        return tuple(
            self._session.execute(
                select(ProjectRevisionRecord)
                .where(ProjectRevisionRecord.project_id == project_id)
                .order_by(ProjectRevisionRecord.sequence)
            ).scalars().all()
        )
