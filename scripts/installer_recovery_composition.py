"""Phase 29 composition root for the existing C-32 Recovery Supervisor.

This module owns no rollback decision, pointer mutation, evidence format, or
installer state. It adapts the already-accepted PDP/PEP and AuditChain to the
two Protocols declared by ``lifecycle.recovery.RecoverySupervisor`` and calls
that sole authority after the installer journey supplies a real failed health
result.
"""

from __future__ import annotations

import pathlib

from sqlalchemy.orm import Session

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore
from arkali.evidence.audit.chain import AuditChain, EvidenceInput
from arkali.lifecycle.recovery.recovery_supervisor import (
    ACTOR,
    ROLLBACK_OPERATION,
    TRUST_TIER,
    HealthCheckResult,
    RecoverySupervisor,
    RollbackRecord,
)
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer


class _AuditEvidenceAdapter:
    def __init__(self, chain: AuditChain) -> None:
        self._chain = chain

    def append_evidence(
        self,
        *,
        requirement_id: str,
        artifact_id: str,
        producer: str,
        result: str,
        contract_id: str,
        test_id: str,
    ) -> str:
        record = self._chain.append(
            EvidenceInput(
                requirement_id=requirement_id,
                artifact_id=artifact_id,
                producer=producer,
                result=result,
                contract_id=contract_id,
                test_id=test_id,
            )
        )
        return record.record_hash

    def evidence_requirement_results(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (record.requirement_id, record.result) for record in self._chain.records()
        )


class _PepRollbackAdapter:
    def __init__(self, pep: PolicyEnforcementPoint) -> None:
        self._pep = pep

    def authorize(self, *, target_verified_immutable: bool) -> None:
        self._pep.require_auto(
            PolicyRequest(
                operation_class=ROLLBACK_OPERATION,
                trust_tier=TRUST_TIER,
                actor=ACTOR,
                rollback_target_verified_immutable=target_verified_immutable,
            )
        )


def recover_failed_installer_upgrade(
    *,
    session: Session,
    pep: PolicyEnforcementPoint,
    pointer: StableRevisionPointer,
    blobs: ArtifactBlobStore,
    candidate_id: str,
    target_revision_id: str,
    failure_detail: str,
) -> RollbackRecord:
    """Submit one real failed-upgrade health result to the sole C-32 authority."""
    supervisor = RecoverySupervisor(
        _PepRollbackAdapter(pep),
        pointer,
        ArtifactStore(session, blobs),
        _AuditEvidenceAdapter(AuditChain(session, pep, pathlib_root())),
    )
    return supervisor.rollback(
        health=HealthCheckResult(
            candidate_id=candidate_id,
            healthy=False,
            detail=failure_detail,
        ),
        target_revision_id=target_revision_id,
    )


def pathlib_root() -> pathlib.Path:
    """Resolve repository documents for the existing AuditChain authority."""
    return pathlib.Path(__file__).resolve().parents[1]
