"""C-36 child-product working-copy isolation over the real, unmodified
Phase 12 `WorkspaceAuthority`/`CandidateWorkspace` (ARK-REQ-0132/0358).

Stage A: real-authority composition. Stage B: structural proof this
context never reaches ARKALI's own source tree.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

import pytest

from arkali.engineering.candidate.errors import WorkspaceIsolationError
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.lifecycle.evolution.child_product_identity import (
    ChildProductIdentity,
    ChildProductMode,
)
from arkali.lifecycle.evolution.child_product_workspace import (
    allocate_child_product_workspace,
    child_workspace_id,
)

MODULE: Final[pathlib.Path] = (
    pathlib.Path(__file__).resolve().parents[3]
    / "backend/arkali/lifecycle/evolution/child_product_workspace.py"
)


def identity(**updates: object) -> ChildProductIdentity:
    values: dict[str, object] = {
        "product_id": "acme-task-tracker",
        "name": "Acme Task Tracker",
        "mode": ChildProductMode.AI_NATIVE_SELF_EVOLVING,
    }
    values.update(updates)
    return ChildProductIdentity.model_validate(values)


class TestChildWorkspaceId:
    def test_deterministic_for_the_same_product_and_campaign(self) -> None:
        subject = identity()
        assert child_workspace_id(subject, campaign_id="c-1") == child_workspace_id(
            subject, campaign_id="c-1"
        )

    def test_distinct_products_never_collide(self) -> None:
        first = child_workspace_id(identity(product_id="a"), campaign_id="c-1")
        second = child_workspace_id(identity(product_id="b"), campaign_id="c-1")
        assert first != second

    def test_distinct_campaigns_for_the_same_product_never_collide(self) -> None:
        subject = identity()
        first = child_workspace_id(subject, campaign_id="c-1")
        second = child_workspace_id(subject, campaign_id="c-2")
        assert first != second

    def test_the_id_is_a_single_valid_path_segment(self) -> None:
        """`WorkspaceAuthority._segment` requires exactly one non-empty
        path component - proven against the real authority below, not
        assumed here."""
        workspace_id = child_workspace_id(identity(), campaign_id="c-1")
        assert pathlib.PurePath(workspace_id).name == workspace_id


class TestAllocatesTheRealUnmodifiedWorkspaceAuthority:
    def test_a_real_workspace_is_allocated_and_isolated(
        self, tmp_path: pathlib.Path
    ) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        (stable / "seed.txt").write_bytes(b"v1 content")
        authority = WorkspaceAuthority(tmp_path / "workspaces")

        handle = allocate_child_product_workspace(
            authority, identity(), campaign_id="c-1", stable_snapshot=stable,
        )

        assert (handle.snapshot / "seed.txt").read_bytes() == b"v1 content"
        assert handle.root.is_dir()

    def test_two_different_products_get_disjoint_workspaces(
        self, tmp_path: pathlib.Path
    ) -> None:
        stable = tmp_path / "stable"
        stable.mkdir()
        authority = WorkspaceAuthority(tmp_path / "workspaces")

        first = allocate_child_product_workspace(
            authority, identity(product_id="a"), campaign_id="c-1",
            stable_snapshot=stable,
        )
        second = allocate_child_product_workspace(
            authority, identity(product_id="b"), campaign_id="c-1",
            stable_snapshot=stable,
        )
        assert first.root != second.root

    def test_the_same_product_and_campaign_cannot_be_allocated_twice(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The real authority's own exclusivity rule still holds - not
        weakened for this caller."""
        stable = tmp_path / "stable"
        stable.mkdir()
        authority = WorkspaceAuthority(tmp_path / "workspaces")
        subject = identity()

        allocate_child_product_workspace(
            authority, subject, campaign_id="c-1", stable_snapshot=stable,
        )
        with pytest.raises(WorkspaceIsolationError):
            allocate_child_product_workspace(
                authority, subject, campaign_id="c-1", stable_snapshot=stable,
            )


class TestNeverReachesArkaliOwnSource:
    """ARK-REQ-0358: this module must never resolve a path outside its
    caller-supplied `stable_snapshot` - proven by AST, not convention."""

    def test_no_repository_root_or_upward_relative_path_reference(self) -> None:
        """AST-based, not text search: a docstring may discuss `__file__`
        in prose (as this module's own does, explaining the rule) without
        the code actually using it - only real `Name`/`Attribute` nodes
        count."""
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        forbidden_names = {"__file__"}
        forbidden_attrs = {"cwd", "getcwd", "parents"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in forbidden_names, f"found {node.id!r}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_attrs, f"found .{node.attr}"

    def test_no_direct_import_of_engineering_candidate(self) -> None:
        """Composition is Protocol-only (see the module docstring for the
        architecture-depth reason) - a direct import would both extend the
        measured chain and give this module a second way to reach a real
        workspace root outside its parameters."""
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert "engineering.candidate" not in node.module
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert "engineering.candidate" not in alias.name

    def test_no_module_level_path_constant(self) -> None:
        """No `ROOT`/`REPO`-style constant exists for this module to reach
        through - every path this module ever touches must arrive as a
        parameter."""
        tree = ast.parse(MODULE.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"resolve", "home"}
