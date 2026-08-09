"""Resolving a C-12 revision's `provenance_ref` to a C-14 artifact.

Owner: `evidence.artifact`.

THE DIRECTION IS THE WHOLE POINT. `control.registry.project` is layer rank 1 and
`evidence.artifact` is rank 2, so this context may read the registry and the
registry may never import this one. Phase 5 anticipated exactly this and left
`provenance_ref` as a nullable scalar with a comment saying the reference would
be resolved from Phase 6 - "held as a reference so no second provenance
authority is created". This module is that resolution, and it is why C-12 needs
no change: a 71-character address already fits its `String(200)` column.

WHY IT IS ITS OWN MODULE. `store.py` already touches `control.policy`, and
`max_contexts_touched_by_module` is 3. Putting the registry import there as well
would push the artifact service toward the central object the constitution
forbids. ADR-0008 makes decomposition the answer to a budget rather than an
exception, so the registry edge lives here alone.

NO SECOND IDENTITY AUTHORITY. Nothing here creates, renames or validates a
revision. `control.registry.project` remains the sole authority for revision
identity; this module only reads the reference it recorded and asks the artifact
store what it points at.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from arkali.control.registry.project.records import ProjectRevisionRecord
from arkali.evidence.artifact.records import ArtifactRecord
from arkali.evidence.artifact.store import ArtifactStore


def provenance_ref_of(session: Session, revision_id: str) -> str | None:
    """The raw reference C-12 recorded, or None. No interpretation applied."""
    return session.execute(
        select(ProjectRevisionRecord.provenance_ref).where(
            ProjectRevisionRecord.revision_id == revision_id
        )
    ).scalar_one_or_none()


def resolve(store: ArtifactStore, session: Session, revision_id: str) -> ArtifactRecord | None:
    """The artifact a revision's `provenance_ref` points at.

    Returns None when the revision has no reference, which is the honest answer
    for every revision created before Phase 6 - and for any revision whose
    producer chose not to record one. A missing reference is not an error here;
    whether it *should* be is an acceptance question, not a storage one.

    A reference that is present but not a canonical content address is refused
    rather than looked up, so a hand-written string cannot masquerade as a
    derived identity.
    """
    reference = provenance_ref_of(session, revision_id)
    if reference is None:
        return None
    store.assert_derived_identity(reference)
    return store.require(reference)
