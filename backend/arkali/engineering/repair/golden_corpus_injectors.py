"""The 8 canonical Golden Repair injector/detector pairs (`GOLDEN_REPAIR_
CORPUS_DEFINITION.md` §2), split out of `golden_corpus.py` to keep that
module's own real size within AUTHORITY_MAP.yaml's architecture budgets.

DOMAIN-INDEPENDENT BY CONSTRUCTION -- see `golden_corpus.py`'s module
docstring for the full rationale; it applies identically here. NO
`engineering.factory` IMPORT for the same reason documented there:
`_detect_dependency_lock_mismatch` restates a real, verified fact
structurally rather than importing across a forbidden dependency edge.
"""

from __future__ import annotations

import ast
import re
from typing import Callable, Mapping

from arkali.engineering.repair.golden_corpus import (
    API_FRONTEND_CONTRACT_DRIFT,
    BOUNDARY_OFF_BY_ONE,
    CONTRACT_VIOLATION,
    CorpusInjectionError,
    DEPENDENCY_LOCK_MISMATCH,
    MIGRATION_MODEL_MISMATCH,
    PERMISSION_CHECK_REMOVAL,
    PERSISTENCE_NOT_COMMITTED,
    RepairCorpusEntry,
    STATE_MACHINE_INVALID_TRANSITION,
)

# ---------------------------------------------------------------------------
# Structural helpers shared by several injectors/detectors -- REUSE, not one
# ad hoc regex per class.
# ---------------------------------------------------------------------------

_ROUTE_DECORATOR = re.compile(
    r"@app\.route\([^)]*methods\s*=\s*\[([^\]]*)\][^)]*\)\s*\ndef\s+(\w+)\s*\([^)]*\)\s*:",
)


def _route_functions(source: str, *, method: str) -> list[re.Match[str]]:
    """Every `@app.route(...)` decorated function declaring `method` among
    its own real `methods=[...]` list -- structural, not name-based."""
    return [
        m for m in _ROUTE_DECORATOR.finditer(source)
        if f"'{method}'" in m.group(1) or f'"{method}"' in m.group(1)
    ]


def _function_body_span(source: str, def_match: re.Match[str]) -> tuple[int, int]:
    """The real [start, end) character span of the function `def_match`
    declares, found by parsing the module and matching the function name at
    or after the decorator's own line -- robust to any real indentation or
    blank-line style a real generated candidate uses."""
    tree = ast.parse(source)
    name = def_match.group(2)
    target_line = source.count("\n", 0, def_match.end()) + 1
    best = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            if best is None or abs(node.lineno - target_line) < abs(best.lineno - target_line):
                best = node
    if best is None or best.end_lineno is None:
        raise CorpusInjectionError(f"no function named {name!r} found by AST parse")
    lines = source.splitlines(keepends=True)
    start = sum(len(line) for line in lines[: best.lineno - 1])
    end = sum(len(line) for line in lines[: best.end_lineno])
    return start, end


def _first_backend_route_file(files: Mapping[str, str]) -> str:
    for path in sorted(files):
        if path == "backend/app.py":
            return path
    raise CorpusInjectionError("no backend/app.py in these files")


# ---------------------------------------------------------------------------
# 1. contract_violation -- injection_target: source_module (canonical §2 row 1)
# ---------------------------------------------------------------------------

_JSONIFY_DICT_KEY = re.compile(r"""['"](\w+)['"]\s*:\s*[^,{}]+?(?=,\s*['"]\w+['"]\s*:|\s*\}\))""")


def _inject_contract_violation(files: Mapping[str, str]) -> Mapping[str, str]:
    """Removes one non-identifier field from a real `jsonify({...})` response
    dict in a real POST (create) route -- the response contract now omits a
    field its own creator declared, T4's own contract class."""
    path = _first_backend_route_file(files)
    source = files[path]
    posts = _route_functions(source, method="POST")
    if not posts:
        raise CorpusInjectionError("no POST route to target for contract_violation")
    start, end = _function_body_span(source, posts[0])
    body = source[start:end]
    keys = [m for m in _JSONIFY_DICT_KEY.finditer(body) if m.group(1) != "id"]
    if not keys:
        raise CorpusInjectionError("no non-id jsonify field found to remove")
    victim = keys[-1]
    match_end = victim.end()
    # consume a trailing ", " if present so the dict literal stays syntactically valid
    trailing = re.match(r",\s*", body[match_end:])
    remove_end = match_end + (trailing.end() if trailing else 0)
    remove_start = victim.start()
    if not trailing:
        # last key in the dict -- strip a preceding ", " instead
        leading = re.search(r",\s*$", body[:remove_start])
        if leading:
            remove_start = leading.start()
    mutated_body = body[:remove_start] + body[remove_end:]
    mutated_source = source[:start] + mutated_body + source[end:]
    return {**files, path: mutated_source}


