"""C-36 consolidated adversarial/authority proofs for the whole child-product
SDK (Packages 1-5), one audit-friendly location covering every attack class
requested for Phase 24 Package 6.

MOST OF THESE ARE ALREADY PROVEN, NOT RE-ASSERTED HERE. Several classes were
already proven, with real negative controls, by the packages that built the
mechanism they attack - re-testing them here would be duplication, not
depth. This file states where each already lives and adds only the classes
those packages did not yet cover on their own.

Attack class -> where it is proven, in `test_child_product_promotion.py`
unless noted:
  self-approval
    -> test_a_barred_actor_cannot_manufacture_its_own_grant
  cross-product authorization reuse
    -> test_a_grant_for_a_different_product_does_not_leak
  wrong digest / wrong candidate
    -> test_a_grant_for_a_different_candidate_does_not_leak
  wrong target / wrong gate
    -> test_a_grant_for_a_different_gate_does_not_satisfy_gate_3
  stale grant / replay
    -> test_a_stale_grant_..., test_the_same_grant_does_not_authorize_a_second_promotion
  alternate promotion path
    -> test_child_product_no_direct_promotion.py (AST: only
       child_product_promotion.py calls .append)
  unauthorized rollback (orchestration bypass)
    -> test_child_product_rollback.py::test_restore_to_is_called_only_here_... (AST)
  direct stable/live mutation, core-copy, ARKALI core promotion misuse,
  campaign restart manipulation, shadow authority
    -> new in this file, below
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

import pytest

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.runner import GateRunner
from arkali.kernel.contracts.content_address import address_of
from arkali.kernel.contracts.state_machine_errors import TerminalStateEscape
from arkali.lifecycle.evolution import evolution_campaign_state_machine as ecsm
from arkali.lifecycle.evolution.campaign_declaration import CampaignBudgets
from arkali.lifecycle.evolution.child_product_campaign import (
    declare_child_product_campaign,
)
from arkali.lifecycle.evolution.child_product_identity import (
    ChildProductIdentity,
    ChildProductMode,
)
from arkali.lifecycle.evolution.child_product_promotion import (
    PROMOTE_CHILD_PRODUCT_OPERATION,
)
from arkali.lifecycle.evolution.child_product_rollback import rollback_child_product
from arkali.lifecycle.evolution.child_product_version import (
    ChildProductVersion,
    ChildProductVersionLineage,
)
from arkali.lifecycle.evolution.core_upgrade_orchestrator import (
    CORE_PROMOTION_OPERATION,
)
from arkali.lifecycle.evolution.errors import (
    ChildProductRollbackRequestInvalidError,
    UnknownVersionReferenceError,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
EVOLUTION_DIR: Final[pathlib.Path] = REPO / "backend/arkali/lifecycle/evolution"
CHILD_PRODUCT_MODULES: Final[tuple[pathlib.Path, ...]] = tuple(
    sorted(EVOLUTION_DIR.glob("child_product_*.py"))
)


def content_ref(label: str) -> str:
    return address_of(label.encode("utf-8"))


def identity(**updates: object) -> ChildProductIdentity:
    values: dict[str, object] = {
        "product_id": "acme-task-tracker",
        "name": "Acme Task Tracker",
        "mode": ChildProductMode.AI_NATIVE_SELF_EVOLVING,
    }
    values.update(updates)
    return ChildProductIdentity.model_validate(values)


def budgets(**updates: object) -> CampaignBudgets:
    from decimal import Decimal

    values: dict[str, object] = {
        "candidate_budget": 5, "ai_call_budget": 20, "time_budget_seconds": 3600,
        "cost_budget": Decimal("10.00"), "regression_ceiling": 0,
        "no_progress_threshold": 3,
    }
    values.update(updates)
    return CampaignBudgets.model_validate(values)


class TestNoDirectStableOrLiveMutationAnywhereInTheChildProductSdk:
    """Direct stable/live mutation: across every `child_product_*.py`
    module, not just promotion/rollback individually - the whole SDK
    surface, in one sweep."""

    def test_no_child_product_module_imports_lifecycle_release_or_recovery(
        self,
    ) -> None:
        offenders = []
        for path in CHILD_PRODUCT_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if "lifecycle.release" in node.module or "lifecycle.recovery" in node.module:
                        offenders.append((path.name, node.module))
        assert not offenders, f"unexpected import of a Stable-mutation authority: {offenders}"

    def test_no_module_names_the_real_mutating_methods(self) -> None:
        """`.promote`/`.rollback_to` are `StableRevisionPointer`'s own
        method names (reused by nothing here - the child-product lineage's
        own analogous methods are named `append`/`restore_to` specifically
        to avoid this exact collision, per Package 5's own repair)."""
        offenders = []
        for path in CHILD_PRODUCT_MODULES:
            called = {
                node.func.attr
                for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            }
            hit = called & {"promote", "rollback_to"}
            if hit:
                offenders.append((path.name, sorted(hit)))
        assert not offenders, f"unexpected Stable-mutating method name: {offenders}"


class TestArkaliCorePromotionCannotBeReachedOrMisused:
    """ARKALI core promotion misuse: `PROMOTE_CHILD_PRODUCT` and
    `CORE_PROMOTION` must be, and stay, two distinct `RUNTIME_OPERATION`
    scoping keys - a grant for one must never be constructible as the
    other, and no child-product code may present `CORE_PROMOTION` as its
    own operation class."""

    def test_the_two_operation_classes_are_distinct_strings(self) -> None:
        assert PROMOTE_CHILD_PRODUCT_OPERATION != CORE_PROMOTION_OPERATION

    def test_no_child_product_module_references_core_promotion(self) -> None:
        """AST-based, not text search: `child_product_promotion.py`'s own
        docstring legitimately *names* `CORE_PROMOTION` in prose, explaining
        why the two scoping keys are parallel and distinct - only a real
        `Import`/`Name` node naming the symbol would mean actual code
        reaches it."""
        offenders = []
        for path in CHILD_PRODUCT_MODULES:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if any(alias.name == "CORE_PROMOTION_OPERATION" for alias in node.names):
                        offenders.append(path.name)
                if isinstance(node, ast.Name) and node.id == "CORE_PROMOTION_OPERATION":
                    offenders.append(path.name)
        assert not offenders, f"child-product code references CORE_PROMOTION_OPERATION: {offenders}"


class TestUnauthorizedRollbackDefenseInDepth:
    """Even bypassing the `rollback_child_product` orchestration entirely
    and calling the lower-level primitive directly, an unrecorded target is
    still refused - the safety property is not solely the orchestration
    wrapper's responsibility."""

    def test_the_lineage_primitive_itself_refuses_an_unrecorded_target(self) -> None:
        subject = identity()
        lineage = ChildProductVersionLineage(product_ref=subject.product_ref).append(
            ChildProductVersion(sequence=1, content_ref=content_ref("v1"), campaign_id="c-1")
        )
        with pytest.raises(UnknownVersionReferenceError):
            lineage.restore_to("sha256:" + "e" * 64, campaign_id="attack")

    def test_rollback_child_product_refuses_a_lineage_from_a_different_product(
        self,
    ) -> None:
        attacker_identity = identity(product_id="attacker-claimed-product")
        victim_lineage = ChildProductVersionLineage(
            product_ref=identity(product_id="victim-product").product_ref
        ).append(
            ChildProductVersion(sequence=1, content_ref=content_ref("v1"), campaign_id="c-1")
        )
        with pytest.raises(ChildProductRollbackRequestInvalidError):
            rollback_child_product(
                victim_lineage, attacker_identity,
                target_version_ref=victim_lineage.versions[0].version_ref,
                reason="attempted cross-product rollback",
            )


class TestCampaignRestartManipulation:
    """A child-product campaign reuses the real, unmodified Phase 23
    `EvolutionCampaign` machine (Package 1) - its own terminal-state
    discipline (`TerminalStateEscape`, `kernel.contracts.state_machine`)
    already forbids restarting a finished campaign to try for a different
    outcome. Proven directly against a child-product-declared instance,
    not assumed from Phase 23's own proof of the machine in the abstract.
    """

    def test_a_terminal_child_campaign_cannot_be_restarted(self) -> None:
        subject = identity()
        declaration = declare_child_product_campaign(
            subject, objective="add recurring tasks",
            baseline_metrics={"feature_count": 4.0}, budgets=budgets(),
        )
        instance = ecsm.build().start("DECLARED")
        instance.apply("RUNNING", declaration.guard_context())
        instance.apply("BLOCKED")  # reaches one of the four terminal states

        with pytest.raises(TerminalStateEscape):
            instance.apply("RUNNING")

    def test_no_new_state_machine_authority_was_minted_for_child_products(self) -> None:
        """The instance really is Phase 23's own machine definition, not a
        child-product look-alike (mirrors
        `test_child_product_campaign.py`'s identical proof, restated here
        as part of the consolidated adversarial sweep)."""
        subject = identity()
        declaration = declare_child_product_campaign(
            subject, objective="x", baseline_metrics={"m": 1.0}, budgets=budgets(),
        )
        instance = ecsm.build().start("DECLARED")
        instance.apply("RUNNING", declaration.guard_context())
        assert instance.machine.definition is ecsm.DEFINITION


class TestNoShadowAuthority:
    """No second parser, PDP/PEP, campaign authority, or human-gate
    mechanism was introduced anywhere in the child-product SDK - enforced
    by the same live architecture gates every other phase's acceptance
    already depends on, re-run here as an explicit adversarial assertion
    rather than assumed from an earlier package's own gate run."""

    def test_no_duplicate_state_machine_or_canonical_authority_exists(self) -> None:
        amap = AuthorityMap.load(REPO)
        results = {
            r.check_id: r for r in GateRunner(REPO, amap).run_all()
        }
        for check_id in (
            "duplicate_state_machine_authority", "duplicate_canonical_authority",
            "duplicate_lifecycle_authority", "shadow_registry",
        ):
            assert str(results[check_id].state).endswith("PASS"), (
                f"{check_id}: {results[check_id].summary}"
            )

    def test_no_child_product_module_defines_its_own_authorization_table_parser(
        self,
    ) -> None:
        """The scoped-grant lookup is reused by reference
        (`GovernanceState.operation_grant`, a structural `Protocol`), never
        reimplemented - no child-product module parses
        `HUMAN_GATE_RECORDS.md` or any markdown table itself."""
        offenders = [
            path.name for path in CHILD_PRODUCT_MODULES
            if "HUMAN_GATE_RECORDS" in path.read_text(encoding="utf-8")
            or "_tables(" in path.read_text(encoding="utf-8")
        ]
        assert not offenders, f"unexpected authorization-table parsing: {offenders}"
