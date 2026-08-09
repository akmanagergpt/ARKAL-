"""Gates that analyse the real source tree.

Owner: control.architecture. Sources: AUTHORITY_MAP.yaml (layers, contexts,
allowed_sibling_edges, architecture_budgets) and ARCHITECTURE.md (dependency
direction rules).

These gates parse actual Python imports with `ast`. They never match identifiers
by name, because the canonical map declares an identifier-only checker
insufficient (ARK-REQ-0352).
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any

from arkali.control.architecture.budget_measurement import (
    MEASUREMENT_KEY,
    DepthMeasurement,
    MeasurementContract,
    measure_module,
    measure_orchestration_depth,
)
from arkali.control.architecture.gates.base import ArchitectureGate, GateContext
from arkali.kernel.contracts.results import CheckResult, HonestState

_SRC = "AUTHORITY_MAP.yaml dependency_rules + ARCHITECTURE.md section 4"
PACKAGE_ROOT = "backend/arkali"


def iter_modules(repo_root: pathlib.Path) -> list[pathlib.Path]:
    root = repo_root / PACKAGE_ROOT
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def dotted_name(repo_root: pathlib.Path, path: pathlib.Path) -> str:
    rel = path.relative_to(repo_root / "backend").with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def internal_imports(path: pathlib.Path) -> list[str]:
    """Every arkali module this file imports, in source order."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(a.name for a in node.names if a.name.startswith("arkali."))
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module and node.module.startswith("arkali."):
                found.append(node.module)
    return found


def _find_cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    white, grey, black = 0, 1, 2
    colour = dict.fromkeys(graph, white)
    stack: list[str] = []
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        colour[node] = grey
        stack.append(node)
        for nxt in sorted(graph.get(node, ())):
            if colour.get(nxt, white) == grey:
                cycles.append(stack[stack.index(nxt):] + [nxt])
            elif colour.get(nxt, white) == white:
                visit(nxt)
        stack.pop()
        colour[node] = black

    for node in sorted(graph):
        if colour[node] == white:
            visit(node)
    return cycles


def _context_edges(ctx: GateContext) -> tuple[dict[str, set[str]], int]:
    """Context-to-context edge set derived from real imports."""
    amap = ctx.authority_map
    graph: dict[str, set[str]] = {name: set() for name in amap.contexts}
    edges = 0
    for path in iter_modules(ctx.repo_root):
        owner = amap.context_for_module(dotted_name(ctx.repo_root, path))
        if owner is None:
            continue
        for imported in internal_imports(path):
            target = amap.context_for_module(imported)
            if target and target != owner:
                graph[owner].add(target)
                edges += 1
    return graph, edges


class ForbiddenDependencyDirectionGate(ArchitectureGate):
    """Every import edge must be permitted by the declared `dependency_rules`.

    NO SHADOW MODEL (F-0028). An earlier version implemented layer rank plus
    `allowed_sibling_edges` only, while the map declared two further exceptions
    - `policy_callable_from_any_layer`, `evidence_write_from_any_layer` - that
    `AuthorityMap` did not even parse, so the gate rejected two edge classes
    ARCHITECTURE.md section 4 rules 5 and 6 permit. The decision now belongs to
    `AuthorityMap.edge_permitted`, which reads the declaration.
    """

    gate_id = "forbidden_dependency_direction"
    authoritative_source = _SRC

    def evaluate(self, ctx: GateContext) -> CheckResult:
        amap = ctx.authority_map
        edges = 0
        violations: list[str] = []
        for path in iter_modules(ctx.repo_root):
            owner = amap.context_for_module(dotted_name(ctx.repo_root, path))
            if owner is None:
                continue
            for imported in internal_imports(path):
                target = amap.context_for_module(imported)
                if target is None or target == owner:
                    continue
                edges += 1
                if amap.edge_permitted(owner, target):
                    continue
                violations.append(
                    f"{owner} (rank {amap.rank_of(owner)}) imports "
                    f"{target} (rank {amap.rank_of(target)}) via {imported}"
                )
        if edges == 0 and not violations:
            return self._result(
                HonestState.NOT_APPLICABLE,
                "no cross-context imports exist yet",
                "The rule is implemented and proven by its negative control, but "
                "the tree contains zero cross-context edges, so a PASS would be "
                "vacuous.",
            )
        return self._from_violations(
            violations,
            f"all {edges} cross-context edges respect layer direction",
            "a dependency points at an equal or higher layer",
        )


class ForbiddenCyclesGate(ArchitectureGate):
    """No cycle at context granularity."""

    gate_id = "forbidden_cycles"
    authoritative_source = _SRC

    def evaluate(self, ctx: GateContext) -> CheckResult:
        graph, edges = _context_edges(ctx)
        if edges == 0:
            return self._result(
                HonestState.NOT_APPLICABLE,
                "no cross-context edges exist to form a cycle",
                "Detection is proven by the negative control; a PASS over an "
                "empty edge set would be vacuous.",
            )
        violations = [" -> ".join(cycle) for cycle in _find_cycles(graph)]
        return self._from_violations(
            violations,
            f"context graph over {edges} edges is acyclic",
            "a cycle exists in the context dependency graph",
        )


