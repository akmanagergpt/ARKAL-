"""Recovery Supervisor (Phase 22B, D-017/D-018, C-32).

Owner: `lifecycle.recovery` (Protected Core).

THE SOLE PRODUCTION CALLER OF `ROLLBACK_STABLE`. Every other actor is refused
by the PDP unconditionally (`pdp.py::_rollback_rule`); this module is the one
place `AUTHORITY_MAP.yaml`'s `stable_mutation.sole_exception` names, and
`check_repository_structure.py` check 11 confines "Stable mutation path" code
to exactly this context.

INDEPENDENT AND DETERMINISTIC (`ARK-REQ-0154`). This module imports no AI
provider, no candidate-generation authority and no repair pipeline - only
already-accepted, deterministic authorities: the PDP/PEP (Phase 4, through
`RollbackAuthorization` - see below), the Stable-revision pointer (Package 1,
`lifecycle.release`, via the declared sibling edge), and the evidence plane
(Phase 6, `evidence.artifact` / `evidence.audit`, the latter through
`EvidenceSink`). A health signal is supplied by the caller, never computed
here - detecting a bad candidate is the concern of whatever runs it (Phase 23,
29), not of the authority that recovers from one.

NO TRANSFORMATION DURING RESTORE (`ARK-REQ-0159`, `ARK-REQ-0339`). Rolling
back means calling `StableRevisionPointer.rollback_to`, an identity-only
pointer switch - no content is read, generated, or rewritten. The target must
already be in the pointer's own recorded history (`ARK-REQ-0157`): a caller's
claim that a revision was "verified" is never trusted, only the pointer's own
durable record is.

EVERY ROLLBACK IS EVIDENCED (`ARK-REQ-0160`). `rollback` always registers a
real C-14 artifact for the rollback record and appends real C-15 evidence
through the injected `EvidenceSink`, reused unmodified - no second evidence
mechanism is introduced.

TWO STRUCTURAL `Protocol`s, NEITHER AN IMPORT - both found by running the real
architecture gate, not assumed:

  * `EvidenceSink` avoids `evidence.audit`. `chain.py` imports
    `control.specification.register_parser`, so its own chain already
    measures `evidence.audit -> control.specification -> control.architecture
    -> kernel.contracts`, 4 of 4 - the canonical `max_orchestration_depth`
    ceiling. A direct import from here would extend it to 5.
  * `RollbackAuthorization` avoids `control.policy`. `pep.py` and
    `policy_contract.py` are each already at `max_fan_in_per_module`'s
    ceiling (15 of 15, reached by Phase 20's own two new `lifecycle.recovery`
    importers); a new direct importer here breaches both. Importing both
    `control.policy` and `evidence.artifact` from one module would also
    breach `max_contexts_touched_by_module` (3), since `kernel.contracts` and
    `lifecycle.release` are unavoidable here too.

Both trade in primitive facts only - the identical shape
`migration_safety_types.HumanGateSource` and `pipeline.WorkspaceTarget`
already use against the same class of problem. The composition root
constructs the real `PolicyEnforcementPoint`/`PolicyRequest` and the real
`AuditChain`, and adapts each to its Protocol here; **the real PDP decision
still gates every rollback** - only the glue code that constructs the request
object moves outside this module, exactly as it already does for every
Protocol-decoupled authority in this codebase.

`verified` IS DERIVED, NEVER SETTABLE (`ARK-REQ-0135`, `ARK-REQ-0136`). There
is no field or constructor argument that marks a Recovery Supervisor
"verified". The property re-queries the real evidence sink, every call, for
a completed `ARK-REQ-0338` PASS record - the same no-caching discipline
`CapabilityGraph` and `GovernanceState` already use. Self-Evolution's own
entry guard (`core_upgrade_state_machine.recovery_supervisor_guard`) must be
populated only from this property in every real composition path; nothing
here, and nothing in that guard, accepts a caller-asserted boolean as
sufficient proof.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.kernel.contracts.error_root import ArkaliError
from arkali.kernel.contracts.honest_state import HonestState
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer

#: The actor this context presents to the PDP - the canonical invoker.
ACTOR: Final[str] = "lifecycle.recovery"
TRUST_TIER: Final[str] = "TRUST-0"
ROLLBACK_OPERATION: Final[str] = "ROLLBACK_STABLE"
CONTRACT_ID: Final[str] = "C-32"
PRODUCER: Final[str] = "lifecycle.recovery.recovery_supervisor"

#: Requirements this one rollback event evidences, in one composed run.
EVERY_ROLLBACK_EVIDENCES_AN_ARTIFACT: Final[str] = "ARK-REQ-0160"
END_TO_END_ROLLBACK_EVIDENCED: Final[str] = "ARK-REQ-0338"
RESTORES_WITHOUT_TRANSFORMATION: Final[str] = "ARK-REQ-0339"


class RecoverySupervisorError(ArkaliError):
    """A rollback was refused before anything was mutated."""

    code = "ARK-ERR-0152"


class HealthCheckResult(BaseModel):
    """A real health signal for one core-upgrade candidate.

    Supplied by the caller - detection is not this authority's concern
    (VDC "Recovery Supervisor": launch -> health failure -> rollback).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    candidate_id: str = Field(min_length=1)
    healthy: bool
    detail: str = Field(min_length=1)


