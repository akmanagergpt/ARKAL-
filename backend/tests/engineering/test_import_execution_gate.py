"""TRUST-3 execution gate: isolation AND human approval, neither substitutes.

Phase 19 Package 3. ARK-REQ-0116 ("TRUST-3 human approval before first
execution", owner control.policy, evidence human) and ARK-REQ-0348 condition
7 ("execution is DENY where the tier's required security properties cannot
be established").
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest

from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
)
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.engineering.project_import.execution_gate import assert_execution_approved
from arkali.engineering.project_import.errors import RescueBoundaryViolationError
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
TIER_REF: Final[str] = "sha256:" + "d" * 64


@pytest.fixture()
def isolation_authority() -> IsolationAuthority:
    return IsolationAuthority.load(REPO)


@pytest.fixture()
def approval_gate() -> WorkflowApprovalGate:
    return WorkflowApprovalGate.load(REPO)


def _satisfied_backends(authority: IsolationAuthority) -> tuple[BackendDescriptor, ...]:
    """Every declared backend claiming PASS for every property it may
    provide - a composition-root double proving the ALLOW path exists,
    without asserting this real host has TRUST-3 capability it does not
    (`BUILD_STATE.md`: TRUST-2/3/4 UNSUPPORTED here)."""
    declared = authority.declared_backends()
    return tuple(
        BackendDescriptor(name=name, provides=provides, availability=HonestState.PASS)
        for name, provides in declared.items()
    )


class TestIsolationMustBeSatisfiable:
    def test_no_available_backends_denies_regardless_of_approval(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve("TRUST-3", available=())
        with pytest.raises(RescueBoundaryViolationError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="human_reviewer",
                approval_binding_hash=TIER_REF,
                tier_assignment_ref=TIER_REF,
            )

    def test_this_real_host_denies_trust_3_honestly(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        """A real, un-doubled probe of this host. TRUST-3 needs
        KERNEL_ISOLATION, which is UNSUPPORTED on an unconfigured host per
        BUILD_STATE.md - this must fail closed, not silently succeed."""
        from arkali.control.isolation.backend_probe import probe_all

        backends = probe_all(isolation_authority, REPO)
        resolution = isolation_authority.resolve("TRUST-3", backends)
        if resolution.execution_decision == "ALLOW":
            pytest.skip("this host genuinely satisfies TRUST-3 isolation")
        with pytest.raises(RescueBoundaryViolationError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="human_reviewer",
                approval_binding_hash=TIER_REF,
                tier_assignment_ref=TIER_REF,
            )

    def test_satisfied_isolation_and_approval_together_permit(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            "TRUST-3", _satisfied_backends(isolation_authority)
        )
        assert resolution.execution_decision == "ALLOW"
        assert_execution_approved(
            isolation_resolution=resolution,
            approval_gate=approval_gate,
            decision="APPROVED",
            actor="human_reviewer",
            approval_binding_hash=TIER_REF,
            tier_assignment_ref=TIER_REF,
        )  # does not raise


class TestApprovalMustBeGenuinelyHuman:
    def test_an_automated_actor_cannot_approve_its_own_import(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            "TRUST-3", _satisfied_backends(isolation_authority)
        )
        with pytest.raises(RescueBoundaryViolationError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="ai_agent",
                approval_binding_hash=TIER_REF,
                tier_assignment_ref=TIER_REF,
            )

    def test_a_rejection_never_permits(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            "TRUST-3", _satisfied_backends(isolation_authority)
        )
        with pytest.raises(RescueBoundaryViolationError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="REJECTED",
                actor="human_reviewer",
                approval_binding_hash=TIER_REF,
                tier_assignment_ref=TIER_REF,
            )

    def test_an_approval_bound_to_a_stale_tier_assignment_never_permits(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        """An approval granted for one tier assignment must not silently
        authorise a different one a later (re-)inspection produced."""
        resolution = isolation_authority.resolve(
            "TRUST-3", _satisfied_backends(isolation_authority)
        )
        with pytest.raises(RescueBoundaryViolationError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="human_reviewer",
                approval_binding_hash="sha256:" + "e" * 64,
                tier_assignment_ref=TIER_REF,
            )
