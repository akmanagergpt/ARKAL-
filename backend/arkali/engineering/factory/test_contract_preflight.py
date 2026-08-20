"""Generated-test fixture contract checks owned by ``engineering.factory``."""

from __future__ import annotations

import ast

from arkali.engineering.factory.product_preflight import SemanticFinding


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


def _is_fixture(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "fixture"


def _is_test(node: ast.stmt) -> bool:
    return isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
        "test"
    )


__all__ = ["fixture_findings"]
