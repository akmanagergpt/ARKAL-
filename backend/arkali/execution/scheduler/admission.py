"""The C-21 admission decision: all three canonical conditions, composed.

Owner: `execution.scheduler`.

`EXECUTION_AND_CAPABILITY.md` §4: "a job is admitted only when (a) its capability
resolves other than `NOT_CONFIGURED`, (b) an isolation composition satisfies its
tier, and (c) resource budget is available." All three are required. There is no
fourth condition, and no condition may be waived by the presence of another.

WHAT THIS DECIDES AND WHAT IT DOES NOT. It answers whether work *may* be
admitted. It starts nothing: no worker is invoked, assigned, reserved or marked
running, no durable job is read or written, and no capacity is consumed. Nothing
is ordered, prioritised or queued - the canonical set gives Phase 8 no authority
for any of that, and structural controls reject it.

EVALUATION ORDER IS IMPLEMENTATION BEHAVIOUR, NOT CANONICAL MEANING. §4 states
the conditions as a conjunction and defines no order, so the order below -
capability, isolation, resource - is chosen for determinism and for reporting the
most fundamental refusal first. Because the conjunction is what is canonical, the
order can never change *whether* a request is admitted, only which refusal is
reported when more than one condition fails; a control asserts that.

THE CAPABILITY CONDITION CANNOT BE OVERRIDDEN. Short-circuiting means a
`NOT_CONFIGURED` capability returns immediately, so no later condition can
overwrite it - but the guarantee does not rest on ordering. `_compose` requires
all three to hold before it returns ADMITTED, so even evaluated in any other
order an unconfigured capability could not produce an admission.

PEP DENIAL IS NOT AN ADMISSION OUTCOME. A policy refusal raises `PolicyDenied`
and never becomes a capability, isolation or resource verdict. Those three say
"the canonical conditions were evaluated and one did not hold"; a denial says the
evaluation was not permitted to happen at all, and collapsing the two would let a
policy failure read as an ordinary infrastructure shortage.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.execution.scheduler.admission_result import (
    AdmissionDecision,
    AdmissionOutcome,
)
from arkali.execution.scheduler.capability_admission import (
    CapabilityAdmission,
    resolves,
)
from arkali.execution.scheduler.isolation_admission import IsolationAdmission
from arkali.execution.scheduler.resource_admission import (
    ResourceAdmission,
    ResourceAvailability,
)
from arkali.execution.scheduler.worker_contract import (
    ACTOR,
    READ,
    TRUST_TIER,
    WorkerContract,
    WorkerDeclaration,
)


class AdmissionRequest(BaseModel):
    """One candidate piece of work, described by the caller.

    A value object rather than four parameters, and the reason it exists at all
    is the boundary: the scheduler is told what is being asked of it and never
    goes looking. It holds no durable job id, no lifecycle state and no handle
    to `execution.durable` - a legal higher-layer caller supplies these facts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    worker_class: str
    capability_id: str
    availability: ResourceAvailability


class AdmissionService:
    """Composes the three canonical conditions into one deterministic answer."""

    def __init__(
        self,
        contract: WorkerContract,
        capability: CapabilityAdmission,
        isolation: IsolationAdmission,
        resource: ResourceAdmission,
        pep: PolicyEnforcementPoint,
    ) -> None:
        self._contract = contract
        self._capability = capability
        self._isolation = isolation
        self._resource = resource
        self._pep = pep

    def _guard(self) -> None:
        """Reading the canonical admission authorities is a governed read.

        The same `READ_FILE` class and the same PEP instance Package 1 uses. No
        second enforcement path and no new operation class: an admission
        evaluation reads the capability graph and the isolation authority, which
        is what the class already describes.
        """
        self._pep.require_auto(
            PolicyRequest(operation_class=READ, trust_tier=TRUST_TIER, actor=ACTOR)
        )

    def evaluate(self, request: AdmissionRequest) -> AdmissionDecision:
        """Answer §4 for one request. Decides only; changes nothing."""
        self._guard()
        declaration = self._contract.require(request.worker_class)
        return self._compose(request, declaration)

    def _compose(
        self, request: AdmissionRequest, declaration: WorkerDeclaration
    ) -> AdmissionDecision:
        capability = self._capability.evaluate(request.capability_id)
        if not resolves(capability):
            return self._decide(
                request, AdmissionOutcome.CAPABILITY_NOT_CONFIGURED, capability.reason
            )
        isolation = self._isolation.evaluate(
            declaration.required_trust_tier,
            declaration.required_isolation_properties,
        )
        if not isolation.satisfied:
            return self._decide(
                request, AdmissionOutcome.ISOLATION_UNSATISFIED, isolation.reason
            )
        resource = self._resource.evaluate(
            declaration.concurrency_limit,
            declaration.resource_profile,
            request.availability,
        )
        if not resource.satisfied:
            return self._decide(
                request, AdmissionOutcome.RESOURCE_UNAVAILABLE, resource.reason
            )
        return self._decide(
            request,
            AdmissionOutcome.ADMITTED,
            f"capability {capability.state.value}; {isolation.reason}; "
            f"{resource.reason}",
        )

    @staticmethod
    def _decide(
        request: AdmissionRequest, outcome: AdmissionOutcome, reason: str
    ) -> AdmissionDecision:
        return AdmissionDecision(
            worker_class=request.worker_class,
            capability_id=request.capability_id,
            outcome=outcome,
            reason=reason,
        )
