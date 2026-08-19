"""C-34 AI Review Bundle (ARK-REQ-0169/0357): architecture/contracts/issues/
evidence/tree/source composed from real, live repository authorities.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.surfaces.operations.ai_review_bundle import build_ai_review_bundle

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


class TestBuildAiReviewBundleComposesRealAuthorities:
    def test_architecture_reflects_the_real_live_gate_run(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        bundle = build_ai_review_bundle(
            pdp, repo_root=REPO, source_root=tmp_path, trust_tier="TRUST-1",
        )
        assert bundle.architecture.gates_total == 8
        assert bundle.architecture.gates_passed == bundle.architecture.gates_total
        assert bundle.architecture.violations == ()

    def test_canonical_documents_are_referenced_and_really_exist(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        bundle = build_ai_review_bundle(pdp, repo_root=REPO, source_root=tmp_path)
        assert bundle.contracts.exists
        assert bundle.contracts.size_bytes is not None and bundle.contracts.size_bytes > 0
        assert bundle.issues.exists
        assert bundle.evidence.exists
        assert bundle.evidence.is_directory
        assert bundle.evidence.file_count is not None and bundle.evidence.file_count > 0

    def test_a_missing_document_is_reported_honestly_not_fabricated(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        from arkali.surfaces.operations.ai_review_bundle import _reference

        missing = _reference(REPO, "docs/this/path/does/not/exist.md")
        assert missing.exists is False
        assert missing.size_bytes is None

    def test_source_is_the_real_export_of_source_root(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        (tmp_path / "hello.py").write_text("print('hi')", encoding="utf-8")
        bundle = build_ai_review_bundle(
            pdp, repo_root=REPO, source_root=tmp_path, trust_tier="TRUST-1",
        )
        assert bundle.source.executed
        assert "hello.py" in bundle.source.tree
