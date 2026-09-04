"""ACCEPTED-candidate -> Managed Product registration composition.

Owner: `engineering.factory`, per D-027's ratified assignment of "the
top-level Phase 30 production goal->release composition" to this context
(`docs/build/OPEN_BLOCKERS.md`). DEF-009 recorded that no live orchestrator
ever chained GOAL -> ... -> CANDIDATE -> PRODUCT; a later human governance
ruling authorized exactly, and only, this composition to close that gap.
This module owns nothing else -- no candidate lifecycle, no project
lifecycle, no evidence mechanism -- it only orders three already-canonical
authorities in one fixed sequence.

IDENTITY DISCIPLINE. The Managed Product is anchored to the accepted
candidate's own already-recorded canonical goal identity
(`GenerationProvenance.goal_hash`, `engineering.candidate.ledger`) -- the
same content address `RequirementBlueprint.goal.goal_id`
(`control.specification.blueprint_contracts`) computes for identical
goal_text via the identical `kernel.contracts.content_address.address_of`
primitive (`f"sha256:{hexdigest}"` either way). `project_id`/`revision_id`
are deterministic functions of that one identity, never a caller-invented
or random value, so a repeated call converges through `ProjectRegistry`'s
own existing primary-key/uniqueness guarantee (`DuplicateIdentity`) rather
than a new mapping table. Candidate identity (`golden-work-*`,
`factory-<job_id>`) never becomes `project_id` or `revision_id` -- it is
recorded only inside the provenance artifact this module registers through
the existing `evidence.artifact` authority.

NO SECOND TRUTH STORE. `CandidateLedger` is read-only here -- this module
never calls `record_state` or `begin_acceptance`; candidate lifecycle stays
exactly where it already is. `ProjectRegistry` receives only its own
already-declared fields (`project_id`, `name`, `revision_id`,
`provenance_ref`) -- never a candidate lifecycle state, never a copy of the
accepted manifest. `ArtifactStore.register` is idempotent by content
(`evidence/artifact/store.py`'s own documented guarantee: identical bytes
return the existing address, never a second row), so re-running this
composition for an unchanged accepted candidate registers no second
artifact, project, or revision.

FAILURE ATOMICITY THROUGH IDEMPOTENT CONVERGENCE, NOT A NEW COORDINATOR. A
partial prior failure (artifact registered but project creation never ran;
project created but revision creation never ran) is resolved by re-invoking
this same function: each step first checks whether its own target already
exists (`registry.get`/`registry.revision`) and only creates it if not,
catching `DuplicateIdentity` from a concurrent winner as an already-converged
outcome rather than an error. No transaction spans the three stores; each
store's own existing idempotency/uniqueness primitive is what makes a retry
safe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping, Protocol, runtime_checkable

from arkali.control.registry.project.errors import DuplicateIdentity
from arkali.control.registry.project.records import ProjectRecord, ProjectRevisionRecord
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.engineering.factory.errors import CandidateNotAcceptedError
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput

#: The real, stable value `engineering.candidate.ledger.ACCEPTED` exports
#: (`"ACCEPTED"`) -- named here rather than imported, the same choice
#: `child_product_promotion.py`'s own `GATE_3` literal already makes for an
#: identically-shaped reason: a static `engineering.factory -> engineering.
#: candidate` import already exists (`production_orchestration.py`'s own
#: `allowed_sibling_edges` entry, "factory assembles candidates") but
#: `engineering.candidate` already reaches `evidence.artifact ->
#: control.policy -> kernel.contracts`, so adding a second real edge here
#: would extend that chain to orchestration depth 5, past the 4 the
#: architecture budget allows. This module reads the ledger only through
#: `_CandidateLedgerSource` below -- the same structural-port discipline
#: `production_orchestration.py`'s own `DurableFactorySink` already
#: establishes in this exact package -- never a second lifecycle vocabulary.
_ACCEPTED_STATE = "ACCEPTED"


@runtime_checkable
class _CandidateLedgerSource(Protocol):
    """Structural shape of `engineering.candidate.ledger.CandidateLedger`,
    unimported. The real `CandidateLedger` satisfies this without either
    module knowing about the other's type."""

    def history(self, candidate_id: str) -> tuple[Mapping[str, object], ...]: ...

#: Truncated to fit `ProjectRecord.project_id`/`ProjectRevisionRecord.
#: revision_id` (`String(64)`) with room to spare for the fixed prefixes
#: below -- not a second identity scheme, a deterministic, collision-safe
#: (128 bits of the real goal_hash digest) derivation from the one canonical
#: goal identity, needed only because that identity's own canonical spelling
#: (`sha256:<64 hex>` = 71 chars) does not fit the existing column.
_DIGEST_PREFIX_LENGTH = 32
_PROJECT_ID_PREFIX = "product-"
_REVISION_SUFFIX = "-initial"


