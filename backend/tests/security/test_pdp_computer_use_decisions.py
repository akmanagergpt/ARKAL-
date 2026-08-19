"""`PolicyDecisionPoint.decide_computer_use` (ARK-REQ-0170, Phase 25): the
primitive-in/primitive-out entry point Computer-Use uses because
`control.policy.pep`/`.policy_contract` are both already at their 15-of-15
fan-in ceiling (mirrors `decide_network_egress`'s own established shape).

Every expectation is derived from `SECURITY_ARCHITECTURE.md` §2, the same
canonical matrix `test_pdp_decisions.py` already asserts against for the
general `decide`/`decide_or_deny_unmapped` entry points - this file proves
the new method agrees with them, not a second copy of the table.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.policy_contract import PolicyRequest

REPO = pathlib.Path(__file__).resolve().parents[3]
ACTOR = "computer_use_worker"


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


class TestDecideComputerUseAgreesWithTheGeneralEntryPoint:
    """For every real request, `decide_computer_use` and `decide` must
    resolve to the identical decision - proving the primitive shortcut is
    not a second, independently-drifting policy model."""

    @pytest.mark.parametrize(
        ("operation_class", "tier", "facts", "local_only"),
        [
            ("RUN_PROCESS", "TRUST-1", {}, False),
            ("RUN_PROCESS", "TRUST-3", {}, False),
            ("TERMINATE_PROCESS", "TRUST-1", {"target_is_own_process": True}, False),
            ("BROWSER_LOCAL", "TRUST-1", {"target_is_loopback": True}, False),
            ("BROWSER_EXTERNAL", "TRUST-1", {}, False),
            ("BROWSER_EXTERNAL", "TRUST-1", {}, True),
            ("INSTALL_DEPENDENCY", "TRUST-1", {"lockfile_bound": True}, False),
            ("INSTALL_SYSTEM_SOFTWARE", "TRUST-1", {}, False),
            ("CHANGE_SYSTEM_CONFIGURATION", "TRUST-1", {}, False),
            ("ACCESS_SECRET", "TRUST-1", {"within_preauthorized_scope": True}, False),
            ("ACCESS_SECRET", "TRUST-1", {"within_preauthorized_scope": False}, False),
            ("WRITE_STABLE_FILE", "TRUST-1", {}, False),
            ("READ_FILE", "TRUST-1", {}, False),
        ],
    )
    def test_the_two_entry_points_never_diverge(
        self, pdp: PolicyDecisionPoint, operation_class: str, tier: str,
        facts: dict, local_only: bool,
    ) -> None:
        via_primitive = pdp.decide_computer_use(
            operation_class=operation_class, trust_tier=tier, actor=ACTOR,
            facts=facts, local_only=local_only,
        )
        via_request = pdp.decide(
            PolicyRequest(
                operation_class=operation_class, trust_tier=tier, actor=ACTOR,
                local_only=local_only,
                target_is_loopback=facts.get("target_is_loopback"),
                target_is_own_process=facts.get("target_is_own_process"),
                within_preauthorized_scope=facts.get("within_preauthorized_scope"),
                lockfile_bound=facts.get("lockfile_bound"),
            )
        )
        assert via_primitive[0] == via_request.decision.value
        assert via_primitive[2] == via_request.required_human_gate


class TestComputerUseCannotEverWriteStable:
    """WRITE_STABLE_FILE is DENY for every actor, always - re-verified here
    for the Computer-Use actor specifically, at every declared trust tier."""

    @pytest.mark.parametrize("tier", ["TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4"])
    def test_write_stable_file_is_always_deny(self, pdp: PolicyDecisionPoint, tier: str) -> None:
        decision, _reason, _gate = pdp.decide_computer_use(
            operation_class="WRITE_STABLE_FILE", trust_tier=tier, actor=ACTOR,
        )
        assert decision == "DENY"

    def test_rollback_stable_is_always_deny_for_computer_use(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        decision, _reason, _gate = pdp.decide_computer_use(
            operation_class="ROLLBACK_STABLE", trust_tier="TRUST-1", actor=ACTOR,
        )
        assert decision == "DENY"


class TestAnUnmappableActionIsRecordedDenyNotAnException:
    def test_an_unknown_operation_class_resolves_to_deny_and_does_not_raise(
        self, pdp: PolicyDecisionPoint,
    ) -> None:
        decision, reason, _gate = pdp.decide_computer_use(
            operation_class="DELETE_THE_INTERNET", trust_tier="TRUST-1", actor=ACTOR,
        )
        assert decision == "DENY"
        assert reason
