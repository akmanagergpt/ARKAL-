"""Drift and negative controls for the ERR-003 budget measurement contract.

Closes F-0020. The ruling requires seven specific proofs; each has a test class
below. All fixtures are in-memory or a temporary copy of the authority map — no
accepted repository state is modified.

The controls call the same `budget_measurement` module the gate calls. A test
computing complexity its own way would be a second formula, which is exactly the
defect the measurement contract exists to prevent (F-0013).
"""

from __future__ import annotations

import copy
import pathlib

import pytest
import yaml
from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.budget_measurement import (
    MEASUREMENT_KEY,
    MeasurementContract,
    measure_module,
    measure_orchestration_depth,
)
from arkali.control.architecture.gates.base import GateContext
from arkali.control.architecture.gates.structure_gates import ArchitectureBudgetGate
from arkali.kernel.contracts.errors import AuthoritativeSourceError
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]
AUTHORITY_MAP_PATH = REPO / "docs/canonical/AUTHORITY_MAP.yaml"


@pytest.fixture(scope="module")
def authority_map() -> AuthorityMap:
    return AuthorityMap.load(REPO)


@pytest.fixture(scope="module")
def contract(authority_map: AuthorityMap) -> MeasurementContract:
    return MeasurementContract.from_authority_map(
        {MEASUREMENT_KEY: authority_map.architecture_budget_measurement},
        authority_map.source_path,
    )


def score_of(source: str, contract: MeasurementContract, name: str) -> int:
    scores = measure_module(source, contract, module="fixture", allowed_maximum=12)
    match = [s for s in scores if s.function == name]
    assert match, f"fixture function {name!r} was not measured"
    return match[0].score


def function_with_complexity(target: int) -> str:
    """A function whose measured complexity is exactly `target`.

    Built from plain `if` statements, each contributing one decision point on
    top of the base of 1. The construction is deliberately boring so the
    fixture's own complexity is not in question.
    """
    branches = "\n".join(
        f"    if value == {n}:\n        return {n}" for n in range(target - 1)
    )
    return f"def subject(value):\n{branches}\n    return -1\n"


class TestFixtureConstructionIsSound:
    """Asserts the controls' own prerequisite before they assert anything else."""

    def test_generator_produces_the_requested_complexity(
        self, contract: MeasurementContract
    ) -> None:
        for target in (5, 12, 13, 20):
            assert score_of(function_with_complexity(target), contract, "subject") == (
                target
            )


class TestControl1And2ComplexityBoundary:
    def test_1_function_at_twelve_passes(self, contract: MeasurementContract) -> None:
        scores = measure_module(
            function_with_complexity(12), contract, module="f", allowed_maximum=12
        )
        assert scores[0].score == 12
        assert scores[0].passed is True

    def test_2_function_at_thirteen_fails(self, contract: MeasurementContract) -> None:
        scores = measure_module(
            function_with_complexity(13), contract, module="f", allowed_maximum=12
        )
        assert scores[0].score == 13
        assert scores[0].passed is False

    def test_result_records_every_field_the_ruling_requires(
        self, contract: MeasurementContract
    ) -> None:
        score = measure_module(
            function_with_complexity(13), contract, module="m.py", allowed_maximum=12
        )[0]
        assert score.contract_version == contract.version
        assert score.module == "m.py"
        assert score.function == "subject"
        assert score.line > 0
        assert score.score == 13
        assert score.allowed_maximum == 12
        assert "FAIL" in score.render()

    def test_nested_functions_are_measured_independently(
        self, contract: MeasurementContract
    ) -> None:
        source = (
            "def outer(a):\n"
            "    def inner(b):\n"
            "        if b:\n"
            "            return 1\n"
            "        return 2\n"
            "    return inner\n"
        )
        assert score_of(source, contract, "outer") == 1
        assert score_of(source, contract, "inner") == 2


class TestControl3And4And5OrchestrationDepth:
    def test_3_depth_four_passes(self, contract: MeasurementContract) -> None:
        graph = {"a": {"b"}, "b": {"c"}, "c": {"d"}, "d": set()}
        found = measure_orchestration_depth(graph, contract, allowed_maximum=4)
        assert found.depth == 4
        assert found.passed is True
        assert found.path == ("a", "b", "c", "d")

    def test_4_depth_five_fails(self, contract: MeasurementContract) -> None:
        graph = {"a": {"b"}, "b": {"c"}, "c": {"d"}, "d": {"e"}, "e": set()}
        found = measure_orchestration_depth(graph, contract, allowed_maximum=4)
        assert found.depth == 5
        assert found.passed is False
        assert found.path == ("a", "b", "c", "d", "e")

    def test_5_cycle_fails_independently_of_depth(
        self, contract: MeasurementContract
    ) -> None:
        graph = {"a": {"b"}, "b": {"c"}, "c": {"a"}}
        found = measure_orchestration_depth(graph, contract, allowed_maximum=99)
        assert found.passed is False
        assert found.cycles, "cycle was not reported"

    def test_unresolvable_ownership_fails_closed(
        self, contract: MeasurementContract
    ) -> None:
        graph = {"a": {"b"}, "b": set()}
        found = measure_orchestration_depth(
            graph, contract, allowed_maximum=4, unresolved=("m.py -> arkali.ghost",)
        )
        assert found.passed is False
        assert found.unresolved

    def test_max_depth_path_is_recorded(self, contract: MeasurementContract) -> None:
        graph = {"a": {"b"}, "b": {"c"}, "c": set(), "x": set()}
        found = measure_orchestration_depth(graph, contract, allowed_maximum=4)
        assert " -> ".join(found.path) in found.render()


