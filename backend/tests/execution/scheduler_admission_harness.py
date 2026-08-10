"""Shared harness for the C-21 admission tiers (Phase 8 Package 2).

Not a test module. It exists because `module <= 400 logical lines` is a real
architecture budget and ADR-0008 makes decomposition the answer rather than an
exception; it follows the `durable_harness.py` precedent.

REAL MECHANISMS, GOVERNED DATA AS FIXTURE. The PDP, the PEP, the
`IsolationAuthority`, the isolation probes and the `CapabilityGraph` are all the
shipping classes. What varies between cases is governed *data*: a copied
authority map that denies `READ_FILE`, or a graph whose `current_phase` equals
its `activation_phase`.

THE ONLY TEST DOUBLE IS A CAPABILITY RESOLVER, AND IT LIVES HERE, NOT IN
`arkali`.
Production capability is `NOT_CONFIGURED` until Phase 9B, so the ADMITTED branch
cannot be reached with the real pre-activation graph. `ResolverSpy` implements
the same `can_perform` question in order to prove the other two conditions and
the composition are correct. A structural control asserts nothing under
`backend/arkali/` defines `can_perform` outside `control.capability`, so this
double cannot be substituted into production.
"""

from __future__ import annotations

import pathlib
import shutil

import yaml

from arkali.control.capability.capability_graph import (
    CapabilityGraph,
    CapabilityQueryResult,
)
from arkali.control.capability.capability_node import CapabilityNode
from arkali.control.isolation.backend_probe import probe_all
from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
)
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.execution.scheduler.admission import AdmissionRequest, AdmissionService
from arkali.execution.scheduler.capability_admission import CapabilityAdmission
from arkali.execution.scheduler.isolation_admission import IsolationAdmission
from arkali.execution.scheduler.resource_admission import (
    ResourceAdmission,
    ResourceAvailability,
)
from arkali.execution.scheduler.worker_contract import READ, WorkerContract
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]

#: `ARK-REQ-0048` puts activation at 9B; the register's Phase column is the
#: authority and this mirrors it for fixture construction only.
ACTIVATION_PHASE = "9B"
PRE_ACTIVATION_PHASE = "8"

CAPABILITY_ID = "build.compile"
PROFILE = "standard"

DOCUMENTS = (
    "docs/canonical/AUTHORITY_MAP.yaml",
    "docs/canonical/SECURITY_ARCHITECTURE.md",
    "docs/canonical/ARCHITECTURE.md",
    "docs/canonical/EXECUTION_AND_CAPABILITY.md",
)


def node(capability_id: str = CAPABILITY_ID, tier: str = "TRUST-0") -> CapabilityNode:
    return CapabilityNode(id=capability_id, version=1, isolation_tier=tier)


def real_graph(current_phase: str = PRE_ACTIVATION_PHASE) -> CapabilityGraph:
    """The SHIPPING CapabilityGraph. Only the node set is a fixture."""
    return CapabilityGraph(
        [node()], activation_phase=ACTIVATION_PHASE, current_phase=current_phase
    )


class ResolverSpy:
    """A test-only capability resolver that counts how often it was asked.

    Counting is the point: proving a verdict is not cached needs evidence that
    the AUTHORITY was re-queried, not merely that the caller called twice.
    """

    def __init__(self, state: HonestState = HonestState.PASS, reason: str = "") -> None:
        self.state = state
        self.reason = reason or f"test resolver returning {state.value}"
        self.calls: list[str] = []

    def can_perform(self, capability_id: str) -> CapabilityQueryResult:
        self.calls.append(capability_id)
        return CapabilityQueryResult(
            capability_id=capability_id,
            state=self.state,
            reason=self.reason,
            authoritative_source="test-only resolver",
        )


def real_pep(root: pathlib.Path = REPO) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(
        PolicyDecisionPoint.load(root), "execution.scheduler.admission"
    )


def denying_pep(root: pathlib.Path) -> PolicyEnforcementPoint:
    """A REAL PEP over a REAL PDP whose authority map denies `READ_FILE`."""
    for relative in DOCUMENTS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    path = root / "docs/canonical/AUTHORITY_MAP.yaml"
    mapping = yaml.safe_load(path.read_text(encoding="utf-8"))
    mapping["operation_classes"][READ] = {"default": "DENY", "fixed": "DENY"}
    path.write_text(yaml.safe_dump(mapping), encoding="utf-8")
    return PolicyEnforcementPoint(PolicyDecisionPoint.load(root), "denied")


def probed_backends(
    root: pathlib.Path = REPO,
) -> tuple[BackendDescriptor, ...]:
    """The real canonical probes against the real host."""
    return probe_all(IsolationAuthority.load(root), root)


def unavailable_backends() -> tuple[BackendDescriptor, ...]:
    """Nothing available. Every tier above TRUST-0 becomes unsatisfiable."""
    return ()


def build_service(
    *,
    resolver: object,
    pep: PolicyEnforcementPoint | None = None,
    backends: object = None,
    root: pathlib.Path = REPO,
) -> AdmissionService:
    """Compose the shipping AdmissionService from the shipping parts."""
    enforcement = pep if pep is not None else real_pep(root)
    source = backends if backends is not None else probed_backends
    return AdmissionService(
        WorkerContract(root, enforcement),
        CapabilityAdmission(resolver),  # type: ignore[arg-type]
        IsolationAdmission(IsolationAuthority.load(root), source),  # type: ignore[arg-type]
        ResourceAdmission(),
        enforcement,
    )


def availability(in_flight: int = 0, profiles: tuple[str, ...] = (PROFILE,)) -> (
    ResourceAvailability
):
    return ResourceAvailability(in_flight=in_flight, available_profiles=profiles)


def request(
    worker_class: str,
    *,
    in_flight: int = 0,
    profiles: tuple[str, ...] = (PROFILE,),
    capability_id: str = CAPABILITY_ID,
) -> AdmissionRequest:
    return AdmissionRequest(
        worker_class=worker_class,
        capability_id=capability_id,
        availability=availability(in_flight, profiles),
    )
