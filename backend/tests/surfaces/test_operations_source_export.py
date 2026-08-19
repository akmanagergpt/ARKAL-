"""C-34 Source Intelligence Export (ARK-REQ-0169/0357): a real file tree
and real, secret-redacted source content, gated by the real PDP.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.secret_reference import REDACTED_TOKEN
from arkali.surfaces.operations.source_export import export_source
from tests.security.test_protected_core_and_secrets import synthetic_secret

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


class _AlwaysDeny:
    def decide_computer_use(self, **_kwargs: object) -> tuple[str, str, str | None]:
        return "DENY", "fixture always denies", None


class TestExportSourceReadsRealFilesFromDisk:
    def test_a_small_real_tree_is_exported_with_real_content(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        (tmp_path / "pkg").mkdir()
        (tmp_path / "pkg" / "a.py").write_text("print('a')", encoding="utf-8")
        (tmp_path / "pkg" / "b.py").write_text("print('b')", encoding="utf-8")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "junk.pyc").write_bytes(b"\x00\x01")

        result = export_source(pdp, root=tmp_path, trust_tier="TRUST-1")
        assert result.executed
        assert set(result.tree) == {"pkg/a.py", "pkg/b.py"}
        contents = {f.relative_path: f.content for f in result.files}
        assert contents["pkg/a.py"] == "print('a')"
        assert contents["pkg/b.py"] == "print('b')"

    def test_a_deny_decision_exports_nothing(self, tmp_path: pathlib.Path) -> None:
        (tmp_path / "a.py").write_text("print('a')", encoding="utf-8")
        result = export_source(_AlwaysDeny(), root=tmp_path)
        assert not result.executed
        assert result.tree == ()
        assert result.files == ()


class TestSecretsAreGenuinelyRedactedInExportedContent:
    def test_a_real_secret_shape_in_a_file_is_redacted_on_export(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        secret = synthetic_secret("openai")
        (tmp_path / "config.py").write_text(
            f"API_KEY = '{secret}'\n", encoding="utf-8",
        )
        result = export_source(pdp, root=tmp_path, trust_tier="TRUST-1")
        exported = result.files[0]
        assert secret not in exported.content
        assert REDACTED_TOKEN in exported.content
        assert exported.redacted is True

    def test_a_file_without_a_secret_is_marked_unredacted(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        (tmp_path / "plain.py").write_text("x = 1\n", encoding="utf-8")
        result = export_source(pdp, root=tmp_path, trust_tier="TRUST-1")
        assert result.files[0].redacted is False


class TestLimitsAreReal:
    def test_max_files_truncates_and_says_so(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        for i in range(5):
            (tmp_path / f"f{i}.txt").write_text("x", encoding="utf-8")
        result = export_source(pdp, root=tmp_path, trust_tier="TRUST-1", max_files=2)
        assert len(result.tree) == 2
        assert result.truncated is True

    def test_max_file_bytes_truncates_one_large_file(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        (tmp_path / "big.txt").write_text("x" * 1000, encoding="utf-8")
        result = export_source(pdp, root=tmp_path, trust_tier="TRUST-1", max_file_bytes=10)
        assert "<truncated" in result.files[0].content
