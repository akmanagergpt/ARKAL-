"""C-20 canonical workflow graph store: publish and read immutable revisions.

Owner: `execution.workflow`.

EVERY OPERATION IS GOVERNED. The PEP is injected with no default - the same
`execution.durable.JobStore` discipline - so a caller cannot obtain a store that
reads or writes without a policy decision. Reads request `READ_FILE`, writes
`WRITE_WORKSPACE_FILE`; no new operation class is invented, and
`unmapped_action_resolution: DENY` means none could be.

REVISION NUMBERING AND SEMVER ARE DERIVED, NEVER SUPPLIED. `publish` computes
the next `revision_number` from the highest stored row and the next semver from
the prior revision's semver plus the caller's declared bump kind
(`bump_semver`), the same "derived from rows, never a counter" idiom
`JobExecution.attempt_count` uses.

THE CONTENT HASH IS NEVER TRUSTED FROM STORAGE. `document_of` recomputes
`WorkflowGraphDocument.content_hash` from the stored declared content and
refuses a mismatch (`RevisionIntegrityViolation`) rather than reading the
stored `revision_hash` column as self-certifying - a tampered or corrupted row
is refused, not silently served.

TRANSACTION BOUNDARIES BELONG TO THE CALLER. Like `JobStore`, this service
never commits.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.execution.workflow.errors import (
    RevisionIntegrityViolation,
    UnknownWorkflow,
    UnknownWorkflowRevision,
)
from arkali.execution.workflow.graph_model import WorkflowGraphDocument, bump_semver
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from arkali.execution.workflow.records import (
    WorkflowRecord,
    WorkflowRevisionRecord,
    utc_now,
)

#: The actor this context presents to the PDP.
ACTOR: Final[str] = "execution.workflow"
TRUST_TIER: Final[str] = "TRUST-0"

READ: Final[str] = "READ_FILE"
WRITE: Final[str] = "WRITE_WORKSPACE_FILE"

Clock = Callable[[], dt.datetime]


class WorkflowGraphStore:
    """C-20 persistence over one session: publish and read revisions."""

    def __init__(
        self,
        session: Session,
        pep: PolicyEnforcementPoint,
        vocabulary: GraphVocabulary,
        clock: Clock = utc_now,
    ) -> None:
        self._session = session
        self._pep = pep
        self._vocabulary = vocabulary
        self._clock = clock

    def _guard(self, operation: str) -> None:
        self._pep.require_auto(
            PolicyRequest(
                operation_class=operation, trust_tier=TRUST_TIER, actor=ACTOR
            )
        )

    # -- reads -----------------------------------------------------------

    def get_workflow(self, workflow_id: str) -> WorkflowRecord | None:
        self._guard(READ)
        return self._session.execute(
            select(WorkflowRecord).where(WorkflowRecord.workflow_id == workflow_id)
        ).scalar_one_or_none()

    def require_workflow(self, workflow_id: str) -> WorkflowRecord:
        found = self.get_workflow(workflow_id)
        if found is None:
            raise UnknownWorkflow(f"no workflow {workflow_id!r} is registered")
        return found

    def latest(self, workflow_id: str) -> WorkflowRevisionRecord | None:
        """The revision with the highest `revision_number`. Derived, not cached."""
        self._guard(READ)
        highest = self._session.execute(
            select(func.max(WorkflowRevisionRecord.revision_number)).where(
                WorkflowRevisionRecord.workflow_id == workflow_id
            )
        ).scalar_one_or_none()
        if highest is None:
            return None
        return self._revision(workflow_id, int(highest))

    def get_revision(
        self, workflow_id: str, revision_number: int
    ) -> WorkflowRevisionRecord | None:
        self._guard(READ)
        return self._revision(workflow_id, revision_number)

    def require_revision(
        self, workflow_id: str, revision_number: int
    ) -> WorkflowRevisionRecord:
        found = self.get_revision(workflow_id, revision_number)
        if found is None:
            raise UnknownWorkflowRevision(
                f"no revision {revision_number} is registered for workflow "
                f"{workflow_id!r}"
            )
        return found

    def history(self, workflow_id: str) -> tuple[WorkflowRevisionRecord, ...]:
        """Every revision, oldest first. Historical rows are never rewritten."""
        self._guard(READ)
        rows = self._session.execute(
            select(WorkflowRevisionRecord)
            .where(WorkflowRevisionRecord.workflow_id == workflow_id)
            .order_by(WorkflowRevisionRecord.revision_number)
        ).scalars()
        return tuple(rows)

    def document_of(self, record: WorkflowRevisionRecord) -> WorkflowGraphDocument:
        """Rebuild and re-validate the declared graph, refusing a tampered row.

        Never returns a document whose recomputed hash disagrees with the
        stored `revision_hash` - `WORKFLOW GRAPH IDENTITY` is never taken on
        the database's word either.
        """
        document = WorkflowGraphDocument.from_dict(self._vocabulary, record.document)
        if document.content_hash != record.revision_hash:
            raise RevisionIntegrityViolation(
                f"revision {record.workflow_id}#{record.revision_number}: "
                f"recomputed hash {document.content_hash} does not match "
                f"stored revision_hash {record.revision_hash}",
                source="CONTRACT_INVENTORY.md row 46 (C-20)",
            )
        return document

    # -- writes ------------------------------------------------------------

    def publish(
        self, document: WorkflowGraphDocument, *, semver_bump: str
    ) -> WorkflowRevisionRecord:
        """Persist `document` as the next revision of its workflow id.

        `revision_number` and `semver` are derived here, never accepted from
        the caller. The content hash is always recomputed from `document`,
        never trusted from any prior claim about it.
        """
        previous = self.latest(document.workflow_id)
        if self.get_workflow(document.workflow_id) is None:
            self._guard(WRITE)
            self._session.add(
                WorkflowRecord(workflow_id=document.workflow_id, created_at=self._clock())
            )
            self._session.flush()

        next_number = 1 if previous is None else previous.revision_number + 1
        next_semver = bump_semver(
            previous.semver if previous is not None else None, semver_bump
        )

        self._guard(WRITE)
        record = WorkflowRevisionRecord(
            workflow_id=document.workflow_id,
            revision_number=next_number,
            semver=next_semver,
            revision_hash=document.content_hash,
            document=document.to_dict(),
            created_at=self._clock(),
        )
        self._session.add(record)
        self._session.flush()
        return record

    def _revision(
        self, workflow_id: str, revision_number: int
    ) -> WorkflowRevisionRecord | None:
        return self._session.execute(
            select(WorkflowRevisionRecord).where(
                WorkflowRevisionRecord.workflow_id == workflow_id,
                WorkflowRevisionRecord.revision_number == revision_number,
            )
        ).scalar_one_or_none()
