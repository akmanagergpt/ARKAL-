"""Shared test-only composition helpers for `backend/tests/persistence`.

Both adapters below are the composition-root half of the ADR-0008 Protocol
decoupling `recovery_supervisor.py`'s own module docstring explains: a direct
production import of `AuditChain` would extend `evidence.audit`'s own
already-4-of-4 orchestration chain to 5, and a direct production import of
`PolicyEnforcementPoint`/`PolicyRequest` would breach both modules'
already-15-of-15 `max_fan_in_per_module` ceiling and the module's own
`max_contexts_touched_by_module` budget. Both live in the test tier
deliberately: production code sees only the Protocol, and only a composition
root ever constructs the real authority. The real PDP decision and the real
evidence chain still gate/record everything - only the glue code moves here.
"""

from __future__ import annotations

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.evidence.audit.chain import AuditChain, EvidenceInput


class AuditChainEvidenceSink:
    """Real `AuditChain`, exposed through `EvidenceSink`'s primitive surface."""

    def __init__(self, chain: AuditChain) -> None:
        self._chain = chain

    def append_evidence(
        self, *, requirement_id: str, artifact_id: str, producer: str,
        result: str, contract_id: str, test_id: str,
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
        return tuple((r.requirement_id, r.result) for r in self._chain.records())


class PepRollbackAuthorization:
    """Real `PolicyEnforcementPoint`, exposed through
    `RollbackAuthorization`'s single-fact primitive surface.

    `actor`/`trust_tier`/`operation_class` are supplied here, by the
    composition root, exactly as `AUTHORITY_MAP.yaml` declares them - never
    by `recovery_supervisor.py`, which only ever states the one fact it alone
    can compute honestly (`target_verified_immutable`).
    """

    def __init__(self, pep: PolicyEnforcementPoint, *, actor: str, trust_tier: str) -> None:
        self._pep = pep
        self._actor = actor
        self._trust_tier = trust_tier

    def authorize(self, *, target_verified_immutable: bool) -> None:
        self._pep.require_auto(
            PolicyRequest(
                operation_class="ROLLBACK_STABLE",
                trust_tier=self._trust_tier,
                actor=self._actor,
                rollback_target_verified_immutable=target_verified_immutable,
            )
        )
