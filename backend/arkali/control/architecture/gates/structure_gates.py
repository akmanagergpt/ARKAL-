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

from arkali.control.architecture.gates.base import ArchitectureGate, GateContext
from arkali.kernel.contracts.results import CheckResult, HonestState

_SRC = "AUTHORITY_MAP.yaml + ARCHITECTURE.md dependency direction rules"
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
    """A context may depend only on strictly lower layers, plus declared siblings."""

    gate_id = "forbidden_dependency_direction"
    authoritative_source = _SRC

    def evaluate(self, ctx: GateContext) -> CheckResult:
        amap = ctx.authority_map
        siblings = {(e.source, e.target) for e in amap.sibling_edges}
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
                if amap.rank_of(target) < amap.rank_of(owner):
                    continue
                if (owner, target) in siblings:
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


class ArchitectureBudgetGate(ArchitectureGate):
    """Numeric budgets from the authority map, applied to real modules."""

    gate_id = "architecture_budget_violation"
    authoritative_source = "AUTHORITY_MAP.yaml architecture_budgets (ADR-0008)"

    def evaluate(self, ctx: GateContext) -> CheckResult:
        budgets = ctx.authority_map.architecture_budgets
        max_lines = int(budgets["max_module_logical_lines"])
        max_public = int(budgets["max_public_symbols_per_module"])
        max_fan_out = int(budgets["max_fan_out_per_module"])
        violations: list[str] = []
        for path in iter_modules(ctx.repo_root):
            rel = path.relative_to(ctx.repo_root).as_posix()
            source = path.read_text(encoding="utf-8")
            logical = [
                line
                for line in source.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
            if len(logical) > max_lines:
                violations.append(f"{rel}: {len(logical)} logical lines > {max_lines}")
            tree = ast.parse(source, filename=str(path))
            public = [
                node.name
                for node in tree.body
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                )
                and not node.name.startswith("_")
            ]
            if len(public) > max_public:
                violations.append(f"{rel}: {len(public)} public symbols > {max_public}")
            fan_out = len({i.split(".")[1] for i in internal_imports(path) if "." in i})
            if fan_out > max_fan_out:
                violations.append(f"{rel}: fan-out {fan_out} > {max_fan_out}")
        return self._from_violations(
            violations,
            "all modules respect the numeric architecture budgets",
            "an architecture budget is exceeded without an approved exception",
        )
