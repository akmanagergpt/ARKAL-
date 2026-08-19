"""Suspicious-package review (ARK-REQ-0125, Phase 26 Package 4)."""

from __future__ import annotations

import pathlib

from arkali.lifecycle.release.sbom import DependencyEntry, SoftwareBillOfMaterials, generate_sbom
from arkali.lifecycle.release.suspicious_package_review import (
    SuspiciousPackageReview,
    review_sbom,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


def _entry(ecosystem: str, name: str, constraint: str = ">=1.0") -> DependencyEntry:
    return DependencyEntry(ecosystem=ecosystem, name=name, version_constraint=constraint)


class TestRealRepositoryIsClean:
    def test_this_repositorys_own_real_sbom_earns_a_genuine_pass(self) -> None:
        """The real dependency set (fastapi, pydantic, sqlalchemy, alembic,
        uvicorn, react, react-dom) triggers none of the three checks - a
        real, earned PASS, not assumed."""
        sbom = generate_sbom(REPO)
        review = review_sbom(sbom)
        assert isinstance(review, SuspiciousPackageReview)
        assert review.reviewed_count == len(sbom.entries)
        assert review.clean is True
        assert review.findings == ()


class TestUnpinnedDetection:
    def test_a_wildcard_constraint_is_flagged(self) -> None:
        sbom = SoftwareBillOfMaterials(entries=(_entry("python", "widget", "*"),))
        review = review_sbom(sbom)
        assert not review.clean
        assert any("unpinned" in f.reason for f in review.findings)

    def test_a_pinned_constraint_is_not_flagged(self) -> None:
        sbom = SoftwareBillOfMaterials(entries=(_entry("python", "widget", ">=1.2.3"),))
        review = review_sbom(sbom)
        assert review.clean


class TestKnownTyposquatDetection:
    def test_a_documented_npm_typosquat_is_flagged(self) -> None:
        sbom = SoftwareBillOfMaterials(entries=(_entry("node", "crossenv"),))
        review = review_sbom(sbom)
        assert not review.clean
        assert any("typosquat" in f.reason for f in review.findings)

    def test_a_documented_pypi_typosquat_is_flagged(self) -> None:
        sbom = SoftwareBillOfMaterials(entries=(_entry("python", "colourama"),))
        review = review_sbom(sbom)
        assert not review.clean

    def test_the_real_legitimate_package_is_not_flagged(self) -> None:
        sbom = SoftwareBillOfMaterials(entries=(_entry("node", "cross-env"),))
        review = review_sbom(sbom)
        assert review.clean


class TestConfusablePairDetection:
    def test_two_one_edit_apart_names_in_the_same_ecosystem_are_flagged(self) -> None:
        sbom = SoftwareBillOfMaterials(
            entries=(_entry("python", "reqeusts"), _entry("python", "reqeust"))
        )
        review = review_sbom(sbom)
        assert not review.clean
        assert any("one edit apart" in f.reason for f in review.findings)

    def test_confusable_names_across_different_ecosystems_are_not_paired(self) -> None:
        sbom = SoftwareBillOfMaterials(
            entries=(_entry("python", "widget"), _entry("node", "widget2"))
        )
        review = review_sbom(sbom)
        assert review.clean

    def test_clearly_distinct_names_are_not_flagged(self) -> None:
        sbom = SoftwareBillOfMaterials(
            entries=(_entry("python", "fastapi"), _entry("python", "sqlalchemy"))
        )
        review = review_sbom(sbom)
        assert review.clean


class TestReviewIsReDerived:
    def test_two_calls_over_the_same_sbom_produce_the_identical_result(self) -> None:
        sbom = generate_sbom(REPO)
        first = review_sbom(sbom)
        second = review_sbom(sbom)
        assert first == second
