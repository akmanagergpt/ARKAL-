"""ARK-REQ-0137/0138: `CoreUpgrade` orchestration — snapshot entry and
scoped HUMAN_GATE_2 promotion authorization.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.acceptance.governance_state import GovernanceState
from arkali.kernel.contracts.state_machine_errors import GuardRejected
from arkali.lifecycle.evolution import core_upgrade_state_machine as cusm
from arkali.lifecycle.evolution.core_upgrade_orchestrator import (
    CORE_PROMOTION_OPERATION,
    GATE_2,
    HumanGate2Source,
    authorize_promotion,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


class FakeHumanGate2Source:
    """Structurally satisfies `HumanGate2Source`. Not `GovernanceState`.

    `grants=True` answers every `operation_grant` call affirmatively,
    mirroring `migration_safety` tests' own `FakeHumanGateSource`.
    """

    def __init__(self, grants: bool = False) -> None:
        self._grants = grants

    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str,
        revision_identity: str,
    ) -> bool:
        return self._grants


class RecordingHumanGate2Source:
    """Records every call; grants only an exact pre-set match - a confused-
    deputy proof mirroring `migration_safety`'s own `RecordingHumanGateSource`."""

    def __init__(self, match: tuple[str, str, str, str] | None = None) -> None:
        self._match = match
        self.calls: list[tuple[str, str, str, str]] = []

    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str,
        revision_identity: str,
    ) -> bool:
        call = (gate_id, operation_class, target_identity, revision_identity)
        self.calls.append(call)
        return call == self._match


class TestAuthorizePromotion:
    def test_no_grant_yields_an_unrecorded_context(self) -> None:
        context = authorize_promotion(
            FakeHumanGate2Source(grants=False),
            candidate_manifest_ref="sha256:" + "c" * 64,
            target_revision_id="sha256:" + "d" * 64,
        )
        assert context == {"human_gate_2_recorded": False}

    def test_a_real_grant_yields_a_recorded_context(self) -> None:
        context = authorize_promotion(
            FakeHumanGate2Source(grants=True),
            candidate_manifest_ref="sha256:" + "c" * 64,
            target_revision_id="sha256:" + "d" * 64,
        )
        assert context == {"human_gate_2_recorded": True}

    def test_gate_operation_and_identities_are_presented_exactly(self) -> None:
        manifest_ref = "sha256:" + "c" * 64
        revision_id = "sha256:" + "d" * 64
        recorder = RecordingHumanGate2Source()
        authorize_promotion(
            recorder, candidate_manifest_ref=manifest_ref, target_revision_id=revision_id,
        )
        assert recorder.calls == [
            (GATE_2, CORE_PROMOTION_OPERATION, manifest_ref, revision_id)
        ]

    def test_a_grant_for_a_different_candidate_does_not_satisfy_this_one(self) -> None:
        """Confused-deputy proof: a grant scoped to one candidate's manifest
        must not authorize a different candidate's promotion."""
        exact = RecordingHumanGate2Source(
            match=(GATE_2, CORE_PROMOTION_OPERATION, "sha256:" + "c" * 64, "sha256:" + "d" * 64)
        )
        context = authorize_promotion(
            exact, candidate_manifest_ref="sha256:" + "e" * 64,
            target_revision_id="sha256:" + "d" * 64,
        )
        assert context == {"human_gate_2_recorded": False}


class TestGateTwoGuardComposition:
    """The real `CoreUpgrade.gate_2_guard`, driven by `authorize_promotion`'s
    real output - not a hand-built context dict."""

    def test_no_grant_is_refused_by_the_real_guard(self) -> None:
        machine = cusm.build()
        with pytest.raises(GuardRejected):
            machine.evaluate(
                "AWAITING_GATE_2", "PROMOTED",
                authorize_promotion(
                    FakeHumanGate2Source(grants=False),
                    candidate_manifest_ref="sha256:" + "c" * 64,
                    target_revision_id="sha256:" + "d" * 64,
                ),
            )

    def test_a_real_grant_is_accepted_by_the_real_guard(self) -> None:
        machine = cusm.build()
        outcome = machine.evaluate(
            "AWAITING_GATE_2", "PROMOTED",
            authorize_promotion(
                FakeHumanGate2Source(grants=True),
                candidate_manifest_ref="sha256:" + "c" * 64,
                target_revision_id="sha256:" + "d" * 64,
            ),
        )
        assert outcome.decision.value == "ACCEPTED"


class TestGovernanceStateSatisfiesHumanGate2Source:
    """`acceptance.engine.GovernanceState` is the real, already-accepted
    grant-scoping authority (`migration_safety_types.HumanGateSource`'s own
    real satisfier). No second implementation is introduced here."""

    def test_governance_state_structurally_satisfies_the_protocol(self) -> None:
        state = GovernanceState.load(REPO)
        assert isinstance(state, HumanGate2Source)

    def test_no_grant_exists_yet_for_core_promotion(self) -> None:
        """HUMAN_GATE_2 has no HGR record of any kind yet (confirmed against
        the live repository, not assumed) - so an honest lookup must refuse."""
        state = GovernanceState.load(REPO)
        assert state.operation_grant(
            GATE_2, CORE_PROMOTION_OPERATION,
            "sha256:" + "c" * 64, "sha256:" + "d" * 64,
        ) is False
