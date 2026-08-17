"""TRUST-4 execution gate: isolation AND human approval per execution.

Phase 21 Package 3. ARK-REQ-0117 ("TRUST-4 human approval per execution",
owner control.policy, evidence human) - the TRUST-4 analogue of Phase 19's
TRUST-3 execution gate (`engineering.import.execution_gate`), reused
mechanism, stricter binding: an approval is scoped to one execution attempt,
not to a standing tier assignment.
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
from arkali.engineering.plugin.errors import PluginExecutionRefusedError
from arkali.engineering.plugin.trust4_execution_gate import (
    TRUST_TIER,
    assert_execution_approved,
    execution_binding_ref,
)
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture()
def isolation_authority() -> IsolationAuthority:
    return IsolationAuthority.load(REPO)


@pytest.fixture()
def approval_gate() -> WorkflowApprovalGate:
    return WorkflowApprovalGate.load(REPO)


def _satisfied_backends(authority: IsolationAuthority) -> tuple[BackendDescriptor, ...]:
    """Every declared backend claiming PASS for every property it may
    provide - a composition-root double proving the ALLOW path exists,
    without asserting this real host has TRUST-4 capability it does not
    (`BUILD_STATE.md`: TRUST-2/3/4 UNSUPPORTED here)."""
    declared = authority.declared_backends()
    return tuple(
        BackendDescriptor(name=name, provides=provides, availability=HonestState.PASS)
        for name, provides in declared.items()
    )


def _ref(nonce: str) -> str:
    return execution_binding_ref(
        plugin_id="acme.example-plugin",
        manifest_ref="sha256:" + "a" * 64,
        action="fetch_advisory",
        execution_nonce=nonce,
    )


class TestExecutionBindingRefIsUniquePerAttempt:
    def test_two_different_nonces_bind_differently(self) -> None:
        assert _ref("attempt-1") != _ref("attempt-2")

    def test_the_same_facts_bind_identically(self) -> None:
        assert _ref("attempt-1") == _ref("attempt-1")

    def test_a_changed_action_changes_the_binding(self) -> None:
        first = execution_binding_ref(
            plugin_id="acme.x", manifest_ref="sha256:" + "b" * 64,
            action="read", execution_nonce="n1",
        )
        second = execution_binding_ref(
            plugin_id="acme.x", manifest_ref="sha256:" + "b" * 64,
            action="write", execution_nonce="n1",
        )
        assert first != second

    def test_ref_is_a_canonical_content_address(self) -> None:
        from arkali.kernel.contracts.content_address import is_address

        assert is_address(_ref("attempt-1"))


class TestIsolationMustBeSatisfiable:
    def test_no_available_backends_denies_regardless_of_approval(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(TRUST_TIER, available=())
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="human_reviewer",
                approval_binding_hash=_ref("attempt-1"),
                execution_ref=_ref("attempt-1"),
            )

    def test_this_real_host_denies_trust_4_honestly(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        """A real, un-doubled probe of this host. TRUST-4 needs
        KERNEL_ISOLATION + DISPOSABILITY, which are UNSUPPORTED on an
        unconfigured host per BUILD_STATE.md - this must fail closed, not
        silently succeed."""
        from arkali.control.isolation.backend_probe import probe_all

        backends = probe_all(isolation_authority, REPO)
        resolution = isolation_authority.resolve(TRUST_TIER, backends)
        if resolution.execution_decision == "ALLOW":
            pytest.skip("this host genuinely satisfies TRUST-4 isolation")
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="human_reviewer",
                approval_binding_hash=_ref("attempt-1"),
                execution_ref=_ref("attempt-1"),
            )

    def test_satisfied_isolation_and_approval_together_permit(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            TRUST_TIER, _satisfied_backends(isolation_authority)
        )
        assert resolution.execution_decision == "ALLOW"
        assert_execution_approved(
            isolation_resolution=resolution,
            approval_gate=approval_gate,
            decision="APPROVED",
            actor="human_reviewer",
            approval_binding_hash=_ref("attempt-1"),
            execution_ref=_ref("attempt-1"),
        )  # does not raise

    def test_wrong_tier_resolution_is_refused(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        """ARK-REQ-0117 governs TRUST-4 only; a TRUST-3 resolution must not
        be silently accepted by this gate."""
        resolution = isolation_authority.resolve(
            "TRUST-3", _satisfied_backends(isolation_authority)
        )
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="human_reviewer",
                approval_binding_hash=_ref("attempt-1"),
                execution_ref=_ref("attempt-1"),
            )


class TestApprovalMustBeGenuinelyHuman:
    def test_an_automated_actor_cannot_approve_its_own_execution(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            TRUST_TIER, _satisfied_backends(isolation_authority)
        )
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="ai_agent",
                approval_binding_hash=_ref("attempt-1"),
                execution_ref=_ref("attempt-1"),
            )

    def test_a_rejection_never_permits(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            TRUST_TIER, _satisfied_backends(isolation_authority)
        )
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="REJECTED",
                actor="human_reviewer",
                approval_binding_hash=_ref("attempt-1"),
                execution_ref=_ref("attempt-1"),
            )


class TestApprovalIsScopedToExactlyOneExecution:
    """The behaviour that distinguishes TRUST-4 ("per execution") from
    TRUST-3 ("before first execution"): an approval genuinely recorded for
    one execution attempt must never authorise a different one."""

    def test_an_approval_for_a_previous_execution_does_not_authorise_the_next(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            TRUST_TIER, _satisfied_backends(isolation_authority)
        )
        # A genuine APPROVED decision exists, but it was bound to attempt-1.
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="human_reviewer",
                approval_binding_hash=_ref("attempt-1"),
                execution_ref=_ref("attempt-2"),
            )

    def test_two_consecutive_executions_each_require_their_own_approval(
        self, isolation_authority: IsolationAuthority, approval_gate: WorkflowApprovalGate
    ) -> None:
        resolution = isolation_authority.resolve(
            TRUST_TIER, _satisfied_backends(isolation_authority)
        )
        # attempt-1 is genuinely approved for attempt-1.
        assert_execution_approved(
            isolation_resolution=resolution,
            approval_gate=approval_gate,
            decision="APPROVED",
            actor="human_reviewer",
            approval_binding_hash=_ref("attempt-1"),
            execution_ref=_ref("attempt-1"),
        )
        # attempt-2 requires its own — attempt-1's approval does not carry over.
        with pytest.raises(PluginExecutionRefusedError):
            assert_execution_approved(
                isolation_resolution=resolution,
                approval_gate=approval_gate,
                decision="APPROVED",
                actor="human_reviewer",
                approval_binding_hash=_ref("attempt-1"),
                execution_ref=_ref("attempt-2"),
            )
        # attempt-2 genuinely approved for attempt-2 succeeds.
        assert_execution_approved(
            isolation_resolution=resolution,
            approval_gate=approval_gate,
            decision="APPROVED",
            actor="human_reviewer",
            approval_binding_hash=_ref("attempt-2"),
            execution_ref=_ref("attempt-2"),
        )