class ProtectedCoreBoundaryGate(ArchitectureGate):
    """Protected Core membership must be declared and consistently realised."""

    gate_id = "protected_core_boundary_violation"
    authoritative_source = "MASTER_SPECIFICATION Protected Core + AUTHORITY_MAP.yaml"

    MINIMUM = (
        "control.policy",
        "control.isolation",
        "control.architecture",
        "evidence.audit",
        "acceptance.engine",
        "lifecycle.release",
        "lifecycle.recovery",
    )

    def evaluate(self, ctx: GateContext) -> CheckResult:
        amap = ctx.authority_map
        declared = {n for n, c in amap.contexts.items() if c.protected_core}
        violations = [
            f"protected-core minimum member {name!r} is not declared protected"
            for name in self.MINIMUM
            if name not in declared
        ]
        for name in sorted(declared):
            root = ctx.repo_root / amap.contexts[name].module_root
            if not root.is_dir():
                violations.append(
                    f"protected-core context {name!r} has no module root on disk"
                )
        return self._from_violations(
            violations,
            f"{len(declared)} protected-core contexts declared and present",
            "protected-core membership is incomplete or unrealised",
        )


def public_symbols(tree: ast.Module) -> list[str]:
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and not node.name.startswith("_")
    ]


def public_parameter_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Declared parameters, excluding an implicit `self`/`cls` receiver."""
    args = node.args
    total = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
    if args.args and args.args[0].arg in ("self", "cls"):
        total -= 1
    return total


class ArchitectureBudgetGate(ArchitectureGate):
    """Numeric budgets from the authority map, applied to real modules.

    SCOPE IS STATED, NOT IMPLIED. An earlier version evaluated three of the nine
    declared budgets while reporting "all modules respect the numeric
    architecture budgets" - a check whose claim was wider than its field of view,
    the defect family of F-0008, F-0013 and F-0016. The enforced set is now
    declared here, reconciled against the authority map by a permanent test, and
    named in the result detail.

    All nine declared numeric budgets are now evaluated. The last two —
    `max_cyclomatic_complexity_per_function` and `max_orchestration_depth` —
    became enforceable when erratum ERR-003 ratified a measurement contract for
    them, closing F-0020. Their formulas are read from `AUTHORITY_MAP.yaml`
    `architecture_budget_measurement`, never encoded here, so changing the
    contract changes the verdict without editing this gate.
    """

    gate_id = "architecture_budget_violation"
    authoritative_source = (
        "AUTHORITY_MAP.yaml architecture_budgets + "
        "architecture_budget_measurement (ADR-0008, ERR-003)"
    )

    #: Budgets this gate evaluates. Reconciled against the authority map by
    #: tests/governance/test_budget_enforcement_coverage.py.
    ENFORCED = (
        "max_module_logical_lines",
        "max_public_symbols_per_module",
        "max_fan_out_per_module",
        "max_fan_in_per_module",
        "max_contexts_touched_by_module",
        "max_parameters_per_public_function",
        "max_public_surface_per_context",
        "max_cyclomatic_complexity_per_function",
        "max_orchestration_depth",
    )
    #: Every declared budget now has a ratified formula (ERR-003 closed F-0020).
    AWAITING_CANONICAL_FORMULA: tuple[str, ...] = ()

    def evaluate(self, ctx: GateContext) -> CheckResult:
        budgets = ctx.authority_map.architecture_budgets
        contract = MeasurementContract.from_authority_map(
            {MEASUREMENT_KEY: ctx.authority_map.architecture_budget_measurement},
            ctx.authority_map.source_path,
        )
        violations: list[str] = []
        violations.extend(self._per_module(ctx, budgets))
        violations.extend(self._cross_module(ctx, budgets))
        violations.extend(self._complexity(ctx, budgets, contract))
        depth = self.measure_depth(ctx, budgets, contract)
        if not depth.passed:
            violations.append(depth.render())
        detail = (
            f"evaluated={list(self.ENFORCED)} "
            f"measurement_contract={contract.version} "
            f"max_orchestration_depth_path={' -> '.join(depth.path)} "
            f"measured_depth={depth.depth}"
        )
        if violations:
            return self._from_violations(
                violations, "", "an architecture budget is exceeded without an "
                                "approved exception"
            )
        return self._result(
            HonestState.PASS,
            f"all {len(self.ENFORCED)} numeric budgets evaluated; no violation",
            detail,
        )

    @staticmethod
    def _complexity(
        ctx: GateContext, budgets: dict[str, Any], contract: MeasurementContract
    ) -> list[str]:
        """Per-function McCabe complexity under the ratified contract."""
        allowed = int(budgets["max_cyclomatic_complexity_per_function"])
        found: list[str] = []
        for path in iter_modules(ctx.repo_root):
            rel = path.relative_to(ctx.repo_root).as_posix()
            scores = measure_module(
                path.read_text(encoding="utf-8"),
                contract,
                module=rel,
                allowed_maximum=allowed,
            )
            found.extend(score.render() for score in scores if not score.passed)
        return found

    @staticmethod
    def measure_depth(
        ctx: GateContext, budgets: dict[str, Any], contract: MeasurementContract
    ) -> DepthMeasurement:
        """Orchestration depth over the real context graph (ARCHITECTURE.md §8).

        Public so the gate's own evidence and the drift controls read the same
        measurement rather than two implementations of it.
        """
        amap = ctx.authority_map
        allowed = int(budgets["max_orchestration_depth"])
        graph: dict[str, set[str]] = {name: set() for name in amap.contexts}
        unresolved: list[str] = []
        for path in iter_modules(ctx.repo_root):
            owner = amap.context_for_module(dotted_name(ctx.repo_root, path))
            if owner is None:
                continue
            for imported in internal_imports(path):
                target = amap.context_for_module(imported)
                if target is None:
                    unresolved.append(f"{path.name} -> {imported}")
                elif target != owner:
                    graph[owner].add(target)
        return measure_orchestration_depth(
            graph,
            contract,
            allowed_maximum=allowed,
            unresolved=tuple(sorted(set(unresolved))),
        )

    def _per_module(self, ctx: GateContext, budgets: dict[str, Any]) -> list[str]:
        found: list[str] = []
        for path in iter_modules(ctx.repo_root):
            rel = path.relative_to(ctx.repo_root).as_posix()
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            found.extend(self._module_shape(ctx, budgets, path, rel, source, tree))
            found.extend(self._function_shape(budgets, rel, tree))
        return found

    @staticmethod
    def _module_shape(
        ctx: GateContext,
        budgets: dict[str, Any],
        path: pathlib.Path,
        rel: str,
        source: str,
        tree: ast.Module,
    ) -> list[str]:
        """Size, public surface, fan-out and contexts touched, for one module."""
        found = ArchitectureBudgetGate._module_size(budgets, rel, source, tree)
        found.extend(ArchitectureBudgetGate._module_coupling(ctx, budgets, path, rel))
        return found

    @staticmethod
    def _module_size(
        budgets: dict[str, Any], rel: str, source: str, tree: ast.Module
    ) -> list[str]:
        """Logical lines and public symbol count."""
        found: list[str] = []
        max_lines = int(budgets["max_module_logical_lines"])
        logical = [
            line for line in source.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        if len(logical) > max_lines:
            found.append(f"{rel}: {len(logical)} logical lines > {max_lines}")
        max_public = int(budgets["max_public_symbols_per_module"])
        public = public_symbols(tree)
        if len(public) > max_public:
            found.append(f"{rel}: {len(public)} public symbols > {max_public}")
        return found

    @staticmethod
    def _module_coupling(
        ctx: GateContext, budgets: dict[str, Any], path: pathlib.Path, rel: str
    ) -> list[str]:
        """Fan-out and the number of distinct foreign contexts touched."""
        amap = ctx.authority_map
        found: list[str] = []
        imports = internal_imports(path)
        max_fan_out = int(budgets["max_fan_out_per_module"])
        fan_out = len({i.split(".")[1] for i in imports if "." in i})
        if fan_out > max_fan_out:
            found.append(f"{rel}: fan-out {fan_out} > {max_fan_out}")
        max_contexts = int(budgets["max_contexts_touched_by_module"])
        owner = amap.context_for_module(dotted_name(ctx.repo_root, path))
        touched = {amap.context_for_module(i) for i in imports}
        touched.discard(None)
        touched.discard(owner)
        if len(touched) > max_contexts:
            found.append(
                f"{rel}: touches {len(touched)} contexts > {max_contexts} "
                f"({sorted(t for t in touched if t)})"
            )
        return found

    @staticmethod
    def _function_shape(
        budgets: dict[str, Any], rel: str, tree: ast.Module
    ) -> list[str]:
        """Parameter count for every public function and method in one module."""
        max_params = int(budgets["max_parameters_per_public_function"])
        found: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            count = public_parameter_count(node)
            if count > max_params:
                found.append(f"{rel}:{node.name}: {count} parameters > {max_params}")
        return found

    def _cross_module(self, ctx: GateContext, budgets: dict[str, Any]) -> list[str]:
        """Budgets whose subject is a context or a module's inbound edges."""
        amap = ctx.authority_map
        max_fan_in = int(budgets["max_fan_in_per_module"])
        max_surface = int(budgets["max_public_surface_per_context"])
        fan_in: dict[str, int] = {}
        surface: dict[str, int] = {}
        for path in iter_modules(ctx.repo_root):
            for imported in internal_imports(path):
                fan_in[imported] = fan_in.get(imported, 0) + 1
            owner = amap.context_for_module(dotted_name(ctx.repo_root, path))
            if owner is None:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            surface[owner] = surface.get(owner, 0) + len(public_symbols(tree))
        found = [
            f"{module}: fan-in {count} > {max_fan_in}"
            for module, count in fan_in.items()
            if count > max_fan_in
        ]
        found.extend(
            f"context {context}: public surface {count} > {max_surface}"
            for context, count in surface.items()
            if count > max_surface
        )
        return found
