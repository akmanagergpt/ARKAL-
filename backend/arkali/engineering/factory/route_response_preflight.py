"""Real, general checks for three route/schema response-shape gaps.

Owner: `engineering.factory`. All three were first found through real
execution — real generated tests, or a real acceptance run, against a
real assembled candidate — never through static analysis alone, since
each requires knowing what a real route handler or a real application
startup actually does, not merely what its source text contains.

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

SCHEMA-CREATION CODE UNREACHABLE FROM THE REAL ROUTES FILE.
`factory-goal-mtpnp9af-yeldck` (real repository evidence, the first real
production Factory candidate to ever reach a real acceptance attempt):
its own real `backend/db.py` correctly created its own real
`overdue_books` table on import, but its own real `backend/app.py` never
imported it — reimplementing its own bare `sqlite3.connect()` instead —
so that schema creation could never actually run when the real
application started. The real, first `pytest` run, in a genuinely fresh
environment, failed outright: `sqlite3.OperationalError: no such table:
overdue_books`. Every prior stage-time check is static/textual and
proves schema creation exists SOMEWHERE under `backend/`, never that
anything real actually reaches it.

GENERAL, NOT GOLDEN-SPECIFIC. All three check for a real pattern — what a
function's body contains, how its variables flow into `jsonify`, or which
real files a real import line actually names — never any specific route
path, table or field name. Any Flask+`sqlite3` backend this pipeline's
own stack produces can trip or satisfy each check identically.
"""

from __future__ import annotations

import ast
import pathlib
import re
from collections.abc import Mapping

from arkali.engineering.factory.semantic_finding import SemanticFinding


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


_IMPORT_LINE = re.compile(r"^\s*(?:import|from)\s")
_SCHEMA_MARKERS = ("create table", "create_all(")
_ROUTE_MARKERS = (
    "@app.route", "@app.get", "@app.post", "@app.put", "@app.delete",
    "@router.", "add_url_rule",
)


def _schema_creating_paths(lowered: Mapping[str, str]) -> set[str]:
    return {path for path, source in lowered.items() if any(m in source for m in _SCHEMA_MARKERS)}


def _route_declaring_paths(lowered: Mapping[str, str]) -> set[str]:
    return {path for path, source in lowered.items() if any(m in source for m in _ROUTE_MARKERS)}


def _module_referenced_on_an_import_line(
    module_stem: str, source_by_path: Mapping[str, str], *, skip_path: str,
) -> bool:
    """Whether any real backend `.py` file OTHER than `skip_path` has a real
    `import`/`from ... import ...` line naming `module_stem` -- covers every
    real Python import shape a candidate's own generated code might use
    (`import backend.db`, `from backend.db import init_db`, `from backend
    import db`, `from . import db`) without needing full import-graph
    resolution: on a real import line, the bare module name always appears
    somewhere in the statement. Deliberately coarse, the same tolerance
    `_matching_methods`/`_module_routes` (`acceptance_plan_compiler.py`)
    already accept for this exact class of check, not full static
    resolution."""
    token = re.compile(rf"\b{re.escape(module_stem)}\b")
    for path, source in source_by_path.items():
        if path == skip_path:
            continue
        for line in source.splitlines():
            if _IMPORT_LINE.match(line) and token.search(line):
                return True
    return False


def _schema_bootstrap_reachability_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Generic, framework-neutral: a file that itself declares real HTTP
    routes is trivially exempt (its own schema creation always runs when
    it does); otherwise the schema file's own module name must appear on a
    real import line in at least one other real backend file."""
    backend_files = {
        path: source for path, source in files.items()
        if path.startswith("backend/") and path.endswith(".py")
    }
    lowered = {path: source.lower() for path, source in backend_files.items()}
    schema_paths = _schema_creating_paths(lowered)
    route_paths = _route_declaring_paths(lowered)
    if not schema_paths or not route_paths:
        return []  # this module's own sibling checks already own "no schema"/"no routes"

    return [
        SemanticFinding(
            code="schema_bootstrap_unreachable", path=schema_path,
            detail=(
                f"{schema_path!r} creates real schema (CREATE TABLE / create_all) but no "
                "other real backend file ever imports it -- this schema-creation code can "
                "never actually run when the real application starts"
            ),
        )
        for schema_path in sorted(schema_paths - route_paths)
        if not _module_referenced_on_an_import_line(
            pathlib.Path(schema_path).stem, backend_files, skip_path=schema_path,
        )
    ]
