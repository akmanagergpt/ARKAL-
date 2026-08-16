"""Deterministic real product generation tests (ARK-REQ-0233)."""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.specification.blueprint_contracts import (
    CandidateRequirement,
    ProductGoal,
    RequirementBlueprint,
    RequirementCategory,
)
from arkali.control.specification.blueprint_engine import derive_blueprint
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.engineering.factory.errors import UnresolvedBlueprintError
from arkali.engineering.factory.product_generation import (
    GENERATED_MODULE_RELPATH,
    generate_product,
    render_module,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def authority_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


@pytest.fixture
def workspace(tmp_path: pathlib.Path):
    stable = tmp_path / "stable"
    stable.mkdir()
    (stable / "README.md").write_text("x", encoding="utf-8")
    authority = WorkspaceAuthority(tmp_path / "workspaces")
    return authority.allocate(
        workspace_id="ws-test", task_id="task-1", agent_id="agent-1",
        stable_snapshot=stable,
    )


class TestUnresolvedBlueprintIsRefused:
    def test_a_blueprint_with_missing_acceptance_criteria_is_refused(
        self, authority_map: AuthorityMap, workspace,
    ) -> None:
        blueprint = derive_blueprint("Orders must persist.", authority_map)
        assert not blueprint.is_fully_resolved
        with pytest.raises(UnresolvedBlueprintError):
            generate_product(blueprint, workspace)

    def test_refusal_writes_nothing_to_the_workspace(
        self, authority_map: AuthorityMap, workspace,
    ) -> None:
        blueprint = derive_blueprint("Orders must persist.", authority_map)
        with pytest.raises(UnresolvedBlueprintError):
            generate_product(blueprint, workspace)
        assert not (workspace.root / GENERATED_MODULE_RELPATH).exists()


class TestDerivedChecksAreRealNotFabricated:
    def test_a_numeric_criterion_yields_a_real_comparison_function(
        self, authority_map: AuthorityMap,
    ) -> None:
        blueprint = derive_blueprint(
            "The system must respond within at least 200 ms.", authority_map,
        )
        assert blueprint.is_fully_resolved
        source, functions = render_module(blueprint)
        assert len(functions) == 1
        assert functions[0].is_derived_check
        assert ">= 200" in source

    def test_a_criterion_the_numeric_pattern_cannot_parse_is_honestly_acknowledged(
        self,
    ) -> None:
        """Constructed directly, bypassing `derive_blueprint`: Phase 15's own
        engine only ever emits acceptance criteria matching this same numeric
        pattern, so a fully-resolved blueprint from it never actually reaches
        this branch today — this proves the defensive path is correct and
        honest (never an unimplemented marker) rather than claiming it is exercised
        by the current Phase 15 output."""
        goal = ProductGoal(goal_text="A requirement with a non-numeric criterion.")
        requirement = CandidateRequirement(
            index=0, statement="Something must be true.",
            category=RequirementCategory.FUNCTIONAL,
            acceptance_criteria=("a free-text criterion no pattern parses",),
        )
        blueprint = RequirementBlueprint(goal=goal, requirements=(requirement,))
        assert blueprint.is_fully_resolved
        _, functions = render_module(blueprint)
        assert len(functions) == 1
        assert not functions[0].is_derived_check

    def test_generated_source_contains_a_real_body_not_an_empty_one(
        self, authority_map: AuthorityMap,
    ) -> None:
        """The generated (untracked) source is checked for a genuine body
        shape here; the repository's own structure scanner separately covers
        all tracked source repo-wide."""
        blueprint = derive_blueprint(
            "The system must respond within at least 200 ms.", authority_map,
        )
        source, _ = render_module(blueprint)
        assert "return measured" in source or "return {" in source
        assert "..." not in source


class TestGeneratedModuleIsReallyImportableAndExecutable:
    def test_the_generated_module_imports_and_the_function_computes_correctly(
        self, authority_map: AuthorityMap, workspace,
    ) -> None:
        blueprint = derive_blueprint(
            "The system must respond within at least 200 ms.", authority_map,
        )
        product = generate_product(blueprint, workspace)
        module_path = workspace.path_for(product.module_relpath)
        assert module_path.is_file()

        spec = importlib.util.spec_from_file_location("generated_product_test", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        fn = getattr(module, product.functions[0].name)
        assert fn(150) is False   # 150 is not >= 200
        assert fn(250) is True    # 250 is >= 200

    def test_generation_writes_only_inside_the_workspace_root(
        self, authority_map: AuthorityMap, workspace,
    ) -> None:
        blueprint = derive_blueprint(
            "The system must respond within at least 200 ms.", authority_map,
        )
        product = generate_product(blueprint, workspace)
        resolved = workspace.path_for(product.module_relpath).resolve()
        assert resolved.is_relative_to(workspace.root.resolve())


class TestProgressiveComplexity:
    """ARK-REQ-0233: 'progressively harder' is measured, not asserted."""

    def test_a_blueprint_with_more_requirements_generates_more_functions(
        self, authority_map: AuthorityMap, workspace,
    ) -> None:
        small = derive_blueprint(
            "The system must respond within at least 200 ms.", authority_map,
        )
        larger = derive_blueprint(
            "The system must respond within at least 200 ms. "
            "The system must support at most 500 users. "
            "The system must be available for at least 99 percent.",
            authority_map,
        )
        assert larger.is_fully_resolved
        small_product = generate_product(small, workspace)
        larger_product = generate_product(larger, workspace)
        assert len(larger_product.functions) > len(small_product.functions)
        assert larger_product.derived_check_count > small_product.derived_check_count
