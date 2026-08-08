"""Permanent guard: every declared numeric budget is accounted for.

Defect class F-0019. The budget gate evaluated three of nine declared budgets
while reporting "all modules respect the numeric architecture budgets". The
claim was wider than the check's field of view — the same root cause as F-0008
(mapping asserted without probing), F-0013 (verified a private copy) and F-0016
(inspected the index instead of the working tree).

The durable fix is not "enforce the six that were missing". It is this test: a
budget declared in AUTHORITY_MAP.yaml must be either enforced by the gate or
explicitly recorded as awaiting a canonical measurement formula. A budget added
later cannot be silently ignored, because it will belong to neither set and this
will fail.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.base import GateContext
from arkali.control.architecture.gates.structure_gates import ArchitectureBudgetGate
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def authority_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


def numeric_budgets(authority_map: AuthorityMap) -> set[str]:
    """Numeric budgets only. The boolean exception-policy keys are not budgets."""
    return {
        name
        for name, value in authority_map.architecture_budgets.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }


class TestEveryDeclaredBudgetIsAccountedFor:
    def test_declared_budget_set_is_not_empty(self, authority_map: AuthorityMap) -> None:
        """Asserts the control's own prerequisite before asserting coverage."""
        assert numeric_budgets(authority_map), "authority map declares no numeric budget"

    def test_no_declared_budget_is_silently_unhandled(
        self, authority_map: AuthorityMap
    ) -> None:
        handled = set(ArchitectureBudgetGate.ENFORCED) | set(
            ArchitectureBudgetGate.AWAITING_CANONICAL_FORMULA
        )
        unhandled = sorted(numeric_budgets(authority_map) - handled)
        assert unhandled == [], (
            f"budgets declared but neither enforced nor recorded as awaiting a "
            f"canonical formula: {unhandled}"
        )

    def test_gate_does_not_claim_a_budget_the_map_does_not_declare(
        self, authority_map: AuthorityMap
    ) -> None:
        declared = numeric_budgets(authority_map)
        claimed = set(ArchitectureBudgetGate.ENFORCED) | set(
            ArchitectureBudgetGate.AWAITING_CANONICAL_FORMULA
        )
        assert sorted(claimed - declared) == []

    def test_enforced_and_deferred_sets_are_disjoint(self) -> None:
        overlap = set(ArchitectureBudgetGate.ENFORCED) & set(
            ArchitectureBudgetGate.AWAITING_CANONICAL_FORMULA
        )
        assert overlap == set()

    def test_deferred_set_is_declared_honestly_and_is_not_a_dumping_ground(
        self, authority_map: AuthorityMap
    ) -> None:
        """Most budgets must actually be enforced, or the gate means nothing."""
        declared = numeric_budgets(authority_map)
        enforced = set(ArchitectureBudgetGate.ENFORCED)
        assert len(enforced) > len(declared) / 2


class TestGateEvaluatesTheEnforcedSet:
    def test_live_tree_passes_every_enforced_budget(
        self, authority_map: AuthorityMap
    ) -> None:
        result = ArchitectureBudgetGate().evaluate(
            GateContext(REPO, authority_map)
        )
        assert result.state is HonestState.PASS, result.summary

    def test_result_detail_names_the_evaluated_budgets(
        self, authority_map: AuthorityMap
    ) -> None:
        """The scope is stated in evidence, not left to be inferred."""
        result = ArchitectureBudgetGate().evaluate(GateContext(REPO, authority_map))
        for name in ArchitectureBudgetGate.ENFORCED:
            assert name in result.detail
        for name in ArchitectureBudgetGate.AWAITING_CANONICAL_FORMULA:
            assert name in result.detail
