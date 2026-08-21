"""Real, general checks for two route response-shape gaps.

Owner: `engineering.factory`. Both were first found through real
execution — real generated tests running against a real assembled
candidate — never through static analysis alone, since both require
knowing what a route handler's real runtime behavior produces.

MISSING GENERATED ID. golden-work-052 and golden-work-053 (session
evidence, frozen, byte-identical across two separate real
`qwen2.5-coder:14b` runs): the same real model's `create_task` handler
executed a SQL `INSERT` and returned `jsonify(data), 201` — the client's
own submitted request body, verbatim, never the row id SQLite actually
assigned — while that same model's own generated test asserted the
response includes `'id'`.

RAW SQLITE ROW PASSED TO JSONIFY. golden-work-056 (session evidence,
frozen): the same real model's `get_task` handler called
`cursor.fetchone()` and passed that exact tuple straight to `jsonify()`
— a real Flask+`sqlite3` footgun: a bare tuple serializes as a JSON
array, not a keyed object — while its own generated test asserted
`response['id']` and got `TypeError: list indices must be integers or
slices, not str`.

GENERAL, NOT GOLDEN-SPECIFIC. Both check for the pattern — what a
function's body contains and how its variables flow into `jsonify` —
never any specific route path, table or field name. Any Flask+`sqlite3`
backend this pipeline's own stack always produces can trip or satisfy
either check identically.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding


def _backend_python_functions(files: Mapping[str, str]):
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".py")):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield path, source, node


def _missing_generated_id_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for path, source, node in _backend_python_functions(files):
        segment = (ast.get_source_segment(source, node) or "").lower()
        if "insert into" not in segment or "jsonify" not in segment:
            continue
        if "lastrowid" in segment:
            continue
        findings.append(SemanticFinding(
            code="missing_generated_id_in_create_response", path=path,
            detail=(
                f"function {node.name!r} executes a SQL INSERT and returns "
                "JSON but never references cursor.lastrowid — add the row's "
                "own generated id (e.g. cursor.lastrowid) to the response "
                "instead of only the submitted request body"
            ),
        ))
    return findings


def _fetchone_assignment_target(node: ast.AST) -> str | None:
    is_fetchone = (
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "fetchone"
    )
    if not is_fetchone:
        return None
    names = [t.id for t in node.targets if isinstance(t, ast.Name)]  # type: ignore[union-attr]
    return names[0] if names else None


def _bare_jsonify_argument(node: ast.AST) -> str | None:
    is_bare_call = (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "jsonify"
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
    )
    return node.args[0].id if is_bare_call else None  # type: ignore[union-attr]


def _fetchone_names_reaching_jsonify(node: ast.AST) -> list[str]:
    fetchone_targets: set[str] = set()
    jsonify_names: set[str] = set()
    for inner in ast.walk(node):
        target = _fetchone_assignment_target(inner)
        if target is not None:
            fetchone_targets.add(target)
        argument = _bare_jsonify_argument(inner)
        if argument is not None:
            jsonify_names.add(argument)
    return sorted(fetchone_targets & jsonify_names)


def _raw_row_jsonify_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for path, source, node in _backend_python_functions(files):
        overlap = _fetchone_names_reaching_jsonify(node)
        if not overlap:
            continue
        segment = (ast.get_source_segment(source, node) or "").lower()
        if "row_factory" in segment or "dict(" in segment:
            continue
        findings.append(SemanticFinding(
            code="raw_sqlite_row_passed_to_jsonify", path=path,
            detail=(
                f"function {node.name!r} passes cursor.fetchone()'s raw tuple "
                f"directly to jsonify({overlap[0]!r}) — it serializes as a JSON "
                "array, not an object with named fields; set conn.row_factory = "
                "sqlite3.Row and convert with dict(row) before returning"
            ),
        ))
    return findings
