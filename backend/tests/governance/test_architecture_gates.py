"""Phase 2 — the eight architecture gates and their negative controls.

Every gate is exercised twice: once against the live repository, and once
against a deliberately corrupted in-memory authority map or an isolated fixture
tree. A gate that cannot reject a defect is not evidence (ARK-REQ-0353).

No canonical repository file is written by any test here.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

from arkali.control.architecture.authority_map import AuthorityMap, BoundedContext
from arkali.control.architecture.gates.authority_gates import (
    DuplicateCanonicalAuthorityGate,
    DuplicateLifecycleAuthorityGate,
    DuplicateStateMachineAuthorityGate,
    ShadowRegistryGate,
)
from arkali.control.architecture.gates.base import GateContext
from arkali.control.architecture.gates.runner import GATE_IMPLEMENTATIONS, GateRunner
from arkali.control.architecture.gates.structure_gates import (
    ArchitectureBudgetGate,
    ForbiddenCyclesGate,
    ForbiddenDependencyDirectionGate,
    ProtectedCoreBoundaryGate,
)
from arkali.kernel.contracts.errors import GovernanceStateError
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture()
def live_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


@pytest.fixture()
def ctx(live_map: AuthorityMap) -> GateContext:
    return GateContext(REPO, live_map)


def mutate(amap: AuthorityMap, **changes: object) -> AuthorityMap:
    """In-memory mutation only. The repository file is never touched."""
    data = amap.model_dump()
    data.update(changes)
    return AuthorityMap.model_validate(data)


class TestGateRunnerReconciliation:
    def test_declared_and_implemented_gates_agree(self, live_map: AuthorityMap) -> None:
        GateRunner(REPO, live_map).reconcile()

    def test_all_eight_declared_gates_run(self, live_map: AuthorityMap) -> None:
        results = GateRunner(REPO, live_map).run_all()
        assert len(results) == len(live_map.architecture_gates) == 8
        assert len(GATE_IMPLEMENTATIONS) == 8

    def test_undeclared_gate_is_rejected(self, live_map: AuthorityMap) -> None:
        """NEGATIVE CONTROL: removing a declaration must fail closed."""
        trimmed = mutate(
            live_map,
            architecture_gates=tuple(list(live_map.architecture_gates)[:-1]),
        )
        with pytest.raises(GovernanceStateError) as exc:
            GateRunner(REPO, trimmed).run_all()
        assert "not declared" in str(exc.value)

    def test_unimplemented_gate_is_rejected(self, live_map: AuthorityMap) -> None:
        """NEGATIVE CONTROL: declaring a gate with no implementation fails closed."""
        extended = mutate(
            live_map,
            architecture_gates=live_map.architecture_gates
            + ({"id": "gate_that_does_not_exist", "threshold": 0},),
        )
        with pytest.raises(GovernanceStateError) as exc:
            GateRunner(REPO, extended).run_all()
        assert "not implemented" in str(exc.value)


class TestDuplicateCanonicalAuthorityGate:
    def test_live_passes(self, ctx: GateContext) -> None:
        assert DuplicateCanonicalAuthorityGate().evaluate(ctx).state is HonestState.PASS

    def test_duplicate_owner_is_rejected(self, live_map: AuthorityMap) -> None:
        """NEGATIVE CONTROL: one concern, two owners."""
        first = live_map.concerns[0]
        clash = first.model_copy(update={"owner": "kernel.contracts"})
        broken = mutate(live_map, concerns=live_map.concerns + (clash,))
        result = DuplicateCanonicalAuthorityGate().evaluate(GateContext(REPO, broken))
        assert result.state is HonestState.FAIL
        assert result.findings


class TestShadowRegistryGate:
    def test_live_passes(self, ctx: GateContext) -> None:
        assert ShadowRegistryGate().evaluate(ctx).state is HonestState.PASS

    def test_copying_permitted_is_rejected(self, live_map: AuthorityMap) -> None:
        """NEGATIVE CONTROL: permitting a second store of provider state."""
        authority = dict(live_map.provider_authority)
        authority["copying_permitted"] = True
        broken = mutate(live_map, provider_authority=authority)
        assert ShadowRegistryGate().evaluate(
            GateContext(REPO, broken)
        ).state is HonestState.FAIL

    def test_owner_listed_as_consumer_is_rejected(self, live_map: AuthorityMap) -> None:
        authority = dict(live_map.provider_authority)
        authority["reference_only_consumers"] = list(
            authority.get("reference_only_consumers", [])
        ) + [authority["owner"]]
        broken = mutate(live_map, provider_authority=authority)
        assert ShadowRegistryGate().evaluate(
            GateContext(REPO, broken)
        ).state is HonestState.FAIL


class TestDuplicateStateMachineAndLifecycleGates:
    def test_live_passes(self, ctx: GateContext) -> None:
        assert DuplicateStateMachineAuthorityGate().evaluate(ctx).state is HonestState.PASS
        assert DuplicateLifecycleAuthorityGate().evaluate(ctx).state is HonestState.PASS

    def test_unknown_state_machine_owner_is_rejected(
        self, live_map: AuthorityMap
    ) -> None:
        """NEGATIVE CONTROL."""
        owners = dict(live_map.state_machine_authorities)
        owners["Project"] = "context.that.does.not.exist"
        broken = mutate(live_map, state_machine_authorities=owners)
        assert DuplicateStateMachineAuthorityGate().evaluate(
            GateContext(REPO, broken)
        ).state is HonestState.FAIL

    def test_promotion_and_rollback_sharing_owner_is_rejected(
        self, live_map: AuthorityMap
    ) -> None:
        """NEGATIVE CONTROL: ADR-0009 forbids one authority doing both."""
        owners = dict(live_map.lifecycle_authorities)
        owners["stable_rollback"] = owners["candidate_promotion"]
        broken = mutate(live_map, lifecycle_authorities=owners)
        result = DuplicateLifecycleAuthorityGate().evaluate(GateContext(REPO, broken))
        assert result.state is HonestState.FAIL
        assert any("ADR-0009" in f.summary for f in result.findings)


class TestDependencyAndCycleGates:
    def test_live_dependency_direction(self, ctx: GateContext) -> None:
        result = ForbiddenDependencyDirectionGate().evaluate(ctx)
        assert result.state in (HonestState.PASS, HonestState.NOT_APPLICABLE)
        if result.state is HonestState.NOT_APPLICABLE:
            assert "vacuous" in result.detail

    def test_inverted_layers_are_rejected(self, live_map: AuthorityMap) -> None:
        """NEGATIVE CONTROL: invert the layer ranks so real edges become illegal.

        The live tree contains genuine cross-context imports; inverting ranks
        turns every one of them into an upward dependency.
        """
        inverted = {name: -rank for name, rank in live_map.layer_ranks.items()}
        broken = mutate(live_map, layer_ranks=inverted, sibling_edges=())
        result = ForbiddenDependencyDirectionGate().evaluate(GateContext(REPO, broken))
        assert result.state is HonestState.FAIL
        assert result.findings

    def test_live_cycles(self, ctx: GateContext) -> None:
        result = ForbiddenCyclesGate().evaluate(ctx)
        assert result.state in (HonestState.PASS, HonestState.NOT_APPLICABLE)

    def test_cycle_detection_rejects_a_cycle(self) -> None:
        """NEGATIVE CONTROL for the cycle finder itself."""
        from arkali.control.architecture.gates.structure_gates import _find_cycles

        assert _find_cycles({"a": {"b"}, "b": {"a"}})
        assert not _find_cycles({"a": {"b"}, "b": set()})


class TestProtectedCoreGate:
    def test_live_passes(self, ctx: GateContext) -> None:
        assert ProtectedCoreBoundaryGate().evaluate(ctx).state is HonestState.PASS

    def test_demoting_a_minimum_member_is_rejected(
        self, live_map: AuthorityMap
    ) -> None:
        """NEGATIVE CONTROL: control.policy silently leaving Protected Core."""
        contexts = copy.deepcopy(live_map.contexts)
        contexts["control.policy"] = BoundedContext(
            **{**contexts["control.policy"].model_dump(), "protected_core": False}
        )
        broken = mutate(live_map, contexts=contexts)
        result = ProtectedCoreBoundaryGate().evaluate(GateContext(REPO, broken))
        assert result.state is HonestState.FAIL
        assert any("control.policy" in f.summary for f in result.findings)


class TestArchitectureBudgetGate:
    def test_live_passes(self, ctx: GateContext) -> None:
        assert ArchitectureBudgetGate().evaluate(ctx).state is HonestState.PASS

    def test_impossible_budget_is_rejected(self, live_map: AuthorityMap) -> None:
        """NEGATIVE CONTROL: a budget the real tree cannot satisfy."""
        budgets = dict(live_map.architecture_budgets)
        budgets["max_module_logical_lines"] = 1
        broken = mutate(live_map, architecture_budgets=budgets)
        result = ArchitectureBudgetGate().evaluate(GateContext(REPO, broken))
        assert result.state is HonestState.FAIL
        assert result.findings


class TestCanonicalStateUnmodified:
    def test_gate_execution_does_not_mutate_the_authority_map(self) -> None:
        path = REPO / "docs" / "canonical" / "AUTHORITY_MAP.yaml"
        before = path.read_bytes()
        GateRunner(REPO, AuthorityMap.load(REPO)).run_all()
        assert path.read_bytes() == before
