from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from arkali.engineering.candidate.assembly_vocabulary import AssemblyVocabulary
from arkali.engineering.candidate.errors import (
    InvalidCandidateManifestError,
    UnknownProductComponentError,
    WorkspaceIsolationError,
)
from arkali.engineering.candidate.manifest import CandidateComponent, CandidateManifest
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.kernel.contracts.content_address import address_of

REPO = pathlib.Path(__file__).resolve().parents[3]


def manifest(**updates: object) -> CandidateManifest:
    values: dict[str, object] = {
        "candidate_id": "candidate-12",
        "workspace_id": "workspace-agent-a",
        "task_id": "task-12",
        "agent_id": "agent-a",
        "snapshot_ref": address_of(b"stable snapshot"),
        "components": (
            CandidateComponent(
                component="Working Copies", artifact_ref=address_of(b"candidate bytes")
            ),
        ),
    }
    values.update(updates)
    return CandidateManifest.assembled(AssemblyVocabulary.load(REPO), **values)


class TestIsolatedWorkspace:
    def test_snapshot_is_copied_and_stable_is_never_written(
        self, tmp_path: pathlib.Path
    ) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        (stable / "app.py").write_text("stable", encoding="utf-8")
        authority = WorkspaceAuthority(tmp_path / "ephemeral")

        workspace = authority.allocate(
            workspace_id="ws-a", task_id="task-a", agent_id="agent-a",
            stable_snapshot=stable,
        )
        workspace.write("snapshot/app.py", b"candidate")

        assert (stable / "app.py").read_text(encoding="utf-8") == "stable"
        assert (workspace.snapshot / "app.py").read_text(encoding="utf-8") == "candidate"

    def test_agents_cannot_share_or_reallocate_a_workspace(
        self, tmp_path: pathlib.Path
    ) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        authority = WorkspaceAuthority(tmp_path / "ephemeral")
        authority.allocate(
            workspace_id="ws-a", task_id="task-a", agent_id="agent-a",
            stable_snapshot=stable,
        )
        with pytest.raises(WorkspaceIsolationError, match="never share"):
            authority.allocate(
                workspace_id="ws-a", task_id="task-b", agent_id="agent-b",
                stable_snapshot=stable,
            )

    @pytest.mark.parametrize("path", ("../stable/app.py", "/tmp/out", "a/../../out"))
    def test_workspace_paths_cannot_escape(self, tmp_path: pathlib.Path, path: str) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        workspace = WorkspaceAuthority(tmp_path / "ephemeral").allocate(
            workspace_id="ws-a", task_id="task-a", agent_id="agent-a",
            stable_snapshot=stable,
        )
        with pytest.raises(WorkspaceIsolationError):
            workspace.write(path, b"escape")

    def test_a_symlink_cannot_turn_a_confined_path_into_an_escape(
        self, tmp_path: pathlib.Path
    ) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        workspace = WorkspaceAuthority(tmp_path / "ephemeral").allocate(
            workspace_id="ws-a", task_id="task-a", agent_id="agent-a",
            stable_snapshot=stable,
        )
        (workspace.root / "link").symlink_to(outside, target_is_directory=True)

        with pytest.raises(WorkspaceIsolationError, match="resolves through a link"):
            workspace.write("link/escaped.txt", b"escape")
        assert not (outside / "escaped.txt").exists()

    def test_delete_removes_a_real_file_and_refuses_escape_or_missing(
        self, tmp_path: pathlib.Path
    ) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        (stable / "app.py").write_text("stable", encoding="utf-8")
        workspace = WorkspaceAuthority(tmp_path / "ephemeral").allocate(
            workspace_id="ws-a", task_id="task-a", agent_id="agent-a",
            stable_snapshot=stable,
        )
        with pytest.raises(WorkspaceIsolationError):
            workspace.delete("../stable/app.py")
        with pytest.raises(WorkspaceIsolationError, match="not an existing file"):
            workspace.delete("snapshot/nonexistent.py")

        workspace.delete("snapshot/app.py")
        assert not (workspace.snapshot / "app.py").exists()
        assert (stable / "app.py").exists()

    def test_rename_moves_a_real_file_and_refuses_escape_or_missing_source(
        self, tmp_path: pathlib.Path
    ) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        (stable / "app.py").write_text("stable", encoding="utf-8")
        workspace = WorkspaceAuthority(tmp_path / "ephemeral").allocate(
            workspace_id="ws-a", task_id="task-a", agent_id="agent-a",
            stable_snapshot=stable,
        )
        with pytest.raises(WorkspaceIsolationError):
            workspace.rename("snapshot/app.py", "../escaped.py")
        with pytest.raises(WorkspaceIsolationError, match="not an existing file"):
            workspace.rename("snapshot/missing.py", "snapshot/renamed.py")

        destination = workspace.rename("snapshot/app.py", "snapshot/sub/renamed.py")
        assert destination == workspace.snapshot / "sub" / "renamed.py"
        assert destination.read_text(encoding="utf-8") == "stable"
        assert not (workspace.snapshot / "app.py").exists()


class TestCandidateManifest:
    def test_manifest_is_canonical_deterministic_and_immutable(self) -> None:
        first = manifest()
        second = manifest()
        assert first.components[0].component == "working_copies"
        assert first.rendering() == second.rendering()
        assert first.manifest_ref == second.manifest_ref
        with pytest.raises(ValidationError):
            first.candidate_id = "changed"  # type: ignore[misc]

    def test_unknown_and_duplicate_components_are_refused(self) -> None:
        with pytest.raises(UnknownProductComponentError):
            manifest(
                components=(
                    CandidateComponent(
                        component="invented", artifact_ref=address_of(b"x")
                    ),
                )
            )
        duplicate = CandidateComponent(
            component="Working Copies", artifact_ref=address_of(b"x")
        )
        with pytest.raises(InvalidCandidateManifestError, match="only once"):
            manifest(components=(duplicate, duplicate))

    @pytest.mark.parametrize("field", ("snapshot_ref", "component"))
    def test_only_content_addressed_artifacts_enter_the_manifest(self, field: str) -> None:
        values: dict[str, object] = {}
        if field == "snapshot_ref":
            values[field] = "stable-latest"
        else:
            values["components"] = (
                CandidateComponent(component="Working Copies", artifact_ref="latest"),
            )
        with pytest.raises(InvalidCandidateManifestError, match="canonical artifact"):
            manifest(**values)

    def test_manifest_has_no_acceptance_or_promotion_surface(self) -> None:
        fields = set(CandidateManifest.model_fields)
        assert not fields.intersection({"accepted", "acceptance", "promoted", "stable"})
