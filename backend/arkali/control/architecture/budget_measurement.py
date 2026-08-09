"""Executable architecture-budget measurement contract (ERR-003, closes F-0020).

Owner: control.architecture (Protected Core). This is the measurement half of
the existing `architecture_budgets` declaration, not a second budget authority.

SINGLE SOURCE OF MEASUREMENT TRUTH. Every formula is read from
`AUTHORITY_MAP.yaml` `architecture_budget_measurement` at call time. The node
types that increment complexity, the amounts, the exclusions, the orchestration
subject and the fail-closed rules are all governed data. Nothing here hard-codes
a decision-point list, so changing the contract changes every verdict without
editing a validator, and no two validators can drift onto different formulas.

Both the architecture gate and the tests call this module. A test computing
complexity its own way would be a private copy of the formula - the F-0013
defect - so none does.

`contract_version` travels with every result. A change to the formula is
therefore auditable and cannot be mistaken for a change in the code measured.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from arkali.control.architecture.refusal import refuse

MEASUREMENT_KEY = "architecture_budget_measurement"


class ComplexityScore(BaseModel):
    """One measured function. Immutable evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str
    module: str
    function: str
    line: int
    score: int
    allowed_maximum: int

    @property
    def passed(self) -> bool:
        return self.score <= self.allowed_maximum

    def render(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"{verdict} {self.module}:{self.function} (line {self.line}) "
            f"complexity {self.score} <= {self.allowed_maximum} "
            f"[contract {self.contract_version}]"
        )


