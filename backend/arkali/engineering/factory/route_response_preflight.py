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

RAW SQLITE ROW PASSED TO JSONIFY OR DICT. golden-work-056 (session
evidence, frozen): the same real model's `get_task` handler called
`cursor.fetchone()` and passed that exact tuple straight to `jsonify()`
— a real Flask+`sqlite3` footgun: a bare tuple serializes as a JSON
array, not a keyed object — while its own generated test asserted
`response['id']` and got `TypeError: list indices must be integers or
slices, not str`. golden-work-057 (session evidence, frozen) then wrapped
the same raw rows in `dict(row)` — a real ecosystem-verified fix for the
FIRST gap — but never set `conn.row_factory = sqlite3.Row`, so `dict()`
on a plain tuple itself raises a real `TypeError`, and every route
handling one returned HTTP 500. `dict(...)` alone does not prove
correctness; only `row_factory` does.

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


_FETCH_METHODS = ("fetchone", "fetchall")
_UNSAFE_WRAPPERS = ("jsonify", "dict")


def _cursor_result_name(node: ast.AST) -> str | None:
    is_fetch = (
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr in _FETCH_METHODS
    )
    if not is_fetch:
        return None
    names = [t.id for t in node.targets if isinstance(t, ast.Name)]  # type: ignore[union-attr]
    return names[0] if names else None


def _loop_target_over_name(node: ast.AST, source_names: set[str]) -> str | None:
    """A comprehension or for-loop variable iterating directly over a
    known raw cursor-result name (e.g. `for row in tasks` where
    `tasks = cursor.fetchall()`) — the loop variable is just as raw."""
    target = getattr(node, "target", None)
    iterable = getattr(node, "iter", None)
    is_direct_loop = (
        isinstance(node, (ast.comprehension, ast.For))
        and isinstance(target, ast.Name)
        and isinstance(iterable, ast.Name)
        and iterable.id in source_names
    )
    return target.id if is_direct_loop else None  # type: ignore[union-attr]


def _bare_call_argument(node: ast.AST) -> str | None:
    is_bare_call = (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _UNSAFE_WRAPPERS
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Name)
    )
    return node.args[0].id if is_bare_call else None  # type: ignore[union-attr]


def _raw_cursor_result_names(node: ast.AST) -> set[str]:
    direct = {n for n in (_cursor_result_name(inner) for inner in ast.walk(node)) if n}
    looped = {
        n for n in (_loop_target_over_name(inner, direct) for inner in ast.walk(node)) if n
    }
    return direct | looped


def _names_reaching_an_unsafe_conversion(node: ast.AST) -> list[str]:
    raw_names = _raw_cursor_result_names(node)
    reached = {
        n for n in (_bare_call_argument(inner) for inner in ast.walk(node))
        if n and n in raw_names
    }
    return sorted(reached)


def _raw_row_jsonify_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    backend_text = "\n".join(
        source for path, source in files.items()
        if path.startswith("backend/") and path.endswith(".py")
    )
    if "row_factory" in backend_text:
        return []
    findings: list[SemanticFinding] = []
    for path, source, node in _backend_python_functions(files):
        reached = _names_reaching_an_unsafe_conversion(node)
        if not reached:
            continue
        findings.append(SemanticFinding(
            code="raw_sqlite_row_passed_to_jsonify", path=path,
            detail=(
                f"function {node.name!r} passes cursor.fetchone()/fetchall()'s "
                f"raw tuple(s) (as {reached[0]!r}) into dict() or jsonify() "
                "without ever setting conn.row_factory = sqlite3.Row — dict() "
                "on a plain tuple raises TypeError, and jsonify() on a bare "
                "tuple serializes as an array, not a keyed object; set "
                "conn.row_factory = sqlite3.Row right after connecting, before "
                "creating the cursor"
            ),
        ))
    return findings
