"""Generated-test fixture contract checks owned by ``engineering.factory``."""

from __future__ import annotations

import ast
import builtins
import sys
from collections.abc import Mapping

from arkali.engineering.factory.semantic_finding import SemanticFinding

_BUILTIN_NAMES = frozenset(dir(builtins))


def fixture_findings(path: str, tree: ast.Module) -> list[SemanticFinding]:
    fixtures = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(_is_fixture(decorator) for decorator in node.decorator_list)
    }
    allowed = fixtures | {"tmp_path", "tmpdir", "monkeypatch", "capsys", "capfd"}
    findings: list[SemanticFinding] = []
    for node in tree.body:
        if not _is_test(node):
            continue
        missing = sorted(
            argument.arg
            for argument in node.args.args
            if argument.arg not in allowed | {"self", "cls"}
        )
        if missing:
            findings.append(
                SemanticFinding(
                    code="undefined_test_fixture",
                    path=path,
                    detail=f"test references undeclared fixtures {missing!r}",
                )
            )
    return findings


def plain_import_findings(
    path: str,
    tree: ast.AST,
    modules: Mapping[str, object],
    dependencies: frozenset[str],
) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for node in (item for item in ast.walk(tree) if isinstance(item, ast.Import)):
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            # golden-work-068 (session evidence, frozen): `import backend.db`
            # (`alias.name` == "backend.db") was flagged as an undeclared
            # dependency on the bare package root "backend" -- real,
            # resolvable local package import, wrongly rejected, because
            # only `root` (the first dotted segment) was ever checked
            # against `modules`, never the full dotted name a real local
            # sub-module actually registers under (`_module_aliases`
            # already keys `modules` by both "db" and "backend.db").
            if (
                root in sys.stdlib_module_names
                or root.lower() in dependencies
                or root in modules
                or alias.name in modules
            ):
                continue
            findings.append(
                SemanticFinding(
                    code="undeclared_test_dependency",
                    path=path,
                    detail=f"{path} imports undeclared dependency {root!r}",
                )
            )
    return findings


def lifecycle_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    backend = "\n".join(
        source
        for path, source in files.items()
        if path.startswith("backend/") and path.endswith(".py")
    )
    tests = "\n".join(
        source
        for path, source in files.items()
        if path.startswith("tests/") and path.endswith(".py")
    )
    has_startup_schema = "on_event(" in backend and "create table" in backend.lower()
    global_client = "client = TestClient(app)" in tests
    context_client = "with TestClient(app)" in tests
    if has_startup_schema and global_client and not context_client:
        return [
            SemanticFinding(
                code="test_skips_application_lifecycle",
                path="tests/",
                detail="TestClient must enter a context when schema bootstrap runs at startup",
            )
        ]
    return []


def _function_parameter_names(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> set[str]:
    names = {a.arg for a in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)}
    if node.args.vararg:
        names.add(node.args.vararg.arg)
    if node.args.kwarg:
        names.add(node.args.kwarg.arg)
    return names


def _import_bound_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {(alias.asname or alias.name).split(".")[0] for alias in node.names}
    if isinstance(node, ast.ImportFrom):
        return {alias.asname or alias.name for alias in node.names if alias.name != "*"}
    return set()


def _binding_target_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
        return {node.id}
    if isinstance(node, ast.ExceptHandler) and node.name:
        return {node.name}
    if isinstance(node, (ast.Global, ast.Nonlocal)):
        return set(node.names)
    return set()


def _bound_names(tree: ast.AST) -> set[str]:
    """Every name bound anywhere in the file — imports, defs, assignments,
    parameters, for/with/comprehension/walrus targets, except-as aliases —
    collected without regard to scope.

    DELIBERATELY OVER-INCLUSIVE. Python's own AST already represents every
    assignment/for/with/comprehension/walrus binding as an `ast.Name` node
    in `Store` context, so a single pass over those plus def/class names,
    function parameters, import aliases and except-handler names covers
    real binding forms without hand-listing each statement kind. The goal
    is never to flag a name genuinely bound somewhere in the file, only
    one bound nowhere at all — a real false negative here (missing an
    actually-undefined name because it happens to share a spelling with
    something bound in an unrelated scope) is the safe failure direction;
    a false positive is not.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            names |= _function_parameter_names(node)
        names |= _import_bound_names(node)
        names |= _binding_target_names(node)
    return names


def _undefined_call_findings(path: str, tree: ast.AST) -> list[SemanticFinding]:
    """A bare-name call (`foo()`, never `obj.foo()`) whose name is neither
    imported, defined, assigned nor a builtin anywhere in the file.

    golden-work-071 (session evidence, frozen): `tests/test_app.py` wrote
    `from backend.app import app, get_db_connection` and then called
    `init_db()` in `setUp()` — a real function, genuinely defined in
    `backend/db.py`, but never imported by this file under any name.
    `ast.parse` is blind to this (calling an undefined name is not a
    syntax error); real `pytest` collection failed all 8 tests outright
    with `NameError: name 'init_db' is not defined`, the first thing any
    of them did.
    """
    bound = _bound_names(tree) | _BUILTIN_NAMES
    findings: list[SemanticFinding] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        name = node.func.id
        if name in bound or name in seen:
            continue
        seen.add(name)
        findings.append(SemanticFinding(
            code="undefined_name_called", path=path,
            detail=f"{path} calls {name!r}, which is never imported, defined or "
                   "assigned anywhere in this file",
        ))
    return findings


def _is_fixture(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "fixture"


def _is_test(node: ast.stmt) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
        "test"
    )


__all__ = [
    "fixture_findings", "lifecycle_findings", "plain_import_findings", "_undefined_call_findings",
]
