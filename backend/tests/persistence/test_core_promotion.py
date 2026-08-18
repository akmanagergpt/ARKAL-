"""Composed CoreUpgrade promotion on a real StableCandidatePath and a real
StableRevisionPointer (ARK-REQ-0134's pipeline-followed half). Nothing
substituted below `lifecycle.evolution`'s own orchestration.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.kernel.contracts.state_machine_errors import GuardRejected
from arkali.lifecycle.evolution import core_upgrade_state_machine as cusm
from arkali.lifecycle.evolution.core_promotion import (
    CorePromotionRequest,
    promote_core_upgrade,
)
from arkali.lifecycle.release.stable_path import StableCandidatePath
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer

REPO = pathlib.Path(__file__).resolve().parents[3]
REV_A = "sha256:" + "a" * 64


class FakeHumanGate2Source:
    def __init__(self, grants: bool) -> None:
        self._grants = grants

    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str,
        revision_identity: str,
    ) -> bool:
        return self._grants


@pytest.fixture()
def path() -> StableCandidatePath:
    return StableCandidatePath.load(REPO)


@pytest.fixture()
def pointer(path: StableCandidatePath, tmp_path: pathlib.Path) -> StableRevisionPointer:
    return StableRevisionPointer(path, tmp_path / "stable_pointer.json")


def _awaiting_gate_2_instance() -> object:
    instance = cusm.build().start("SNAPSHOT_TAKEN")
    instance.apply("CANDIDATE_BUILT", {"recovery_supervisor_verified": True})
    instance.apply("VERIFYING")
    instance.apply("AWAITING_GATE_2")
    return instance


class TestPromoteCoreUpgrade:
    def test_refused_without_a_real_gate_2_grant_and_the_pointer_is_untouched(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        instance = _awaiting_gate_2_instance()
        receipt = path.begin_candidate(candidate_id="cand-1")
        for stage in path.stages()[2:-1]:
            receipt = path.advance(receipt, to_stage=stage)

        request = CorePromotionRequest(
            instance=instance, gates=FakeHumanGate2Source(grants=False), path=path,
            pointer=pointer, receipt=receipt, revision_id=REV_A,
            candidate_manifest_ref="sha256:" + "c" * 64,
        )
        with pytest.raises(GuardRejected):
            promote_core_upgrade(request)

        assert pointer.current() is None
        assert instance.state == "AWAITING_GATE_2"  # the refused transition never applied

    def test_a_real_grant_drives_a_genuine_stable_promotion(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        instance = _awaiting_gate_2_instance()
        receipt = path.begin_candidate(candidate_id="cand-1")
        for stage in path.stages()[2:-1]:
            receipt = path.advance(receipt, to_stage=stage)

        request = CorePromotionRequest(
            instance=instance, gates=FakeHumanGate2Source(grants=True), path=path,
            pointer=pointer, receipt=receipt, revision_id=REV_A,
            candidate_manifest_ref="sha256:" + "c" * 64,
        )
        record = promote_core_upgrade(request)

        assert record.revision_id == REV_A
        assert record.candidate_id == "cand-1"
        assert instance.state == "PROMOTED"
        assert pointer.current() is not None
        assert pointer.current().revision_id == REV_A  # type: ignore[union-attr]

    def test_a_stale_receipt_is_refused_before_anything_mutates(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        """The gate grant alone does not manufacture a promotion - the
        five-stage receipt proof is independent and still enforced, and
        checked *before* the CoreUpgrade instance transitions, so a stale
        receipt cannot leave the instance claiming PROMOTED while Stable was
        never written."""
        from arkali.lifecycle.release.stable_path import StablePathError

        instance = _awaiting_gate_2_instance()
        incomplete_receipt = path.begin_candidate(candidate_id="cand-1")  # stage 1 only

        request = CorePromotionRequest(
            instance=instance, gates=FakeHumanGate2Source(grants=True), path=path,
            pointer=pointer, receipt=incomplete_receipt, revision_id=REV_A,
            candidate_manifest_ref="sha256:" + "c" * 64,
        )
        with pytest.raises(StablePathError):
            promote_core_upgrade(request)

        assert pointer.current() is None
        assert instance.state == "AWAITING_GATE_2"  # never transitioned


class TestTheTwoRefusalsAreIndependent:
    def test_core_upgrade_guard_runs_before_the_pointer_is_ever_touched(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        """A denied gate never reaches `StableRevisionPointer.promote` at
        all - proven by the pointer file never being created."""
        instance = _awaiting_gate_2_instance()
        receipt = path.begin_candidate(candidate_id="cand-1")
        for stage in path.stages()[2:-1]:
            receipt = path.advance(receipt, to_stage=stage)

        request = CorePromotionRequest(
            instance=instance, gates=FakeHumanGate2Source(grants=False), path=path,
            pointer=pointer, receipt=receipt, revision_id=REV_A,
            candidate_manifest_ref="sha256:" + "c" * 64,
        )
        pointer_file = pointer._pointer_path  # type: ignore[attr-defined]
        assert not pointer_file.exists()
        with pytest.raises(GuardRejected):
            promote_core_upgrade(request)
        assert not pointer_file.exists()
