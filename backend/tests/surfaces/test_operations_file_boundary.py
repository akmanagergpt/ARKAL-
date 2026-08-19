"""C-34 permission-aware file access (ARK-REQ-0170): real reads/writes,
structurally confined, gated by the real PDP.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.surfaces.operations.file_boundary import (
    FileConfinementError,
    read_workspace_file,
    write_workspace_file,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


class _AlwaysDeny:
    def decide_computer_use(self, **_kwargs: object) -> tuple[str, str, str | None]:
        return "DENY", "fixture always denies", None


class TestWriteThenReadIsReal:
    def test_a_written_file_is_really_on_disk_and_readable_back(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        write_outcome = write_workspace_file(
            pdp, root=tmp_path, relative="notes/hello.txt", payload=b"hello computer-use",
        )
        assert write_outcome.executed
        on_disk = tmp_path / "notes" / "hello.txt"
        assert on_disk.is_file()
        assert on_disk.read_bytes() == b"hello computer-use"

        read_outcome = read_workspace_file(pdp, root=tmp_path, relative="notes/hello.txt")
        assert read_outcome.executed
        assert read_outcome.content == b"hello computer-use"

    def test_reading_a_missing_file_reports_not_executed_rather_than_raising(
        self, pdp: PolicyDecisionPoint, tmp_path: pathlib.Path,
    ) -> None:
        outcome = read_workspace_file(pdp, root=tmp_path, relative="never-written.txt")
        assert not outcome.executed
        assert outcome.content is None


class TestConfinementIsStructuralNotJustPolicy:
    def test_a_parent_traversal_is_refused_before_any_policy_question(
        self, tmp_path: pathlib.Path,
    ) -> None:
        with pytest.raises(FileConfinementError):
            write_workspace_file(
                _AlwaysDeny(), root=tmp_path, relative="../escape.txt", payload=b"x",
            )

    def test_an_absolute_path_is_refused(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(FileConfinementError):
            read_workspace_file(_AlwaysDeny(), root=tmp_path, relative="/etc/passwd")

    def test_a_deny_decision_writes_nothing(
        self, tmp_path: pathlib.Path,
    ) -> None:
        outcome = write_workspace_file(
            _AlwaysDeny(), root=tmp_path, relative="never.txt", payload=b"x",
        )
        assert not outcome.executed
        assert not (tmp_path / "never.txt").exists()
