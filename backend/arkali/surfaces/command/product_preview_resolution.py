"""Managed Product -> current-revision preview subject resolution, for
"Uygulamayı Aç" from Product Detail.

Owner: `surfaces.command`.

F-0074 CONVERGENCE (D-030's own "Preview-Refactor-Safety" concern). The
prior version of this module required a project to carry EXACTLY ONE
`ProjectRevisionRecord` -- correct for D-029's own registration shape
(always exactly one revision) but insufficient once D-030's own promotion
path (`engineering.product_change.promotion.promote_modification`) can
append a second, third, ... revision. This version resolves the project's
real CURRENT revision by D-030's own ratified rule --
`ProjectRevisionRecord.sequence` maximum, read directly off `ProjectRegistry`
(never a new pointer, never an import of `engineering.product_change`) --
and branches on which of the two real provenance marker shapes the current
revision's own artifact carries.

AUTHORITY BOUNDARIES ARE NOT SKIPPED. This module composes, in one fixed
order, exactly the chain Product Detail needs and nothing it does not:
`ProjectRegistry` (identity/revision truth, `control.registry.project`,
unmodified) -> `evidence.artifact.ArtifactStore` (provenance truth,
unmodified) -> for a Factory-origin revision only, a real `CandidateLedger`
eligibility read (candidate lifecycle truth, `engineering.candidate`,
unmodified). Nothing here creates, renames or duplicates any of those
authorities' own identity.

WHY `engineering.candidate` IS REACHED THROUGH A PROTOCOL, UNCHANGED FROM
BEFORE. `engineering.candidate`'s own chain into `kernel.contracts` is
already measured at `max_orchestration_depth` (4 of 4). A real
`surfaces.command -> engineering.candidate` import would extend that chain
to 5 -- the identical shape `product_registration.py` (`engineering.
factory`) answered by defining `_CandidateLedgerSource` instead of
importing `CandidateLedger`.

WHY `engineering.product_change` IS NEVER IMPORTED EITHER. `resolve_
current_revision`'s own real algorithm (`ProjectRevisionRecord.sequence`
maximum) is three lines over an already-legal `ProjectRegistry` read --
reused here by re-expressing the identical algorithm directly against the
same public `revisions_of`, never by importing the function itself, since
that module's own chain plus this context's own already lands at
orchestration depth 5 and touches a fourth context (measured real during
D-030's own implementation for the reverse edge, `surfaces.command ->
engineering.product_change`, for the promote route -- the identical
budget applies here). This is the SAME "redeclare the trivial algorithm
against the shared authority, do not import the sibling module" discipline
`_MANAGED_PRODUCT_PROVENANCE_SPEC` below already established for its own
marker string, now applied a second time to `_MANAGED_PRODUCT_REVISION_
SOURCE_SPEC`.

WHAT THIS MODULE DOES NOT MATERIALIZE. Extracting a promoted revision's
real archive into a real directory is deferred to the worker (`scripts/
run_candidate_preview_worker.py`), which reuses `engineering.product_
change.revision_resolution.materialized_source` UNCHANGED, exactly as
`scripts/run_product_change_worker.py` already does -- real, possibly
slow file I/O has no business in an HTTP request (`ARK-REQ-0027`). This
module's own job is the same real, synchronous, fast eligibility check its
predecessor already performed for the candidate case, generalized: does a
real, resolvable, correctly-marked revision exist right now, so a bad
request is refused immediately rather than silently failing a durable job
minutes later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterator, Literal, Mapping, Protocol, runtime_checkable

from sqlalchemy.orm import Session

from arkali.control.registry.project.registry import ProjectRegistry
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore
from arkali.kernel.contracts.contract_violation_base import ContractViolation

#: Must match `engineering.factory.product_registration`'s own marker
#: exactly -- see the module docstring for why this is redeclared, not
#: imported.
_MANAGED_PRODUCT_PROVENANCE_SPEC = "managed-product-provenance/1.0.0"
#: Must match `engineering.product_change.revision_resolution`'s own
#: marker exactly -- the same redeclaration discipline, one level further.
_MANAGED_PRODUCT_REVISION_SOURCE_SPEC = "managed-product-revision-source/1.0.0"
_ACCEPTED_STATE = "ACCEPTED"

PreviewSubjectKind = Literal["candidate", "archive"]


class _NoRevisionForProjectError(ContractViolation):
    """A project has no revision at all -- never silently guessed."""

    code = "ARK-ERR-0150"


class _RevisionHasNoProvenanceError(ContractViolation):
    """A project's current revision carries no `provenance_ref` at all --
    a revision created before D-029, or through the generic manual route."""

    code = "ARK-ERR-0151"


class _ProvenanceNotManagedProductError(ContractViolation):
    """A revision's `provenance_ref` resolves to a real artifact, but that
    artifact's own recorded provenance carries neither real Managed
    Product marker this module knows -- never trusted as a preview source
    anyway."""

    code = "ARK-ERR-0152"


class _ReferencedCandidateNotEligibleError(ContractViolation):
    """The candidate a Factory-origin provenance artifact references is
    not, right now, a real terminal `ACCEPTED` candidate in
    `CandidateLedger`."""

    code = "ARK-ERR-0153"


class _UnknownRevisionForProjectError(ContractViolation):
    """An explicit historical-preview/restore request names a
    `revision_id` that either does not exist at all or belongs to a
    different project -- never guessed or silently substituted with the
    current revision (Revision History + Restore-as-New Convergence)."""

    code = "ARK-ERR-0175"


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
    two-database reality.
    """

    artifact_session_scope: Callable[[], Iterator[Session]]
    artifact_blobs: ArtifactBlobStore
    ledger: _CandidateLedgerSource


