"""ARK-REQ-0330: HUMAN APPROVAL as an enforced policy stop (Phase 17 Package 4).

REAL AUTHORITY MAP for the positive path. Negative controls copy and mutate a
real map, so a refusal proven here is the shipping refusal.
"""

from __future__ import annotations

import pathlib
from typing import Any, Final

import pytest
import yaml

from arkali.control.policy.policy_errors import AutomatedActorCannotApprove
from arkali.control.policy.workflow_approval import APPROVED, WorkflowApprovalGate

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
MAP = "docs/canonical/AUTHORITY_MAP.yaml"

REVISION = "sha256:" + "a" * 64
OTHER_REVISION = "sha256:" + "b" * 64


@pytest.fixture(scope="module")
def gate() -> WorkflowApprovalGate:
    return WorkflowApprovalGate.load(REPO)


def canonical() -> dict[str, Any]:
    return yaml.safe_load((REPO / MAP).read_text(encoding="utf-8"))


def write_map(root: pathlib.Path, raw: dict[str, Any]) -> pathlib.Path:
    target = root / MAP
    target.parent.mkdir(parents=True)
    target.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return root


class TestAuthorityIsDerived:
    def test_automated_actors_match_the_canonical_prohibited_list(
        self, gate: WorkflowApprovalGate
    ) -> None:
        raw = canonical()
        assert set(gate.automated_actors()) == set(raw["stable_mutation"]["prohibited_actors"])

    def test_workflow_is_a_declared_automated_actor(self, gate: WorkflowApprovalGate) -> None:
        """The canonical set already names `workflow` - a workflow execution
        path may never supply its own approval."""
        assert "workflow" in gate.automated_actors()

    def test_missing_prohibited_actors_refuses(self, tmp_path: pathlib.Path) -> None:
        raw = canonical()
        raw["stable_mutation"]["prohibited_actors"] = []
        with pytest.raises(Exception, match="no automated"):
            WorkflowApprovalGate.load(write_map(tmp_path, raw))


class TestAutomatedActorsCannotRecordApproval:
    def test_workflow_actor_is_refused_by_type_and_reason(
        self, gate: WorkflowApprovalGate
    ) -> None:
        with pytest.raises(AutomatedActorCannotApprove, match="workflow"):
            gate.assert_may_record("workflow")

    def test_every_declared_automated_actor_is_refused(self, gate: WorkflowApprovalGate) -> None:
        for actor in gate.automated_actors():
            with pytest.raises(AutomatedActorCannotApprove):
                gate.assert_may_record(actor)

    def test_case_and_whitespace_do_not_evade_the_refusal(
        self, gate: WorkflowApprovalGate
    ) -> None:
        with pytest.raises(AutomatedActorCannotApprove):
            gate.assert_may_record("  WORKFLOW  ")

    def test_a_human_actor_is_not_refused(self, gate: WorkflowApprovalGate) -> None:
        gate.assert_may_record("human")  # must not raise


class TestIsEnforcedApproval:
    def test_a_genuine_human_approval_bound_to_the_current_revision_is_enforced(
        self, gate: WorkflowApprovalGate
    ) -> None:
        assert gate.is_enforced_approval(
            decision=APPROVED,
            actor="human",
            approval_revision_hash=REVISION,
            current_revision_hash=REVISION,
        )

    def test_an_automated_actor_never_authorises_even_if_recorded_as_approved(
        self, gate: WorkflowApprovalGate
    ) -> None:
        for actor in gate.automated_actors():
            assert not gate.is_enforced_approval(
                decision=APPROVED,
                actor=actor,
                approval_revision_hash=REVISION,
                current_revision_hash=REVISION,
            )

    def test_a_rejection_never_authorises(self, gate: WorkflowApprovalGate) -> None:
        assert not gate.is_enforced_approval(
            decision="REJECTED",
            actor="human",
            approval_revision_hash=REVISION,
            current_revision_hash=REVISION,
        )

    def test_an_approval_bound_to_a_stale_revision_never_authorises(
        self, gate: WorkflowApprovalGate
    ) -> None:
        """The graph changed after the approval was recorded; the approval
        does not silently carry over to the new revision."""
        assert not gate.is_enforced_approval(
            decision=APPROVED,
            actor="human",
            approval_revision_hash=REVISION,
            current_revision_hash=OTHER_REVISION,
        )

    def test_no_narrowing_condition_can_be_bypassed_by_the_others(
        self, gate: WorkflowApprovalGate
    ) -> None:
        """An automated actor with a stale-and-rejected decision is refused
        for every reason at once, not accidentally accepted by one check
        short-circuiting past another."""
        assert not gate.is_enforced_approval(
            decision="REJECTED",
            actor="workflow",
            approval_revision_hash=REVISION,
            current_revision_hash=OTHER_REVISION,
        )