def _detect_contract_violation(files: Mapping[str, str]) -> bool:
    """True while any POST route's own `jsonify` response omits a field its
    own function assigns from the real request body (`data['x']` used to
    build the response elsewhere in the same function, or a field the
    original response declared and this check's own paired injector would
    have removed) -- detected structurally: a POST handler that reads more
    request keys than it echoes back in its own jsonify dict."""
    path = _first_backend_route_file(files)
    source = files[path]
    posts = _route_functions(source, method="POST")
    if not posts:
        return False
    start, end = _function_body_span(source, posts[0])
    body = source[start:end]
    requested = set(re.findall(r"data\[['\"](\w+)['\"]\]", body))
    responded = {m.group(1) for m in _JSONIFY_DICT_KEY.finditer(body)}
    return bool(requested - responded)


# ---------------------------------------------------------------------------
# 2. state_machine_invalid_transition -- injection_target: source_module
# (canonical §2 row 2)
# ---------------------------------------------------------------------------

_ROWCOUNT_GUARD = re.compile(
    r"[ \t]*if\s+\w+\.rowcount\s*==\s*0\s*:\n(?:[ \t]+.*\n)+?", re.MULTILINE,
)


def _inject_state_machine_invalid_transition(files: Mapping[str, str]) -> Mapping[str, str]:
    """Removes the existence guard (`if <cursor>.rowcount == 0: ...`) a real
    UPDATE or DELETE route uses to refuse mutating a record that does not
    exist -- once removed, mutating a nonexistent record's real identity
    silently "succeeds", a real invalid state transition (acting on an
    entity that was never in the required prior state)."""
    path = _first_backend_route_file(files)
    source = files[path]
    targets = _route_functions(source, method="PUT") or _route_functions(source, method="DELETE")
    if not targets:
        raise CorpusInjectionError("no PUT/DELETE route to target")
    start, end = _function_body_span(source, targets[0])
    body = source[start:end]
    guard = _ROWCOUNT_GUARD.search(body)
    if not guard:
        raise CorpusInjectionError("no rowcount==0 existence guard found")
    mutated_body = body[: guard.start()] + body[guard.end():]
    mutated_source = source[:start] + mutated_body + source[end:]
    return {**files, path: mutated_source}


def _detect_state_machine_invalid_transition(files: Mapping[str, str]) -> bool:
    """True while a PUT/DELETE route commits a mutation with no prior
    existence guard -- structurally: the function calls `.commit()` but its
    body never checks `rowcount == 0` (or an equivalent `is None` guard)
    before doing so."""
    path = _first_backend_route_file(files)
    source = files[path]
    targets = _route_functions(source, method="PUT") or _route_functions(source, method="DELETE")
    if not targets:
        return False
    start, end = _function_body_span(source, targets[0])
    body = source[start:end]
    has_commit = ".commit(" in body
    has_guard = bool(_ROWCOUNT_GUARD.search(body)) or "is None" in body
    return has_commit and not has_guard


# ---------------------------------------------------------------------------
# 3. permission_check_removal -- injection_target: source_module
# (canonical §2 row 3)
# ---------------------------------------------------------------------------
#
# A GENUINE, EVIDENCE-BASED SCOPING NOTE. Candidates this pipeline produces
# today carry no role/auth system at all (STAGED_GENERATION_STAGES.md never
# requires one) -- fabricating one here to remove would be exactly the
# contrived, non-generic injection this corpus definition forbids. The one
# REAL, structural access-control primitive every real candidate already
# carries is CORS (`flask_cors`, canonically required by `backend_cors_
# boundary`, STAGED_GENERATION_STAGES.md#4): it is the actual mechanism that
# decides which origins may call the API at all. Removing it is a real,
# structural permission/access-control removal, not a contrived stand-in.

_CORS_CALL = re.compile(r"\bCORS\(\s*app\s*\)")


