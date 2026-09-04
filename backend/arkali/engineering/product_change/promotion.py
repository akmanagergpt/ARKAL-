"""Promote or reject one prepared Managed Product modification (D-030
Rulings 4, 13, 16, 17-19; the Promotion-Idempotency, Base-Revision-
Concurrency and Rollback-Implementation-Scope rules).

HUMAN_GATE_3, A NEW OPERATION CLASS, NEVER A BROADENED ONE. Gate 3's own
canonical description (`CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md`
§Canonical HUMAN GATES, item 3) is "Generated-product promotion where the
canonical set marks it approval-gated" -- a Managed Product revision IS
exactly this category, so this reuses Gate 3's own number. It is a
DIFFERENT `operation_class` (`MANAGED_PRODUCT_REVISION_PROMOTION`) from
`lifecycle.evolution`'s existing `PROMOTE_CHILD_PRODUCT`, independently
scoped by `GovernanceState.operation_grant`'s own (gate, operation_class,
target, revision) binding -- Phase 24's own recorded HGR-006 note already
anticipated exactly this: a Gate 3 grant "does not authorize... any real
future PROMOTE_CHILD_PRODUCT runtime operation, which requires its own
separate RUNTIME_OPERATION-scope grant". No existing grant can satisfy
this; no grant this creates can satisfy `PROMOTE_CHILD_PRODUCT`.

`GovernanceState` UNIMPORTED. `_HumanGateSource` is redeclared, not
imported, for the identical reason `lifecycle.recovery.migration_safety_
types.HumanGateSource` already is: `acceptance.engine`'s own chain into
`kernel.contracts` already measures 4 of 4.

IDEMPOTENCY VIA `ArtifactStore` CONTENT-ADDRESSING, NOT A SECOND LEDGER.
The archived changeset's bytes are registered before any revision is
created; if an identical-content revision already exists for this
project, it is returned unchanged rather than duplicated -- the same
content-idempotency discipline D-030's own Ruling on `ProjectRegistry`
uniqueness already established for the initial Managed Product revision.

ROLLBACK IS RE-PROMOTING AN OLDER REVISION'S OWN SOURCE, NOT A NEW
MACHINE. `ProjectRevisionRecord.sequence` already orders every revision;
"rollback" is out of this module's scope to implement as a distinct
capability (Ruling: Rollback-Implementation-Scope) -- a human re-running
`prepare_modification`/`promote_modification` against an older revision's
own materialized source through the ordinary flow already achieves it
with zero new authority.
"""

from __future__ import annotations

import shutil
from typing import Protocol, runtime_checkable

from arkali.control.registry.project.records import ProjectRevisionRecord
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.engineering.product_change.errors import (
    PromotionNotAuthorizedError,
    StaleBaseRevisionError,
    VerificationFailedError,
)
from arkali.engineering.product_change.modification import PreparedModification
from arkali.engineering.product_change.revision_resolution import (
    _MANAGED_PRODUCT_REVISION_SOURCE_SPEC,
    archive_source,
    resolve_current_revision,
)
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput

PROMOTION_GATE_ID = "HUMAN_GATE_3"
PROMOTION_OPERATION_CLASS = "MANAGED_PRODUCT_REVISION_PROMOTION"


@runtime_checkable
class _HumanGateSource(Protocol):
    """Structural shape of `acceptance.engine.GovernanceState.operation_
    grant` -- see the module docstring for why this is redeclared."""

    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str,
        revision_identity: str,
    ) -> bool: ...


def _find_revision_by_provenance(
    registry: ProjectRegistry, project_id: str, provenance_ref: str,
) -> ProjectRevisionRecord | None:
    for revision in registry.revisions_of(project_id):
        if revision.provenance_ref == provenance_ref:
            return revision
    return None


def promote_modification(
    project_id: str, prepared: PreparedModification, *, registry: ProjectRegistry,
    artifacts: ArtifactStore, human_gates: _HumanGateSource, issuer_identity: str,
) -> ProjectRevisionRecord:
    """Turn one verified `PreparedModification` into a new, real
    `ProjectRevisionRecord` -- refusing (never silently degrading) if
    verification failed, the project's real current revision moved on
    since `prepared` captured its base, or no matching Gate 3 grant for
    this exact changeset exists. Returns the SAME existing record,
    creating nothing new, if this exact changeset was already promoted
    (double-accept safety)."""
    if not prepared.verification.passed:
        raise VerificationFailedError(
            f"changeset failed verification: {prepared.verification.failures}"
        )

    archive_bytes = archive_source(prepared.product_root)
    archive_ref = artifacts.register(
        archive_bytes,
        ProvenanceInput(
            producer_agent="engineering.product_change", provider_model="local",
            task_id=project_id, specification_version=_MANAGED_PRODUCT_REVISION_SOURCE_SPEC,
            #: The changeset's own content-address, already a real,
            #: deterministic digest of exactly what this archive contains.
            context_hash=prepared.changeset_ref,
            parents=(prepared.plan_ref, prepared.changeset_ref),
        ),
    )
    existing = _find_revision_by_provenance(registry, project_id, archive_ref)
    if existing is not None:
        return existing

    current = resolve_current_revision(project_id, registry=registry)
    if current.revision_id != prepared.base_revision_id:
        raise StaleBaseRevisionError(
            f"project {project_id!r} current revision is now "
            f"{current.revision_id!r}, not the base "
            f"{prepared.base_revision_id!r} this modification was prepared "
            "against; re-run the modification against the current revision"
        )

    if not human_gates.operation_grant(
        PROMOTION_GATE_ID, PROMOTION_OPERATION_CLASS, archive_ref, current.revision_id,
    ):
        raise PromotionNotAuthorizedError(
            f"no recorded {PROMOTION_GATE_ID} grant for operation "
            f"{PROMOTION_OPERATION_CLASS!r}, target {archive_ref!r}, "
            f"revision {current.revision_id!r}; issuer {issuer_identity!r} "
            "must record one before this changeset may be promoted"
        )

    revision_id = f"{project_id}-r{current.sequence + 1}"
    return registry.create_revision(project_id, revision_id, provenance_ref=archive_ref)


def reject_modification(prepared: PreparedModification) -> None:
    """Discard a prepared modification's isolated workspace. Creates
    nothing, mutates no registry -- `ProjectRegistry` never records a
    rejected proposal, matching the Ruling's explicit "zero
    ProjectRevisionRecords on reject" requirement."""
    shutil.rmtree(prepared.workspace.root, ignore_errors=True)