class DepthMeasurement(BaseModel):
    """Longest orchestration chain, with the path that produced it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str
    depth: int
    allowed_maximum: int
    path: tuple[str, ...]
    cycles: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.depth <= self.allowed_maximum
            and not self.cycles
            and not self.unresolved
        )

    def render(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"{verdict} orchestration depth {self.depth} <= "
            f"{self.allowed_maximum} via {' -> '.join(self.path) or '(none)'} "
            f"[contract {self.contract_version}]"
        )


class MeasurementContract:
    """The ratified formulas, parsed from the authority map."""

    def __init__(self, raw: Mapping[str, Any], source_path: str) -> None:
        self._raw = raw
        self.source_path = source_path
        self.version = str(raw.get("contract_version", "")).strip()
        if not self.version:
            raise refuse(
                "budget measurement contract declares no contract_version",
                source=source_path,
            )
        self._cyclomatic = raw.get("cyclomatic_complexity") or {}
        self._depth = raw.get("orchestration_depth") or {}
        if not self._cyclomatic or not self._depth:
            raise refuse(
                "budget measurement contract is missing a required section",
                source=source_path,
            )

    @classmethod
    def from_authority_map(
        cls, raw_map: Mapping[str, Any], source_path: str
    ) -> MeasurementContract:
        section = raw_map.get(MEASUREMENT_KEY)
        if not section:
            raise refuse(
                f"authority map declares no {MEASUREMENT_KEY!r} section; budgets "
                "cannot be measured without a ratified formula",
                source=source_path,
            )
        return cls(section, source_path)

    # -- cyclomatic complexity ------------------------------------------------

    @property
    def base(self) -> int:
        return int(self._cyclomatic.get("base", 1))

    @property
    def node_increments(self) -> dict[str, int]:
        return {
            str(k): int(v)
            for k, v in (self._cyclomatic.get("increment_per_node") or {}).items()
        }

    @property
    def boolean_increment(self) -> int:
        raw = self._cyclomatic.get("increment_per_boolean_value_beyond_first") or {}
        return int(raw.get("BoolOp", 0))

    @property
    def measures_nested_independently(self) -> bool:
        return bool(self._cyclomatic.get("nested_functions_measured_independently"))

    # -- orchestration depth --------------------------------------------------

    @property
    def cycle_is_failure(self) -> bool:
        return str(self._depth.get("on_cycle", "FAIL")).upper() == "FAIL"

    @property
    def unresolved_is_failure(self) -> bool:
        return (
            str(self._depth.get("on_unresolvable_context_ownership", "FAIL")).upper()
            == "FAIL"
        )

    @property
    def ignores_self_edges(self) -> bool:
        return bool(self._depth.get("self_edges_ignored", True))


def _decision_points(node: ast.AST, contract: MeasurementContract) -> int:
    """Sum contract-declared decision points inside one function body.

    Nested function bodies are skipped when the contract says they are measured
    independently, so a helper defined inside a function does not inflate its
    parent's score.
    """
    increments = contract.node_increments
    boolean = contract.boolean_increment
    total = 0
    stack: list[ast.AST] = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        name = type(current).__name__
        if contract.measures_nested_independently and name in (
            "FunctionDef",
            "AsyncFunctionDef",
        ):
            continue
        total += increments.get(name, 0)
        if name == "comprehension":
            total += increments.get("comprehension_if", 0) * len(
                getattr(current, "ifs", [])
            )
        if name == "match_case":
            total += 0  # counted by the increments lookup above
        if name == "BoolOp" and boolean:
            total += boolean * (len(getattr(current, "values", [])) - 1)
        stack.extend(ast.iter_child_nodes(current))
    return total


def measure_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    contract: MeasurementContract,
    *,
    module: str,
    allowed_maximum: int,
) -> ComplexityScore:
    """Measure one function under the ratified formula."""
    return ComplexityScore(
        contract_version=contract.version,
        module=module,
        function=node.name,
        line=node.lineno,
        score=contract.base + _decision_points(node, contract),
        allowed_maximum=allowed_maximum,
    )


def measure_module(
    source: str, contract: MeasurementContract, *, module: str, allowed_maximum: int
) -> list[ComplexityScore]:
    """Every function and method in one module, nested ones included."""
    tree = ast.parse(source)
    return [
        measure_function(
            node, contract, module=module, allowed_maximum=allowed_maximum
        )
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def measure_orchestration_depth(
    edges: Mapping[str, set[str]],
    contract: MeasurementContract,
    *,
    allowed_maximum: int,
    unresolved: tuple[str, ...] = (),
) -> DepthMeasurement:
    """Longest directed chain over the context graph, with its exact path.

    A cycle fails independently of depth: an unbounded chain has no meaningful
    maximum, so reporting a number would be misleading. Unresolvable context
    ownership fails closed, because a module whose owner is unknown could sit
    anywhere in the graph.
    """
    cycles = _find_cycle_paths(edges)
    if cycles and contract.cycle_is_failure:
        return DepthMeasurement(
            contract_version=contract.version,
            depth=allowed_maximum + 1,
            allowed_maximum=allowed_maximum,
            path=(),
            cycles=cycles,
            unresolved=unresolved,
        )
    best: tuple[str, ...] = ()
    memo: dict[str, tuple[str, ...]] = {}
    for node in sorted(edges):
        found = _longest_from(node, edges, memo, contract)
        if len(found) > len(best):
            best = found
    return DepthMeasurement(
        contract_version=contract.version,
        depth=len(best),
        allowed_maximum=allowed_maximum,
        path=best,
        cycles=(),
        unresolved=unresolved if contract.unresolved_is_failure else (),
    )


def _longest_from(
    node: str,
    edges: Mapping[str, set[str]],
    memo: dict[str, tuple[str, ...]],
    contract: MeasurementContract,
) -> tuple[str, ...]:
    if node in memo:
        return memo[node]
    memo[node] = (node,)
    best: tuple[str, ...] = ()
    for nxt in sorted(edges.get(node, ())):
        if contract.ignores_self_edges and nxt == node:
            continue
        found = _longest_from(nxt, edges, memo, contract)
        if len(found) > len(best):
            best = found
    memo[node] = (node, *best)
    return memo[node]


def _find_cycle_paths(edges: Mapping[str, set[str]]) -> tuple[str, ...]:
    white, grey, black = 0, 1, 2
    colour = {node: white for node in edges}
    stack: list[str] = []
    found: list[str] = []

    def visit(node: str) -> None:
        colour[node] = grey
        stack.append(node)
        for nxt in sorted(edges.get(node, ())):
            if nxt == node:
                continue
            if colour.get(nxt, white) == grey:
                found.append(" -> ".join([*stack[stack.index(nxt):], nxt]))
            elif colour.get(nxt, white) == white:
                visit(nxt)
        stack.pop()
        colour[node] = black

    for node in sorted(edges):
        if colour.get(node, white) == white:
            visit(node)
    return tuple(sorted(set(found)))