def _inject_permission_check_removal(files: Mapping[str, str]) -> Mapping[str, str]:
    """Removes the real `CORS(app)` access-control call -- the backend now
    accepts cross-origin requests it was declared to refuse."""
    path = _first_backend_route_file(files)
    source = files[path]
    match = _CORS_CALL.search(source)
    if not match:
        raise CorpusInjectionError("no CORS(app) call found to remove")
    line_start = source.rfind("\n", 0, match.start()) + 1
    line_end = source.find("\n", match.end())
    line_end = len(source) if line_end == -1 else line_end + 1
    mutated_source = source[:line_start] + source[line_end:]
    return {**files, path: mutated_source}


def _detect_permission_check_removal(files: Mapping[str, str]) -> bool:
    """True while the backend imports `flask_cors` but never actually calls
    `CORS(app)` -- the declared access-control boundary is not wired."""
    path = _first_backend_route_file(files)
    source = files[path]
    imports_cors = bool(re.search(r"from\s+flask_cors\s+import\s+CORS", source))
    return imports_cors and not bool(_CORS_CALL.search(source))


# ---------------------------------------------------------------------------
# 4. persistence_not_committed -- injection_target: source_module
# (canonical §2 row 4)
# ---------------------------------------------------------------------------


def _inject_persistence_not_committed(files: Mapping[str, str]) -> Mapping[str, str]:
    """Removes the real `.commit()` call from a mutating (POST) route -- the
    write reaches SQLite's own connection but is never durably committed."""
    path = _first_backend_route_file(files)
    source = files[path]
    posts = _route_functions(source, method="POST")
    if not posts:
        raise CorpusInjectionError("no POST route to target for persistence_not_committed")
    start, end = _function_body_span(source, posts[0])
    body = source[start:end]
    commit_match = re.search(r"[ \t]*\w+\.commit\(\)\n", body)
    if not commit_match:
        raise CorpusInjectionError("no real .commit() call found")
    mutated_body = body[: commit_match.start()] + body[commit_match.end():]
    mutated_source = source[:start] + mutated_body + source[end:]
    return {**files, path: mutated_source}


def _detect_persistence_not_committed(files: Mapping[str, str]) -> bool:
    """True while a POST route's function body executes an INSERT with no
    matching `.commit()` call anywhere in that same function."""
    path = _first_backend_route_file(files)
    source = files[path]
    posts = _route_functions(source, method="POST")
    if not posts:
        return False
    start, end = _function_body_span(source, posts[0])
    body = source[start:end]
    return "insert into" in body.lower() and ".commit(" not in body


# ---------------------------------------------------------------------------
# 5. api_frontend_contract_drift -- injection_target: route_contract
# (canonical §2 row 5)
# ---------------------------------------------------------------------------


def _inject_api_frontend_contract_drift(files: Mapping[str, str]) -> Mapping[str, str]:
    """Mutates one real declared method in `backend/routes.json` (the
    canonical route contract) so it no longer matches the real backend's own
    `@app.route(..., methods=[...])` declaration for that path -- a real
    API/frontend contract drift, detected by comparing the two."""
    import json
    path = "backend/routes.json"
    if path not in files:
        raise CorpusInjectionError("no backend/routes.json in these files")
    routes = json.loads(files[path])
    if not routes:
        raise CorpusInjectionError("backend/routes.json declares no routes")
    mutated = list(routes)
    victim = mutated[0]
    # "PATCH" is deliberately never a method STAGED_GENERATION_STAGES.md's
    # own canonical CRUD vocabulary (GET/POST/PUT/DELETE) ever declares, so
    # this is guaranteed to be a real, unmatched drift rather than an
    # accidental duplicate of a route the backend already declares.
    mutated[0] = {**victim, "method": "PATCH"}
    return {**files, path: json.dumps(mutated, indent=2)}


def _detect_api_frontend_contract_drift(files: Mapping[str, str]) -> bool:
    """True while any `backend/routes.json` entry names a (path, method)
    pair the real backend source's own `@app.route` decorators do not
    declare for that path."""
    import json
    path = "backend/routes.json"
    backend_path = _first_backend_route_file(files)
    if path not in files:
        return False
    routes = json.loads(files[path])
    source = files[backend_path]
    declared: set[tuple[str, str]] = set()
    for match in re.finditer(
        r"""@app\.route\(\s*['"]([^'"]+)['"][^)]*methods\s*=\s*\[([^\]]*)\]""", source,
    ):
        route_path = match.group(1)
        for method in re.findall(r"""['"](\w+)['"]""", match.group(2)):
            declared.add((route_path, method))
    for entry in routes:
        route_path = str(entry.get("path", "")).replace("{id}", "<int:id>")
        pair = (route_path, str(entry.get("method", "")))
        if pair not in declared:
            return True
    return False