class TestControl6BudgetChangeFlipsVerdictWithoutEditingValidator:
    def _map_with(self, tmp_path: pathlib.Path, **budget_overrides: int) -> AuthorityMap:
        raw = yaml.safe_load(AUTHORITY_MAP_PATH.read_text(encoding="utf-8"))
        mutated = copy.deepcopy(raw)
        mutated["architecture_budgets"].update(budget_overrides)
        target = tmp_path / "docs" / "canonical"
        target.mkdir(parents=True)
        (target / "AUTHORITY_MAP.yaml").write_text(
            yaml.safe_dump(mutated), encoding="utf-8"
        )
        return AuthorityMap.load(tmp_path)

    def test_6_lowering_the_complexity_budget_flips_the_gate_to_fail(
        self, tmp_path: pathlib.Path
    ) -> None:
        """No validator source is edited; only the authoritative number moves."""
        lowered = self._map_with(tmp_path, max_cyclomatic_complexity_per_function=3)
        result = ArchitectureBudgetGate().evaluate(GateContext(REPO, lowered))
        assert result.state is HonestState.FAIL

    def test_6b_lowering_the_depth_budget_flips_the_gate_to_fail(
        self, tmp_path: pathlib.Path
    ) -> None:
        lowered = self._map_with(tmp_path, max_orchestration_depth=1)
        result = ArchitectureBudgetGate().evaluate(GateContext(REPO, lowered))
        assert result.state is HonestState.FAIL

    def test_6c_the_live_budget_passes(self, authority_map: AuthorityMap) -> None:
        result = ArchitectureBudgetGate().evaluate(GateContext(REPO, authority_map))
        assert result.state is HonestState.PASS, result.summary


class TestControl7ContractChangeIsDetectableAndAuditable:
    def test_7_contract_version_travels_with_every_measurement(
        self, contract: MeasurementContract
    ) -> None:
        score = measure_module(
            function_with_complexity(4), contract, module="m", allowed_maximum=12
        )[0]
        depth = measure_orchestration_depth({"a": set()}, contract, allowed_maximum=4)
        assert score.contract_version == contract.version
        assert depth.contract_version == contract.version
        assert contract.version in score.render()
        assert contract.version in depth.render()

    def test_gate_evidence_records_the_contract_version(
        self, authority_map: AuthorityMap
    ) -> None:
        result = ArchitectureBudgetGate().evaluate(GateContext(REPO, authority_map))
        assert f"measurement_contract={authority_map.architecture_budget_measurement['contract_version']}" in result.detail

    def test_changing_a_formula_changes_the_measurement(
        self, authority_map: AuthorityMap
    ) -> None:
        """Removing a decision-point rule must lower the score, provably."""
        raw = copy.deepcopy(authority_map.architecture_budget_measurement)
        raw["contract_version"] = "9.9.9-test"
        raw["cyclomatic_complexity"]["increment_per_node"].pop("If")
        altered = MeasurementContract.from_authority_map(
            {MEASUREMENT_KEY: raw}, "in-memory"
        )
        source = function_with_complexity(8)
        assert score_of(source, altered, "subject") == 1
        assert altered.version == "9.9.9-test"

    def test_missing_measurement_contract_fails_closed(self) -> None:
        with pytest.raises(AuthoritativeSourceError):
            MeasurementContract.from_authority_map({}, "in-memory")

    def test_contract_without_a_version_fails_closed(
        self, authority_map: AuthorityMap
    ) -> None:
        raw = copy.deepcopy(authority_map.architecture_budget_measurement)
        raw.pop("contract_version")
        with pytest.raises(AuthoritativeSourceError):
            MeasurementContract.from_authority_map(
                {MEASUREMENT_KEY: raw}, "in-memory"
            )

    def test_contract_missing_a_section_fails_closed(
        self, authority_map: AuthorityMap
    ) -> None:
        raw = copy.deepcopy(authority_map.architecture_budget_measurement)
        raw.pop("orchestration_depth")
        with pytest.raises(AuthoritativeSourceError):
            MeasurementContract.from_authority_map(
                {MEASUREMENT_KEY: raw}, "in-memory"
            )


class TestSingleSourceOfMeasurementTruth:
    def test_every_declared_budget_is_now_enforced(
        self, authority_map: AuthorityMap
    ) -> None:
        """ERR-003 closed F-0020; nothing may remain awaiting a formula."""
        assert ArchitectureBudgetGate.AWAITING_CANONICAL_FORMULA == ()
        declared = {
            name
            for name, value in authority_map.architecture_budgets.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
        assert declared == set(ArchitectureBudgetGate.ENFORCED)

    def test_live_repository_has_no_function_over_budget(
        self, authority_map: AuthorityMap, contract: MeasurementContract
    ) -> None:
        from arkali.control.architecture.gates.structure_gates import iter_modules

        allowed = int(
            authority_map.architecture_budgets["max_cyclomatic_complexity_per_function"]
        )
        over = [
            score.render()
            for path in iter_modules(REPO)
            for score in measure_module(
                path.read_text(encoding="utf-8"),
                contract,
                module=path.relative_to(REPO).as_posix(),
                allowed_maximum=allowed,
            )
            if not score.passed
        ]
        assert over == []

    def test_live_orchestration_depth_is_within_budget(
        self, authority_map: AuthorityMap, contract: MeasurementContract
    ) -> None:
        found = ArchitectureBudgetGate.measure_depth(
            GateContext(REPO, authority_map),
            authority_map.architecture_budgets,
            contract,
        )
        assert found.passed, found.render()
        assert found.cycles == ()
        assert found.unresolved == ()
