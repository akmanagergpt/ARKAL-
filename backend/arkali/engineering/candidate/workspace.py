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