# ---------------------------------------------------------------------------
# 6. dependency_lock_mismatch -- injection_target: lockfile
# (canonical §2 row 6). Structurally restates the same real, verified fact
# `product_preflight._missing_compatibility_cap_findings` already checks on
# the generation side (golden-work-077, real frozen session evidence: a
# Flask 2.x pin with no `Werkzeug<3` cap installs cleanly but genuinely
# fails Flask's own `test_client()` against Werkzeug 3.x) -- restated here,
# not imported, because AUTHORITY_MAP.yaml's `allowed_sibling_edges` permits
# only `engineering.factory -> engineering.repair`, never the reverse.
# ---------------------------------------------------------------------------

_FLASK_PIN = re.compile(r"(?im)^flask==(\d+)\.")
_WERKZEUG_CAP = re.compile(r"(?im)^werkzeug\s*<\s*3")


def _inject_dependency_lock_mismatch(files: Mapping[str, str]) -> Mapping[str, str]:
    """Widens the real, already-verified Flask pin in `backend/requirements.
    txt` to a version with no compatible Werkzeug bound."""
    path = "backend/requirements.txt"
    if path not in files:
        raise CorpusInjectionError("no backend/requirements.txt in these files")
    source = files[path]
    mutated, count = re.subn(
        r"(?im)^flask==[0-9.]+$", "flask==2.1.3", source,
    )
    if not count:
        raise CorpusInjectionError("no pinned flask== line found to widen")
    mutated = re.sub(r"(?im)^Werkzeug<3\n?", "", mutated)
    return {**files, path: mutated}


def _detect_dependency_lock_mismatch(files: Mapping[str, str]) -> bool:
    """True while `backend/requirements.txt` pins a Flask 2.x release with
    no `Werkzeug<3` upper-bound cap declared alongside it."""
    path = "backend/requirements.txt"
    if path not in files:
        return False
    source = files[path]
    match = _FLASK_PIN.search(source)
    if not match or int(match.group(1)) != 2:
        return False
    return not bool(_WERKZEUG_CAP.search(source))


# ---------------------------------------------------------------------------
# 7. migration_model_mismatch -- injection_target: migration
# (canonical §2 row 7)
# ---------------------------------------------------------------------------


