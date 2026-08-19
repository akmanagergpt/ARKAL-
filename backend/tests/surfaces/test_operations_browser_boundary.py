"""C-34 permission-aware browser interaction (ARK-REQ-0170): the real PDP
decision, honestly NOT_CONFIGURED for launch (no driver dependency exists
on this host).
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.surfaces.operations.browser_boundary import authorize_browser_navigation

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


class TestBrowserAuthorizationIsRealButLaunchIsHonest:
    def test_a_loopback_local_navigation_is_auto_but_never_executed(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        outcome = authorize_browser_navigation(
            pdp, external=False, trust_tier="TRUST-1", target_is_loopback=True,
        )
        assert outcome.decision.permits_execution
        assert not outcome.executed
        assert "NOT_CONFIGURED" in outcome.stderr or "driver" in outcome.stderr

    def test_external_navigation_asks_a_human_by_default(self, pdp: PolicyDecisionPoint) -> None:
        outcome = authorize_browser_navigation(pdp, external=True, trust_tier="TRUST-1")
        assert outcome.decision.decision == "ASK_USER"
        assert not outcome.executed

    def test_external_navigation_is_denied_under_local_only(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        outcome = authorize_browser_navigation(
            pdp, external=True, trust_tier="TRUST-1", local_only=True,
        )
        assert outcome.decision.decision == "DENY"
        assert not outcome.executed

    def test_never_claims_execution_it_did_not_perform(self, pdp: PolicyDecisionPoint) -> None:
        for external in (False, True):
            outcome = authorize_browser_navigation(pdp, external=external, trust_tier="TRUST-1")
            assert outcome.executed is False
