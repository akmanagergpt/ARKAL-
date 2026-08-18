"""Stable-revision pointer primitive (D-017, ARK-REQ-0157, ARK-REQ-0158).

Every case is driven through the real `StableCandidatePath`, loaded from the
live `AUTHORITY_MAP.yaml` - this file does not invent its own stage list.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import (
    StablePointerError,
    StableRevisionPointer,
)

REPO = pathlib.Path(__file__).resolve().parents[3]

REV_A = "sha256:" + "a" * 64
REV_B = "sha256:" + "b" * 64


@pytest.fixture()
def path() -> StableCandidatePath:
    return StableCandidatePath.load(REPO)


def _promotion_receipt(path: StableCandidatePath, candidate_id: str) -> StageReceipt:
    receipt = path.begin_candidate(candidate_id=candidate_id)
    for stage in path.stages()[2:-1]:
        receipt = path.advance(receipt, to_stage=stage)
    return path.promotion_receipt(receipt)


class TestEmptyPointer:
    def test_current_is_none_before_any_promotion(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        assert pointer.current() is None
        assert pointer.history() == ()

    def test_nothing_is_previously_verified_before_any_promotion(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        assert pointer.is_previously_verified(REV_A) is False


class TestPromotion:
    def test_promotion_requires_the_full_canonical_receipt(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        partial = path.begin_candidate(candidate_id="cand-1")
        with pytest.raises(StablePointerError):
            pointer.promote(partial, revision_id=REV_A, candidate_id="cand-1")

    def test_promotion_refuses_a_receipt_for_a_different_candidate(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        receipt = _promotion_receipt(path, "cand-1")
        with pytest.raises(StablePointerError):
            pointer.promote(receipt, revision_id=REV_A, candidate_id="cand-2")

    def test_promotion_refuses_a_non_canonical_revision_id(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        receipt = _promotion_receipt(path, "cand-1")
        with pytest.raises(StablePointerError):
            pointer.promote(receipt, revision_id="not-a-content-address", candidate_id="cand-1")

    def test_a_genuine_promotion_becomes_current_and_previously_verified(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        receipt = _promotion_receipt(path, "cand-1")
        record = pointer.promote(receipt, revision_id=REV_A, candidate_id="cand-1")
        assert record.revision_id == REV_A
        assert pointer.current() is not None
        assert pointer.current().revision_id == REV_A  # type: ignore[union-attr]
        assert pointer.is_previously_verified(REV_A) is True

    def test_history_is_append_only_across_promotions(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer_path = tmp_path / "stable_pointer.json"
        pointer = StableRevisionPointer(path, pointer_path)
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        pointer.promote(
            _promotion_receipt(path, "cand-2"), revision_id=REV_B, candidate_id="cand-2"
        )
        assert pointer.current().revision_id == REV_B  # type: ignore[union-attr]
        assert [rec.revision_id for rec in pointer.history()] == [REV_A]
        assert pointer.is_previously_verified(REV_A) is True
        assert pointer.is_previously_verified(REV_B) is True

    def test_promoting_the_same_pointer_path_twice_never_loses_the_prior_record(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        """A fresh pointer object over the same file sees the durable state."""
        pointer_path = tmp_path / "stable_pointer.json"
        StableRevisionPointer(path, pointer_path).promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        reopened = StableRevisionPointer(path, pointer_path)
        assert reopened.current().revision_id == REV_A  # type: ignore[union-attr]


class TestRollback:
    def test_rollback_refuses_a_revision_never_recorded_as_stable(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        with pytest.raises(StablePointerError):
            pointer.rollback_to(REV_B)

    def test_rollback_to_a_previously_promoted_revision_switches_current(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        pointer.promote(
            _promotion_receipt(path, "cand-2"), revision_id=REV_B, candidate_id="cand-2"
        )
        record = pointer.rollback_to(REV_A)
        assert record.revision_id == REV_A
        assert pointer.current().revision_id == REV_A  # type: ignore[union-attr]

    def test_rollback_carries_the_abandoned_revision_into_history_not_lossy(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        pointer.promote(
            _promotion_receipt(path, "cand-2"), revision_id=REV_B, candidate_id="cand-2"
        )
        pointer.rollback_to(REV_A)
        assert {rec.revision_id for rec in pointer.history()} == {REV_B}
        assert pointer.is_previously_verified(REV_A) is True
        assert pointer.is_previously_verified(REV_B) is True

    def test_rollback_to_the_current_revision_is_a_harmless_no_op(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        record = pointer.rollback_to(REV_A)
        assert record.revision_id == REV_A
        assert pointer.history() == ()

    def test_rollback_never_appears_twice_in_history_after_switching_back(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        """The rolled-back-to revision leaves history to become current again -
        it is never simultaneously current and its own history entry."""
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        pointer.promote(
            _promotion_receipt(path, "cand-2"), revision_id=REV_B, candidate_id="cand-2"
        )
        pointer.rollback_to(REV_A)
        ids_in_history = [rec.revision_id for rec in pointer.history()]
        assert ids_in_history.count(REV_A) == 0


class TestTamperResistance:
    def test_a_truncated_pointer_file_is_refused_not_silently_repaired(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer_path = tmp_path / "stable_pointer.json"
        pointer_path.write_text("{not valid json", encoding="utf-8")
        pointer = StableRevisionPointer(path, pointer_path)
        with pytest.raises(StablePointerError):
            pointer.current()

    def test_an_unknown_major_version_is_refused(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer_path = tmp_path / "stable_pointer.json"
        pointer_path.write_text(
            '{"pointer_version": "99.0.0", "current": null, "history": []}',
            encoding="utf-8",
        )
        pointer = StableRevisionPointer(path, pointer_path)
        with pytest.raises(StablePointerError):
            pointer.current()

    def test_no_temp_file_is_left_behind_after_a_successful_promotion(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        pointer.promote(
            _promotion_receipt(path, "cand-1"), revision_id=REV_A, candidate_id="cand-1"
        )
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".stable_pointer_")]
        assert leftovers == []
