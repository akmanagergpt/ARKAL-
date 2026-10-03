"""Conservative deterministic repair for generated schema bootstrap wiring."""
from __future__ import annotations

import ast
import pathlib
from collections.abc import Mapping


def _zero_arg_bootstraps(source: str) -> tuple[str, ...]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    found: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = node.args
        if args.args or args.posonlyargs or args.kwonlyargs or args.vararg or args.kwarg:
            continue
        if node.name in {"init_db", "create_schema", "init_schema"}:
            found.append(node.name)
    return tuple(found)


def _bootstrap_candidate(path: str, source: str) -> tuple[str, str] | None:
    is_backend_python = path.startswith("backend/") and path.endswith(".py")
    creates_schema = "create table" in source.lower() or ".create_all(" in source
    if not is_backend_python or not creates_schema:
        return None
    names = _zero_arg_bootstraps(source)
    return (path, names[0]) if len(names) == 1 else None


def _route_owner(path: str, source: str) -> bool:
    lowered = source.lower()
    markers = ("@app.route", "@router.", "register_blueprint")
    return (
        path.startswith("backend/")
        and path.endswith(".py")
        and any(marker in lowered for marker in markers)
    )


def _already_imports(source: str, stem: str) -> bool:
    imports = (
        line.strip() for line in source.splitlines()
        if line.strip().startswith(("import ", "from "))
    )
    return any(stem in line for line in imports)


def _repair_unreachable_schema_bootstrap(
    visible_files: Mapping[str, str], stage_files: dict[str, str],
) -> dict[str, str] | None:
    """Reuse one existing zero-argument bootstrap in one unambiguous app."""
    candidates = tuple(filter(None, (
        _bootstrap_candidate(path, source) for path, source in visible_files.items()
    )))
    routes = tuple(
        path for path, source in stage_files.items() if _route_owner(path, source)
    )
    if len(candidates) != 1 or len(routes) != 1:
        return None
    schema_path, bootstrap = candidates[0]
    target = routes[0]
    source = stage_files[target]
    schema = pathlib.PurePosixPath(schema_path)
    if _already_imports(source, schema.stem):
        return None
    module = schema.with_suffix("").as_posix().replace("/", ".")
    repaired = dict(stage_files)
    repaired[target] = f"from {module} import {bootstrap}\n{bootstrap}()\n" + source
    return repaired
