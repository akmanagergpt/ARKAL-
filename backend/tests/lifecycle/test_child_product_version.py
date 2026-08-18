"""C-36 child-product version lineage (ARK-REQ-0132, ARK-REQ-0358)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arkali.kernel.contracts.content_address import address_of
from arkali.lifecycle.evolution.child_product_version import (
    ChildProductVersion,
    ChildProductVersionLineage,
)
from arkali.lifecycle.evolution.errors import (
    UnknownVersionReferenceError,
    VersionLineageOrderError,
)


def content_ref(label: str) -> str:
    return address_of(label.encode("utf-8"))


def lineage(**updates: object) -> ChildProductVersionLineage:
    values: dict[str, object] = {"product_ref": content_ref("acme-task-tracker")}
    values.update(updates)
    return ChildProductVersionLineage.model_validate(values)


class TestChildProductVersion:
    def test_content_ref_must_be_a_real_content_address(self) -> None:
        with pytest.raises(ValidationError):
            ChildProductVersion(
                sequence=1, content_ref="not-an-address", campaign_id="c-1",
            )

    def test_version_ref_is_deterministic_and_distinct_from_content_ref(self) -> None:
        version = ChildProductVersion(
            sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
        )
        assert version.version_ref != version.content_ref
        assert version.version_ref == ChildProductVersion(
            sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
        ).version_ref

    def test_frozen(self) -> None:
        version = ChildProductVersion(
            sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
        )
        with pytest.raises(ValidationError):
            version.sequence = 2  # type: ignore[misc]


class TestLineageAppendOrdering:
    def test_the_first_version_must_have_sequence_one_and_no_parent(self) -> None:
        first = ChildProductVersion(
            sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
        )
        appended = lineage().append(first)
        assert appended.current == first
        assert len(appended.versions) == 1

    def test_a_gap_in_sequence_is_refused(self) -> None:
        skipped = ChildProductVersion(
            sequence=2, content_ref=content_ref("v1"), campaign_id="c-1",
        )
        with pytest.raises(VersionLineageOrderError):
            lineage().append(skipped)

    def test_a_second_version_must_reference_the_first_as_parent(self) -> None:
        base = lineage().append(
            ChildProductVersion(
                sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
            )
        )
        wrong_parent = ChildProductVersion(
            sequence=2, content_ref=content_ref("v2"), campaign_id="c-1",
            parent_ref="sha256:" + "0" * 64,
        )
        with pytest.raises(VersionLineageOrderError):
            base.append(wrong_parent)

    def test_a_correctly_chained_second_version_is_accepted(self) -> None:
        base = lineage().append(
            ChildProductVersion(
                sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
            )
        )
        second = ChildProductVersion(
            sequence=2, content_ref=content_ref("v2"), campaign_id="c-1",
            parent_ref=base.current.version_ref,  # type: ignore[union-attr]
        )
        chained = base.append(second)
        assert chained.current == second
        assert len(chained.versions) == 2

    def test_append_returns_a_new_lineage_the_original_is_unmutated(self) -> None:
        base = lineage()
        base.append(
            ChildProductVersion(
                sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
            )
        )
        assert base.versions == ()


class TestRollback:
    def _two_version_lineage(self) -> ChildProductVersionLineage:
        base = lineage().append(
            ChildProductVersion(
                sequence=1, content_ref=content_ref("v1.4"), campaign_id="c-1",
            )
        )
        return base.append(
            ChildProductVersion(
                sequence=2, content_ref=content_ref("v1.5"), campaign_id="c-2",
                parent_ref=base.current.version_ref,  # type: ignore[union-attr]
            )
        )

    def test_rollback_to_an_earlier_version_appends_never_truncates(self) -> None:
        two = self._two_version_lineage()
        target = two.versions[0].version_ref
        rolled_back = two.rollback_to(target, campaign_id="c-3")
        assert len(rolled_back.versions) == 3
        assert rolled_back.versions[0] == two.versions[0]
        assert rolled_back.versions[1] == two.versions[1]

    def test_the_new_entry_reproduces_the_target_content_and_is_flagged(self) -> None:
        two = self._two_version_lineage()
        target = two.versions[0]
        rolled_back = two.rollback_to(target.version_ref, campaign_id="c-3")
        newest = rolled_back.current
        assert newest is not None
        assert newest.content_ref == target.content_ref
        assert newest.is_rollback is True
        assert newest.sequence == 3

    def test_rollback_to_an_unrecorded_version_is_refused(self) -> None:
        two = self._two_version_lineage()
        with pytest.raises(UnknownVersionReferenceError):
            two.rollback_to("sha256:" + "f" * 64, campaign_id="c-3")

    def test_rollback_current_stays_recoverable_by_a_second_rollback(self) -> None:
        """No data is lost: after rolling back, the version rolled away
        from is still findable in history and can itself be the target of a
        later rollback."""
        two = self._two_version_lineage()
        newer_ref = two.versions[1].version_ref
        rolled_back = two.rollback_to(two.versions[0].version_ref, campaign_id="c-3")
        forward_again = rolled_back.rollback_to(newer_ref, campaign_id="c-4")
        assert forward_again.current is not None
        assert forward_again.current.content_ref == two.versions[1].content_ref
        assert len(forward_again.versions) == 4


class TestLineageRef:
    def test_lineage_ref_is_deterministic(self) -> None:
        a = lineage().append(
            ChildProductVersion(
                sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
            )
        )
        b = lineage().append(
            ChildProductVersion(
                sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
            )
        )
        assert a.lineage_ref == b.lineage_ref

    def test_lineage_ref_changes_when_history_changes(self) -> None:
        base = lineage()
        appended = base.append(
            ChildProductVersion(
                sequence=1, content_ref=content_ref("v1"), campaign_id="c-1",
            )
        )
        assert base.lineage_ref != appended.lineage_ref
