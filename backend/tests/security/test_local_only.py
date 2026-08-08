"""Local-Only mode (ARK-REQ-0104, 0105, 0106, 0107).

SECURITY_ARCHITECTURE.md §7: when enabled the PDP returns DENY for all outbound
egress on every path, from every trust tier. Loopback remains permitted so local
build, test and browser verification continue. Enabling or disabling it is
HUMAN GATE 4.

The set of egress-bearing classes is derived from the canonical `fixed` rule
`DENY_IN_LOCAL_ONLY`, not listed here, so a class gaining that rule later is
covered automatically.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.operation_class import Decision, OperationClassVocabulary
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.policy_contract import PolicyRequest

REPO = pathlib.Path(__file__).resolve().parents[3]
TIERS = ("TRUST-0", "TRUST-1", "TRUST-2", "TRUST-3", "TRUST-4")
#: Every actor path §7 names: provider, research, plugin/connector, external
#: browser, agent, workflow.
ACTORS = (
    "control.registry.provider",
    "engineering.knowledge",
    "engineering.plugin",
    "surfaces.operations",
    "engineering.agent",
    "execution.workflow",
)


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture(scope="module")
def egress_classes() -> tuple[str, ...]:
    """Derived from the canonical fixed rule, never listed by hand."""
    vocabulary = OperationClassVocabulary.load(REPO)
    found = tuple(
        name for name in vocabulary.names()
        if vocabulary.get(name).denied_in_local_only
    )
    assert found, "no class carries DENY_IN_LOCAL_ONLY; the control would be vacuous"
    return found


def request_for(operation: str, tier: str, **overrides: object) -> PolicyRequest:
    base: dict[str, object] = {
        "operation_class": operation,
        "trust_tier": tier,
        "actor": "engineering.agent",
    }
    base.update(overrides)
    return PolicyRequest(**base)  # type: ignore[arg-type]


class TestLocalOnlyDeniesEgress:
    def test_the_egress_class_set_is_what_the_canonical_set_declares(
        self, egress_classes: tuple[str, ...]
    ) -> None:
        assert set(egress_classes) == {"BROWSER_EXTERNAL", "NETWORK_EXTERNAL"}

    @pytest.mark.parametrize("tier", TIERS)
    def test_every_egress_class_is_denied_at_every_tier(
        self, pdp: PolicyDecisionPoint, egress_classes: tuple[str, ...], tier: str
    ) -> None:
        """ARK-REQ-0104: DENY on every path, from every tier."""
        for name in egress_classes:
            record = pdp.decide(request_for(name, tier, local_only=True))
            assert record.decision is Decision.DENY

    @pytest.mark.parametrize("actor", ACTORS)
    def test_no_actor_path_bypasses_local_only(
        self, pdp: PolicyDecisionPoint, egress_classes: tuple[str, ...], actor: str
    ) -> None:
        """ARK-REQ-0107: no capability silently degrades to a cloud path."""
        for name in egress_classes:
            record = pdp.decide(
                request_for(name, "TRUST-0", local_only=True, actor=actor)
            )
            assert record.decision is Decision.DENY
            assert "Local-Only" in record.reason

    def test_local_only_cannot_be_widened_by_any_other_fact(
        self, pdp: PolicyDecisionPoint, egress_classes: tuple[str, ...]
    ) -> None:
        for name in egress_classes:
            record = pdp.decide(
                request_for(
                    name,
                    "TRUST-0",
                    local_only=True,
                    target_is_loopback=True,
                    within_preauthorized_scope=True,
                    lockfile_bound=True,
                    isolation_satisfied=True,
                    recorded_human_gates=("HUMAN_GATE_4", "HUMAN_GATE_2"),
                )
            )
            assert record.decision is Decision.DENY


class TestLoopbackSurvives:
    @pytest.mark.parametrize("tier", TIERS)
    def test_loopback_browser_is_still_permitted(
        self, pdp: PolicyDecisionPoint, tier: str
    ) -> None:
        """ARK-REQ-0105: local build, test and browser verification continue."""
        record = pdp.decide(
            request_for(
                "BROWSER_LOCAL", tier, local_only=True, target_is_loopback=True
            )
        )
        assert record.decision is Decision.AUTO

    def test_local_workspace_work_is_unaffected(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        for name in ("READ_FILE", "WRITE_WORKSPACE_FILE"):
            record = pdp.decide(request_for(name, "TRUST-2", local_only=True))
            assert record.decision is Decision.AUTO

    def test_loopback_claim_is_still_required(
        self, pdp: PolicyDecisionPoint
    ) -> None:
        """Local-Only does not relax LOOPBACK_ONLY; an off-loopback target fails."""
        record = pdp.decide(
            request_for(
                "BROWSER_LOCAL", "TRUST-0", local_only=True, target_is_loopback=False
            )
        )
        assert record.decision is Decision.DENY


class TestLocalOnlyToggleIsGated:
    def test_toggling_local_only_is_a_change_of_security_boundary(self) -> None:
        """ARK-REQ-0106: the toggle is HUMAN GATE 4.

        Phase 4 records the requirement structurally: the toggle is a
        Protected Core policy change, `control.policy` is protected, and the
        canonical gate for a security-boundary change is GATE 4. The gate itself
        is a human decision and is not self-produced here.
        """
        import yaml

        raw = yaml.safe_load(
            (REPO / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
        )
        assert raw["human_gates"]["HUMAN_GATE_4"].startswith(
            "Weakening or change of a security boundary"
        )
        assert raw["contexts"]["control.policy"]["protected_core"] is True
