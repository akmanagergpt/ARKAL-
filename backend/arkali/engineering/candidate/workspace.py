"""Ephemeral candidate workspaces isolated by exclusive identity and path."""

from __future__ import annotations

import pathlib
import shutil
from dataclasses import dataclass

from arkali.engineering.candidate.errors import WorkspaceIsolationError


def _segment(value: str, field: str) -> str:
    candidate = pathlib.PurePath(value)
    if not value.strip() or candidate.name != value or value in {".", ".."}:
        raise WorkspaceIsolationError(f"{field} must be one non-empty path segment")
    return value


@dataclass(frozen=True)
class CandidateWorkspace:
    """A lease whose writable tree is disjoint from every other lease."""

    workspace_id: str
    task_id: str
    agent_id: str
    root: pathlib.Path
    snapshot: pathlib.Path

    def path_for(self, relative: str) -> pathlib.Path:
        requested = pathlib.PurePath(relative)
        if requested.is_absolute() or ".." in requested.parts or not requested.parts:
            raise WorkspaceIsolationError("workspace paths must be relative and confined")
        target = self.root.joinpath(*requested.parts)
        if not target.is_relative_to(self.root):
            raise WorkspaceIsolationError("workspace path escapes its assigned root")
        return target

    def write(self, relative: str, payload: bytes) -> pathlib.Path:
        target = self.path_for(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        resolved_root = self.root.resolve()
        resolved_target = target.resolve()
        if not resolved_target.is_relative_to(resolved_root):
            raise WorkspaceIsolationError(
                "workspace path resolves through a link outside its assigned root"
            )
        target.write_bytes(payload)
        return target

    def delete(self, relative: str) -> None:
        """Remove one real file already inside this workspace. Refuses a
        path escape by the identical two-stage check `write` already uses
        (declared-relative, then resolved-relative); refuses a target that
        is not a real, existing, plain file, so a caller can never delete
        a directory (or nothing) through this call."""
        target = self.path_for(relative)
        resolved_root = self.root.resolve()
        resolved_target = target.resolve()
        if not resolved_target.is_relative_to(resolved_root):
            raise WorkspaceIsolationError(
                "workspace path resolves through a link outside its assigned root"
            )
        if not target.is_file():
            raise WorkspaceIsolationError(
                f"delete target {relative!r} is not an existing file in this workspace"
            )
        target.unlink()

    def rename(self, relative: str, new_relative: str) -> pathlib.Path:
        """Move one real file already inside this workspace to a new path,
        also inside this workspace. Both the source and destination are
        checked through the identical containment discipline `write`/
        `delete` already use; the destination's parent directory is
        created if needed, matching `write`'s own behaviour."""
        source = self.path_for(relative)
        destination = self.path_for(new_relative)
        resolved_root = self.root.resolve()
        if not source.resolve().is_relative_to(resolved_root):
            raise WorkspaceIsolationError(
                "workspace path resolves through a link outside its assigned root"
            )
        if not source.is_file():
            raise WorkspaceIsolationError(
                f"rename source {relative!r} is not an existing file in this workspace"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        resolved_destination = destination.resolve()
        if not resolved_destination.is_relative_to(resolved_root):
            raise WorkspaceIsolationError(
                "workspace path resolves through a link outside its assigned root"
            )
        source.rename(destination)
        return destination


class WorkspaceAuthority:
    """Allocates exclusive workspaces without ever opening a stable write path."""

    def __init__(self, workspace_root: pathlib.Path) -> None:
        self._root = workspace_root

    def allocate(
        self,
        *,
        workspace_id: str,
        task_id: str,
        agent_id: str,
        stable_snapshot: pathlib.Path,
    ) -> CandidateWorkspace:
        workspace_id = _segment(workspace_id, "workspace_id")
        _segment(task_id, "task_id")
        _segment(agent_id, "agent_id")
        if not stable_snapshot.is_dir():
            raise WorkspaceIsolationError("stable snapshot must be an existing directory")

        root = self._root / workspace_id
        try:
            root.mkdir(parents=True, exist_ok=False)
            snapshot = root / "snapshot"
            shutil.copytree(stable_snapshot, snapshot)
        except FileExistsError as exc:
            raise WorkspaceIsolationError(
                f"workspace {workspace_id!r} is already allocated; agents never share one"
            ) from exc
        except Exception:
            if root.exists():
                shutil.rmtree(root)
            raise
        return CandidateWorkspace(workspace_id, task_id, agent_id, root, snapshot)
