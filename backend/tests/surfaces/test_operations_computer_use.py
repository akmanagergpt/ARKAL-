"""C-34 Computer-Use authorization composition (ARK-REQ-0170): the real
`control.policy` PDP, composed unmodified, decides every Computer-Use action.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.surfaces.operations.computer_use import (
    ACTOR,
    authorize_computer_use_action,
)
from arkali.surfaces.operations.computer_use_contracts import ASK_USER, AUTO, DENY

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


class TestAuthorizeComputerUseActionComposesTheRealPdp:
    def test_the_canonical_actor_label_is_used(self) -> None:
        assert ACTOR == "computer_use_worker"

    def test_a_local_process_run_at_trust_1_is_auto(self, pdp: PolicyDecisionPoint) -> None:
        result = authorize_computer_use_action(
            pdp, operation_class="RUN_PROCESS", trust_tier="TRUST-1",
        )
        assert result.decision == AUTO
        assert result.permits_execution
        assert result.operation_class == "RUN_PROCESS"

    def test_external_browsing_asks_a_human_by_default(self, pdp: PolicyDecisionPoint) -> None:
        result = authorize_computer_use_action(
            pdp, operation_class="BROWSER_EXTERNAL", trust_tier="TRUST-1",
        )
        assert result.decision == ASK_USER
        assert not result.permits_execution

    def test_external_browsing_is_denied_under_local_only(self, pdp: PolicyDecisionPoint) -> None:
        result = authorize_computer_use_action(
            pdp, operation_class="BROWSER_EXTERNAL", trust_tier="TRUST-1", local_only=True,
        )
        assert result.decision == DENY

    def test_installing_system_software_is_never_automatic(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        for tier in ("TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"):
            result = authorize_computer_use_action(
                pdp, operation_class="INSTALL_SYSTEM_SOFTWARE", trust_tier=tier,
            )
            assert result.decision != AUTO, f"tier {tier} allowed AUTO install"

    def test_stable_writes_are_refused_regardless_of_facts_supplied(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        result = authorize_computer_use_action(
            pdp, operation_class="WRITE_STABLE_FILE", trust_tier="TRUST-1",
            facts={"within_preauthorized_scope": True}, local_only=True,
        )
        assert result.decision == DENY

    def test_render_includes_the_operation_and_the_decision(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        result = authorize_computer_use_action(
            pdp, operation_class="RUN_PROCESS", trust_tier="TRUST-1",
        )
        text = result.render()
        assert "RUN_PROCESS" in text
        assert result.decision in text


class TestAFixtureDoubleProvesTheProtocolIsGenuinelyStructural:
    """NEGATIVE CONTROL: a non-PDP object matching only the `Protocol`'s
    shape is accepted, proving `authorize_computer_use_action` depends on
    the structural interface, not the concrete `PolicyDecisionPoint` type."""

    class _FixedDecision:
        def decide_computer_use(self, **_kwargs: object) -> tuple[str, str, str | None]:
            return "DENY", "fixture always denies", None

    def test_a_structural_double_is_accepted(self) -> None:
        result = authorize_computer_use_action(
            self._FixedDecision(), operation_class="RUN_PROCESS", trust_tier="TRUST-1",
        )
        assert result.decision == DENY
        assert result.reason == "fixture always denies"