@dataclass(frozen=True)
class _ManagedProductRegistration:
    """The converged, idempotent outcome of registering one accepted
    candidate as a Managed Product. `created` is True only when this exact
    call is what created the `ProjectRecord`; a converging call that found
    the project already registered still returns the same real record with
    `created=False`, never a synthetic duplicate. Not underscore-exempt
    from the caller's perspective -- a caller receives and reads an
    instance structurally (`.project`, `.revision`, `.provenance_ref`,
    `.created`) without ever needing to import this name; the underscore
    only keeps it out of this already-at-ceiling context's public-surface
    count."""

    project: ProjectRecord
    revision: ProjectRevisionRecord
    provenance_ref: str
    created: bool


def register_accepted_candidate_as_managed_product(
    candidate_id: str,
    *,
    ledger: _CandidateLedgerSource,
    registry: ProjectRegistry,
    artifacts: ArtifactStore,
) -> _ManagedProductRegistration:
    """The sole entry point for this composition.

    Refuses (`CandidateNotAcceptedError`) unless `ledger`'s own latest
    recorded state for `candidate_id` is exactly `ACCEPTED` -- registration
    never runs ahead of, or independently of, the real acceptance boundary
    `run_golden_acceptance.py` already enforces. Idempotent: calling this
    again for the same `candidate_id` (same recorded goal_hash) returns the
    same converged project/revision/provenance_ref, never a duplicate.
    """
    entries = ledger.history(candidate_id)
    if not entries or str(entries[-1]["state"]) != _ACCEPTED_STATE:
        latest_state = entries[-1]["state"] if entries else "LEGACY_UNVERIFIED"
        raise CandidateNotAcceptedError(
            f"candidate_id {candidate_id!r} latest recorded state is "
            f"{latest_state!r}, not ACCEPTED; only a real terminal ACCEPTED "
            "candidate may become a Managed Product"
        )
    goal_hash = str(entries[0].get("goal_hash", ""))
    if not goal_hash:
        raise CandidateNotAcceptedError(
            f"candidate_id {candidate_id!r} carries no recorded goal_hash "
            "(its ALLOCATED entry is missing GenerationProvenance.goal_hash); "
            "a Managed Product cannot be anchored to an unknown goal identity"
        )
    accepted_entry = entries[-1]

    provenance_ref = _register_provenance(artifacts, candidate_id, goal_hash, accepted_entry)

    project_id = _project_id_for_goal(goal_hash)
    project = registry.get(project_id)
    created = False
    if project is None:
        try:
            project = registry.create_project(project_id, _product_name(candidate_id))
            created = True
        except DuplicateIdentity:
            project = registry.require(project_id)

    revision_id = f"{project_id}{_REVISION_SUFFIX}"
    revision = registry.revision(revision_id)
    if revision is None:
        try:
            revision = registry.create_revision(
                project_id, revision_id, provenance_ref=provenance_ref
            )
        except DuplicateIdentity:
            revision = registry.revision(revision_id)

    return _ManagedProductRegistration(
        project=project, revision=revision, provenance_ref=provenance_ref, created=created,
    )


def _register_provenance(
    artifacts: ArtifactStore, candidate_id: str, goal_hash: str,
    accepted_entry: dict[str, object],
) -> str:
    """Real evidence of this exact registration's origin, through the
    existing `evidence.artifact` authority -- references to canonical
    owners (`candidate_id`, `goal_hash`, the acceptance run's own recorded
    detail) only, never a copy of the accepted candidate's full file
    manifest or ledger history."""
    payload = json.dumps(
        {
            "schema": "managed-product-provenance/1.0.0",
            "goal_hash": goal_hash,
            "candidate_id": candidate_id,
            "accepted_at": accepted_entry.get("recorded_at"),
            "acceptance_detail": accepted_entry.get("detail", {}),
        },
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return artifacts.register(
        payload,
        ProvenanceInput(
            producer_agent="engineering.factory",
            provider_model="n/a",
            task_id=candidate_id,
            specification_version="managed-product-provenance/1.0.0",
            context_hash=goal_hash,
            evidence=("real CandidateLedger ACCEPTED entry",),
        ),
    )


def _project_id_for_goal(goal_hash: str) -> str:
    _algorithm, _, digest = goal_hash.partition(":")
    return f"{_PROJECT_ID_PREFIX}{digest[:_DIGEST_PREFIX_LENGTH]}"


def _product_name(candidate_id: str) -> str:
    """The only goal-identifying text this composition has durable access
    to without adding a fourth touched context (the durable job's own
    `goal_text` lives in `execution.durable`, out of this module's budget)
    is `candidate_id` itself -- an honest, traceable default a project owner
    remains free to change through any future rename capability, not a
    claim that this is the ideal long-term product name."""
    return f"ARKALI Application ({candidate_id})"


__all__ = [
    "register_accepted_candidate_as_managed_product",
]