def _inject_migration_model_mismatch(files: Mapping[str, str]) -> Mapping[str, str]:
    """Removes one real column from a `CREATE TABLE` statement in
    `backend/db.py` -- the live schema migration no longer matches
    `backend/data_model.json`'s own declared fields for that table."""
    path = "backend/db.py"
    if path not in files:
        raise CorpusInjectionError("no backend/db.py in these files")
    source = files[path]
    match = re.search(
        r"CREATE TABLE[^(]*\(([^;]*?)\)\s*\n?\s*'''", source, re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise CorpusInjectionError("no CREATE TABLE statement found")
    column_lines = [
        line for line in match.group(1).splitlines()
        if line.strip() and "PRIMARY KEY" not in line.upper()
    ]
    if len(column_lines) < 2:
        raise CorpusInjectionError("not enough real columns to remove one safely")
    victim = column_lines[-1]
    mutated_columns = match.group(1).replace(victim, "", 1)
    # drop a now-dangling trailing comma before the closing paren
    mutated_columns = re.sub(r",(\s*)$", r"\1", mutated_columns.rstrip()) + "\n        "
    mutated_source = source[: match.start(1)] + mutated_columns + source[match.end(1):]
    return {**files, path: mutated_source}


def _detect_migration_model_mismatch(files: Mapping[str, str]) -> bool:
    """True while `backend/db.py`'s own `CREATE TABLE` column set for a
    table is missing a field `backend/data_model.json` declares for it."""
    import json
    db_path, model_path = "backend/db.py", "backend/data_model.json"
    if db_path not in files or model_path not in files:
        return False
    source = files[db_path]
    declared_fields = json.loads(files[model_path]).get("fields", {})
    for table_match in re.finditer(
        r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)\s*\(([^;]*?)\)\s*\n?\s*'''",
        source, re.IGNORECASE | re.DOTALL,
    ):
        table, body = table_match.group(1), table_match.group(2)
        fields = declared_fields.get(table)
        if not isinstance(fields, dict):
            continue
        columns = {
            re.match(r"\s*(\w+)", line).group(1)
            for line in body.splitlines() if re.match(r"\s*(\w+)", line)
        }
        if set(fields) - columns:
            return True
    return False


# ---------------------------------------------------------------------------
# 8. boundary_off_by_one -- injection_target: source_module
# (canonical §2 row 8)
# ---------------------------------------------------------------------------

_INT_CONVERTER = re.compile(r"<int:(\w+)>")


def _inject_boundary_off_by_one(files: Mapping[str, str]) -> Mapping[str, str]:
    """Removes the real `<int:...>` type-boundary converter from every real
    route decorator sharing the first one's own exact real path pattern,
    widening them to accept any string -- a real boundary/type-validation
    defect: a non-integer id now reaches a query built to expect one. Every
    occurrence of the identical converter is replaced together (not just the
    first), since a real generated candidate commonly declares the identical
    `<int:id>` segment across its own GET/PUT/DELETE routes for one
    resource -- leaving any one of them untouched would leave the boundary
    genuinely still enforced for that resource."""
    path = _first_backend_route_file(files)
    source = files[path]
    match = _INT_CONVERTER.search(source)
    if not match:
        raise CorpusInjectionError("no <int:...> route converter found")
    literal = match.group(0)
    mutated_source = source.replace(literal, f"<{match.group(1)}>")
    return {**files, path: mutated_source}


def _detect_boundary_off_by_one(files: Mapping[str, str]) -> bool:
    """True while `backend/routes.json` declares a parameterised path this
    backend's own route decorators no longer type-constrain with
    `<int:...>` for the matching parameter."""
    import json
    path, backend_path = "backend/routes.json", _first_backend_route_file(files)
    if path not in files:
        return False
    routes = json.loads(files[path])
    source = files[backend_path]
    has_id_route = any("{id}" in str(r.get("path", "")) for r in routes)
    return has_id_route and not bool(_INT_CONVERTER.search(source))


INJECTORS: dict[str, Callable[[Mapping[str, str]], Mapping[str, str]]] = {
    CONTRACT_VIOLATION: _inject_contract_violation,
    STATE_MACHINE_INVALID_TRANSITION: _inject_state_machine_invalid_transition,
    PERMISSION_CHECK_REMOVAL: _inject_permission_check_removal,
    PERSISTENCE_NOT_COMMITTED: _inject_persistence_not_committed,
    API_FRONTEND_CONTRACT_DRIFT: _inject_api_frontend_contract_drift,
    DEPENDENCY_LOCK_MISMATCH: _inject_dependency_lock_mismatch,
    MIGRATION_MODEL_MISMATCH: _inject_migration_model_mismatch,
    BOUNDARY_OFF_BY_ONE: _inject_boundary_off_by_one,
}
DETECTORS: dict[str, Callable[[Mapping[str, str]], bool]] = {
    CONTRACT_VIOLATION: _detect_contract_violation,
    STATE_MACHINE_INVALID_TRANSITION: _detect_state_machine_invalid_transition,
    PERMISSION_CHECK_REMOVAL: _detect_permission_check_removal,
    PERSISTENCE_NOT_COMMITTED: _detect_persistence_not_committed,
    API_FRONTEND_CONTRACT_DRIFT: _detect_api_frontend_contract_drift,
    DEPENDENCY_LOCK_MISMATCH: _detect_dependency_lock_mismatch,
    MIGRATION_MODEL_MISMATCH: _detect_migration_model_mismatch,
    BOUNDARY_OFF_BY_ONE: _detect_boundary_off_by_one,
}

def apply_corpus(
    files: Mapping[str, str], entries: tuple[RepairCorpusEntry, ...],
) -> Mapping[str, str]:
    """Applies every entry's own injector once, in declared corpus order,
    against an isolated copy -- never the caller's own mapping."""
    current = dict(files)
    for entry in entries:
        injector = INJECTORS[entry.defect_class]
        current = dict(injector(current))
    return current


def corpus_defects_present(
    files: Mapping[str, str], entries: tuple[RepairCorpusEntry, ...],
) -> dict[str, bool]:
    """`{entry.id: True}` for every entry whose own detector still finds its
    defect present in `files`."""
    return {entry.id: DETECTORS[entry.defect_class](files) for entry in entries}


__all__ = ["DETECTORS", "INJECTORS", "apply_corpus", "corpus_defects_present"]