@runtime_checkable
class RollbackAuthorization(Protocol):
    """Structural view of the real PDP-mediated `ROLLBACK_STABLE` grant.

    See the module docstring for why this is a `Protocol` and not an import.
    """

    def authorize(self, *, target_verified_immutable: bool) -> None:
        """Raise (`PolicyDenied`) unless the real PDP grants this exact
        rollback `AUTO`. The implementation is responsible for stating
        `actor`/`trust_tier`/`operation_class` truthfully to the real PDP;
        this module supplies only the one fact it alone can compute honestly.
        """
        ...


@runtime_checkable
class EvidenceSink(Protocol):
    """Structural view of `evidence.audit.AuditChain`'s append/read surface,
    reduced to primitive facts only. See the module docstring for why this is
    a `Protocol` and not an import.
    """

    def append_evidence(
        self, *, requirement_id: str, artifact_id: str, producer: str,
        result: str, contract_id: str, test_id: str,
    ) -> str:
        """Append one evidence record; return its `record_hash`."""
        ...

    def evidence_requirement_results(self) -> tuple[tuple[str, str], ...]:
        """Every recorded `(requirement_id, result)` pair, in any order."""
        ...


class RollbackRecord(BaseModel):
    """C-32: what one rollback proved. Built from what actually happened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_revision_id: str | None
    to_revision_id: str
    candidate_id: str
    reason: str
    performed_at: dt.datetime
    evidence_record_hashes: tuple[str, ...]


class RecoverySupervisor:
    """The deterministic authority behind every real Stable rollback.

    Construct with real, already-loaded authorities - the composition root
    loads the pointer and adapts the real policy/evidence authorities once,
    the same discipline every other orchestrator in this build
    (`MigrationSafetySequence`, `RecoveryService`) already follows.
    """

    def __init__(
        self,
        authorization: RollbackAuthorization,
        pointer: StableRevisionPointer,
        artifacts: ArtifactStore,
        evidence: EvidenceSink,
    ) -> None:
        self._authorization = authorization
        self._pointer = pointer
        self._artifacts = artifacts
        self._evidence = evidence

    def rollback(
        self, *, health: HealthCheckResult, target_revision_id: str
    ) -> RollbackRecord:
        """Roll a failed candidate's Stable revision back to a known-good one.

        Refuses before anything is written if the candidate is reported
        healthy, or if the target is not a revision this pointer itself ever
        recorded - the PDP enforces the second refusal (`PolicyDenied`), not
        a convention this module could get wrong.
        """
        if health.healthy:
            raise RecoverySupervisorError(
                "rollback refused: candidate "
                f"{health.candidate_id!r} is reported healthy; ROLLBACK_STABLE "
                "exists only to recover from a failed upgrade"
            )
        verified = self._pointer.is_previously_verified(target_revision_id)
        self._authorization.authorize(target_verified_immutable=verified)

        from_record = self._pointer.current()
        to_record = self._pointer.rollback_to(target_revision_id)
        performed_at = dt.datetime.now(dt.UTC)
        reason = f"health check failed for {health.candidate_id}: {health.detail}"

        artifact_id = self._register_rollback_artifact(
            from_revision_id=from_record.revision_id if from_record else None,
            to_revision_id=to_record.revision_id,
            candidate_id=health.candidate_id,
            reason=reason,
            performed_at=performed_at,
        )
        hashes = self._emit_evidence(artifact_id, health.candidate_id)

        return RollbackRecord(
            from_revision_id=from_record.revision_id if from_record else None,
            to_revision_id=to_record.revision_id,
            candidate_id=health.candidate_id,
            reason=reason,
            performed_at=performed_at,
            evidence_record_hashes=hashes,
        )

    def is_verified(self) -> bool:
        """Whether this repository's evidence chain proves a real end-to-end
        rollback ever completed. Re-derived from the evidence sink on every
        call - never cached, never settable.
        """
        return any(
            requirement_id == END_TO_END_ROLLBACK_EVIDENCED
            and result == HonestState.PASS.value
            for requirement_id, result in self._evidence.evidence_requirement_results()
        )

    def _register_rollback_artifact(
        self,
        *,
        from_revision_id: str | None,
        to_revision_id: str,
        candidate_id: str,
        reason: str,
        performed_at: dt.datetime,
    ) -> str:
        payload = json.dumps(
            {
                "contract": CONTRACT_ID,
                "from_revision_id": from_revision_id,
                "to_revision_id": to_revision_id,
                "candidate_id": candidate_id,
                "reason": reason,
                "performed_at": performed_at.isoformat(),
                "transformation": "none - atomic identity pointer switch only",
            },
            sort_keys=True,
        ).encode("utf-8")
        return self._artifacts.register(
            payload,
            ProvenanceInput(
                producer_agent=PRODUCER,
                provider_model="none",
                task_id=candidate_id,
                specification_version=CONTRACT_ID,
                context_hash=to_revision_id,
            ),
        )

    def _emit_evidence(self, artifact_id: str, candidate_id: str) -> tuple[str, ...]:
        hashes = []
        for requirement_id in (
            EVERY_ROLLBACK_EVIDENCES_AN_ARTIFACT,
            END_TO_END_ROLLBACK_EVIDENCED,
            RESTORES_WITHOUT_TRANSFORMATION,
        ):
            record_hash = self._evidence.append_evidence(
                requirement_id=requirement_id,
                artifact_id=artifact_id,
                producer=PRODUCER,
                result=HonestState.PASS.value,
                contract_id=CONTRACT_ID,
                test_id=candidate_id,
            )
            hashes.append(record_hash)
        return tuple(hashes)