@dataclass(frozen=True)
class _PreviewSubject:
    """What Product Detail's real current revision resolves to, right now
    -- never a candidate_id alone (Revision 2+ has none). `subject_id` is
    the real C-19 idempotency-scope key for this preview: the current
    revision's own real `revision_id`, stable and unique for exactly as
    long as this revision stays current -- once a later promotion advances
    the project's own current revision, this value changes, so a fresh
    real preview cycle is minted rather than an old revision's job being
    recovered (D-030's own Part G/H invariant)."""

    subject_id: str
    revision_id: str
    kind: PreviewSubjectKind


def _resolve_preview_subject_for_project(
    project_id: str,
    *,
    registry: ProjectRegistry,
    artifact_session: Session,
    wiring: _PreviewBridgeWiring,
) -> _PreviewSubject:
    """The sole entry point for "Uygulamayı Aç": a Managed Product's
    `project_id` resolves to its real current revision's own real preview
    subject, or raises a typed refusal naming exactly which step in the
    chain failed. `registry.require` already raises `UnknownProject`
    (`control.registry.project.errors`) for an unknown project -- reused,
    not restated.
    """
    registry.require(project_id)
    revisions = registry.revisions_of(project_id)
    if not revisions:
        raise _NoRevisionForProjectError(
            f"project {project_id!r} has no revision to preview"
        )
    # D-030's own ratified current-revision rule -- the identical
    # three-line algorithm `engineering.product_change.revision_
    # resolution.resolve_current_revision` implements, re-expressed here
    # directly against the same public `ProjectRevisionRecord.sequence`
    # rather than imported (see the module docstring). Lexical
    # `revision_id` ordering never substitutes for the real sequence.
    revision = max(revisions, key=lambda r: r.sequence)
    return _resolve_subject_for_revision(
        revision, project_id=project_id, artifact_session=artifact_session, wiring=wiring,
    )


def _resolve_preview_subject_for_explicit_revision(
    project_id: str,
    revision_id: str,
    *,
    registry: ProjectRegistry,
    artifact_session: Session,
    wiring: _PreviewBridgeWiring,
) -> _PreviewSubject:
    """The sole entry point for an EXPLICIT historical preview ("Önizle"
    on a non-current `Sürüm`, Revision History + Restore-as-New
    Convergence): resolves to `revision_id`'s own real preview subject
    regardless of whether it is the project's current revision -- never
    silently substituted with `max(sequence)`. Shares every real check
    `_resolve_preview_subject_for_project` performs beyond identity
    resolution, through `_resolve_subject_for_revision`, so a historical
    preview is refused for exactly the same real reasons a current one
    would be (no provenance, wrong marker, not-ACCEPTED candidate) -- no
    second, weaker eligibility rule for the historical case."""
    registry.require(project_id)
    revision = registry.revision(revision_id)
    if revision is None or revision.project_id != project_id:
        raise _UnknownRevisionForProjectError(
            f"revision {revision_id!r} is not a real revision of project {project_id!r}"
        )
    return _resolve_subject_for_revision(
        revision, project_id=project_id, artifact_session=artifact_session, wiring=wiring,
    )


def _resolve_subject_for_revision(
    revision, *, project_id: str, artifact_session: Session, wiring: _PreviewBridgeWiring,  # noqa: ANN001
) -> _PreviewSubject:
    """The real chain shared by both entry points above, over one already-
    identified `ProjectRevisionRecord`: `provenance_ref` -> `ArtifactStore`
    -> the two real Managed Product provenance markers, exactly as before
    F-0074's own convergence, just no longer requiring `revision` to be
    the project's current one."""
    reference = revision.provenance_ref
    artifacts = ArtifactStore(artifact_session, wiring.artifact_blobs)
    if reference is None:
        raise _RevisionHasNoProvenanceError(
            f"revision {revision.revision_id!r} of project {project_id!r} "
            "carries no provenance_ref"
        )

    artifacts.assert_derived_identity(reference)
    provenance = artifacts.require(reference).provenance
    spec = provenance.specification_version if provenance is not None else None

    if spec == _MANAGED_PRODUCT_PROVENANCE_SPEC:
        candidate_id = provenance.task_id  # type: ignore[union-attr]
        entries = wiring.ledger.history(candidate_id)
        if not entries or str(entries[-1]["state"]) != _ACCEPTED_STATE:
            latest_state = entries[-1]["state"] if entries else "LEGACY_UNVERIFIED"
            raise _ReferencedCandidateNotEligibleError(
                f"candidate {candidate_id!r}, referenced by project "
                f"{project_id!r}, is not currently ACCEPTED (latest "
                f"recorded state: {latest_state!r})"
            )
        return _PreviewSubject(
            subject_id=candidate_id, revision_id=revision.revision_id, kind="candidate",
        )

    if spec == _MANAGED_PRODUCT_REVISION_SOURCE_SPEC:
        # The archive's own real existence was just proved by `artifacts.
        # require(reference)` above; real extraction/integrity
        # verification is the worker's own job (`materialized_source`,
        # reused unchanged) -- deliberately deferred out of this request.
        return _PreviewSubject(
            subject_id=revision.revision_id, revision_id=revision.revision_id, kind="archive",
        )

    raise _ProvenanceNotManagedProductError(
        f"artifact {reference!r} referenced by revision "
        f"{revision.revision_id!r} does not carry a recognised Managed "
        "Product provenance marker"
    )
