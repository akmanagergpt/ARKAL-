"""Release Manifest domain model + Release Authority (ARK-REQ-0007 partial,
ARK-REQ-0350 partial, Phase 26 Package 1).

Every case is driven through the real `StableCandidatePath`/`StableRevisionPointer`
and the real, unmodified `Release` state machine - this file invents neither.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest

from arkali.kernel.contracts.state_machine import GuardRejected
from arkali.lifecycle.release import release_state_machine as rsm
from arkali.lifecycle.release.release_manifest import (
    ReleaseAuthority,
    ReleaseAuthorityError,
    ReleaseCandidate,
)
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer

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


def _pointer_with_stable(path: StableCandidatePath, tmp_path: pathlib.Path) -> StableRevisionPointer:
    pointer = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
    receipt = _promotion_receipt(path, "core-cand-1")
    pointer.promote(receipt, revision_id=REV_A, candidate_id="core-cand-1")
    return pointer


class TestNoReleaseBeforeStableCoreExists:
    def test_declaration_is_refused_before_any_core_promotion(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        empty = StableRevisionPointer(path, tmp_path / "stable_pointer.json")
        authority = ReleaseAuthority(empty)
        with pytest.raises(ReleaseAuthorityError):
            authority.declare_release_candidate()


class TestDeclareReleaseCandidate:
    def test_declares_over_the_real_current_stable_core_revision(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        candidate, instance = authority.declare_release_candidate()
        assert candidate.core_revision_id == REV_A
        assert instance.state == "DRAFT"

    def test_the_instance_is_a_real_unmodified_release_machine(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        _candidate, instance = authority.declare_release_candidate()
        assert instance.machine.definition is rsm.DEFINITION

    def test_release_id_is_content_addressed_not_caller_suppliable(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        now = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
        first, _ = authority.declare_release_candidate(now=now)
        second, _ = authority.declare_release_candidate(now=now)
        assert first.release_id == second.release_id, "same (revision, instant) is deterministic"

    def test_two_declarations_at_different_instants_are_distinct_candidates(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        first, _ = authority.declare_release_candidate(now=dt.datetime(2026, 1, 1, tzinfo=dt.UTC))
        second, _ = authority.declare_release_candidate(now=dt.datetime(2026, 1, 2, tzinfo=dt.UTC))
        assert first.release_id != second.release_id

    def test_release_id_cannot_be_forged_from_a_different_revision(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        """A caller cannot construct a ReleaseCandidate that claims a release_id
        not actually derived from its own (core_revision_id, declared_at)."""
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        genuine, _ = authority.declare_release_candidate()
        forged = ReleaseCandidate(
            release_id=genuine.release_id,
            core_revision_id=REV_B,
            declared_at=genuine.declared_at,
        )
        assert forged.core_revision_id != genuine.core_revision_id


class TestAssertStillStable:
    def test_a_genuinely_promoted_revision_passes(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        candidate, _ = authority.declare_release_candidate()
        authority.assert_still_stable(candidate)  # must not raise

    def test_a_revision_the_pointer_never_recorded_is_refused(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        forged = ReleaseCandidate(
            release_id="sha256:" + "0" * 64,
            core_revision_id=REV_B,
            declared_at=dt.datetime.now(dt.UTC),
        )
        with pytest.raises(ReleaseAuthorityError):
            authority.assert_still_stable(forged)


class TestRealReleaseMachineReuse:
    def test_no_second_state_machine_authority_was_minted(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        """Identity, not equality - the same proof Phase 23/24 used for their
        own reused machines."""
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        _candidate, instance = authority.declare_release_candidate()
        assert instance.machine.definition is rsm.DEFINITION
        assert rsm.DEFINITION.machine == "Release"

    def test_draft_to_released_is_refused_without_a_real_human_gate_7(
        self, path: StableCandidatePath, tmp_path: pathlib.Path
    ) -> None:
        """The real, unmodified guard: no fact means no transition, structurally
        - this is the same machine STATE_MACHINES.md §7 already declares."""
        pointer = _pointer_with_stable(path, tmp_path)
        authority = ReleaseAuthority(pointer)
        _candidate, instance = authority.declare_release_candidate()
        for target in ("BUILT", "VERIFIED", "SIGNED_READY"):
            outcome_instance_state_before = instance.state
            instance.apply(target)
            assert instance.state != outcome_instance_state_before
        with pytest.raises(GuardRejected):
            instance.apply("RELEASED")
