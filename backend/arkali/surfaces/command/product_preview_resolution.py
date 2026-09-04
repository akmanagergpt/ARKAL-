"""Managed Product -> accepted candidate resolution, for "Uygulamayı Aç" from
Product Detail.

Owner: `surfaces.command`.

AUTHORITY BOUNDARIES ARE NOT SKIPPED. This module composes, in one fixed
order, exactly the chain Product Detail needs and nothing it does not:
`ProjectRegistry` (identity/revision truth, `control.registry.project`,
unmodified) -> `evidence.artifact.ArtifactStore` (provenance truth,
unmodified) -> a real `CandidateLedger` eligibility read
(candidate lifecycle truth, `engineering.candidate`, unmodified). Nothing
here creates, renames or duplicates any of those three authorities' own
identity: `ProjectRegistry` never becomes a candidate lookup database (it is
read only for its own revision/provenance_ref), the provenance artifact is
read only (never written here), and the candidate's lifecycle state is read,
never recorded or transitioned.

WHY `engineering.candidate` IS REACHED THROUGH A PROTOCOL. `engineering.
candidate`'s own chain into `kernel.contracts` (`engineering.candidate ->
evidence.artifact -> control.policy -> kernel.contracts`) is already
measured at `max_orchestration_depth` (4 of 4, confirmed by D-029's own
composition). A real `surfaces.command -> engineering.candidate` import
would extend that chain to 5 -- the identical shape `product_registration.
py` (`engineering.factory`) answered by defining `_CandidateLedgerSource`
instead of importing `CandidateLedger`; this module makes the same choice,
independently, since Protocols do not share across contexts.

WHY THE CANDIDATE ELIGIBILITY CHECK IS HERE, NOT ONLY INSIDE `run_preview`.
`engineering.candidate.preview.run_preview` already refuses a non-ACCEPTED
candidate (`_require_accepted`), but that refusal would only ever be
observed by a durable-job worker, minutes or hours after a user's own
click. Refusing here, synchronously, in the resolution step, is a real UX
improvement Part B's own chain requires ("-> CandidateLedger eligibility
check ->") -- it duplicates no state, since it reads the SAME real ledger
`run_preview` itself reads, through the same append-only history.

CURRENT REVISION SEMANTICS. `ProjectRegistry` declares no "current" or
"active" revision pointer anywhere (`registry.py`'s own public surface:
`revision`, `revisions_of`, both plain reads, no notion of "the" revision).
Inventing one here would be exactly the kind of policy this turn's own
directive forbids. This resolver therefore requires EXACTLY ONE revision to
exist for the project and refuses (`_AmbiguousRevisionError`) otherwise --
correct for D-029's own registration shape (always exactly one revision)
and honest about the genuinely undefined case (a product with more than one
revision, which only a human using the existing generic `POST /projects/
{id}/revisions` route could create today) rather than silently guessing
"latest".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Mapping, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from arkali.control.registry.project.registry import ProjectRegistry
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore
from arkali.kernel.contracts.contract_violation_base import ContractViolation

#: Must match `engineering.factory.product_registration`'s own marker
#: exactly -- the one fact that distinguishes a real Managed Product
#: provenance artifact from any other artifact `evidence.artifact` might
#: ever hold, without either module importing the other (a same-layer edge
#: `allow_same_layer: false` forbids, and neither needs the other's types).
_MANAGED_PRODUCT_PROVENANCE_SPEC = "managed-product-provenance/1.0.0"
_ACCEPTED_STATE = "ACCEPTED"


class _NoRevisionForProjectError(ContractViolation):
    """A project has no revision, or more than one with no canonical
    "current" pointer to disambiguate -- never silently guessed."""

    code = "ARK-ERR-0150"


class _RevisionHasNoProvenanceError(ContractViolation):
    """A project's one revision carries no `provenance_ref` at all -- a
    revision created before D-029, or through the generic manual route."""

    code = "ARK-ERR-0151"


class _ProvenanceNotManagedProductError(ContractViolation):
    """A revision's `provenance_ref` resolves to a real artifact, but that
    artifact's own recorded provenance does not carry the Managed Product
    registration marker -- never trusted as a candidate reference anyway."""

    code = "ARK-ERR-0152"


class _ReferencedCandidateNotEligibleError(ContractViolation):
    """The candidate a provenance artifact references is not, right now, a
    real terminal `ACCEPTED` candidate in `CandidateLedger`."""

    code = "ARK-ERR-0153"


@runtime_checkable
class _CandidateLedgerSource(Protocol):
    """Structural shape of `engineering.candidate.ledger.CandidateLedger`,
    unimported -- see the module docstring for why."""

    def history(self, candidate_id: str) -> tuple[Mapping[str, object], ...]: ...


@dataclass(frozen=True)
class _PreviewBridgeWiring:
    """Everything the composition root must supply for this resolver to
    run over real persistence -- constructed once, at startup, and reused
    across requests, exactly as `workflow_wiring`/`operations_wiring`
    already are for their own optional Command Center capabilities.
    `artifact_blobs` and `ledger` are cheap, stateless/append-only real
    collaborators (no per-request session needed for either); only the
    evidence database needs its own per-request session, kept separate
    from `command_center.db`'s own, matching every existing script's own
    two-database reality (`register_managed_product.py`, `product_
    registration.py`) rather than merging them into one.
    """

    artifact_session_scope: Callable[[], Iterator[Session]]
    artifact_blobs: ArtifactBlobStore
    ledger: _CandidateLedgerSource


def _resolve_candidate_for_project(
    project_id: str,
    *,
    registry: ProjectRegistry,
    artifact_session: Session,
    wiring: _PreviewBridgeWiring,
) -> str:
    """The sole entry point: a Managed Product's `project_id` resolves to
    the one real, currently-ACCEPTED candidate_id its own real provenance
    artifact references, or raises a typed refusal naming exactly which
    step in the chain failed. `registry.require` already raises
    `UnknownProject` (`control.registry.project.errors`) for an unknown
    project -- reused, not restated.
    """
    registry.require(project_id)
    revisions = registry.revisions_of(project_id)
    if len(revisions) != 1:
        raise _NoRevisionForProjectError(
            f"project {project_id!r} has {len(revisions)} revisions; this "
            "resolver requires exactly one, since no canonical current-"
            "revision pointer exists to disambiguate more"
        )
    revision = revisions[0]

    # The reference itself is already a plain attribute on the revision
    # `registry.revisions_of` just returned -- no second query needed, and
    # no `evidence.artifact.revision_link.provenance_ref_of` re-read
    # against a session bound to a DIFFERENT real database (`artifact_
    # session` is `repair-evidence.db`'s own; `ProjectRevisionRecord`
    # lives in `command_center.db`'s). `revision_link.resolve`'s OWN real
    # value -- proving the reference is a genuine derived content address
    # and resolving it to the real artifact row -- is reused below via the
    # identical `ArtifactStore` methods it itself calls.
    reference = revision.provenance_ref
    artifacts = ArtifactStore(artifact_session, wiring.artifact_blobs)
    if reference is None:
        raise _RevisionHasNoProvenanceError(
            f"revision {revision.revision_id!r} of project {project_id!r} "
            "carries no provenance_ref"
        )

    artifacts.assert_derived_identity(reference)
    provenance = artifacts.require(reference).provenance
    if provenance is None or provenance.specification_version != _MANAGED_PRODUCT_PROVENANCE_SPEC:
        raise _ProvenanceNotManagedProductError(
            f"artifact {reference!r} referenced by revision "
            f"{revision.revision_id!r} does not carry the Managed Product "
            "registration provenance marker"
        )
    candidate_id = provenance.task_id

    entries = wiring.ledger.history(candidate_id)
    if not entries or str(entries[-1]["state"]) != _ACCEPTED_STATE:
        latest_state = entries[-1]["state"] if entries else "LEGACY_UNVERIFIED"
        raise _ReferencedCandidateNotEligibleError(
            f"candidate {candidate_id!r}, referenced by project {project_id!r}, "
            f"is not currently ACCEPTED (latest recorded state: {latest_state!r})"
        )
    return candidate_id
