"""Reduced model-context construction for the `manifests` staged-generation stage.

Owner: `engineering.factory`. Split out of `component_generation.py`
(ADR-0008 decomposition, not a GATE 8 exception): adding this reduction
pushed that module to 452 logical lines against its 400 ceiling, measured
by the real architecture-budget gate, not assumed.

WHY THIS EXISTS. `manifests` declares all 10 prior stages as inputs —
every route, test, UI, mutation-UI and UX-planning file this pipeline
produces — because reconciling dependencies genuinely needs to know
what every stage actually imports. Sending all of it as full file bytes
caused a real HTTP-level timeout, 4/4 attempts, at exactly this stage
(the largest prompt of the eleven) — session evidence, golden-work-046.
`product_preflight._manifest_findings` (verified by reading its source,
not assumed) only ever reads three things: `backend/requirements.txt`,
`frontend/package.json`, and whether `frontend/public/index.html` exists —
never route/test/UI bytes. Everything this module returns instead of
those bytes is a mechanically-extracted signal, never a paraphrase and
never invented: real top-level package names actually imported by the
real source (both `backend/*.py` and `tests/*.py` — golden-work-072,
session evidence, frozen: a real test file's own `import pytest` was
invisible to manifests until this covered `tests/*.py` too), nothing
else.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Mapping

_LOCAL_PACKAGE_ROOTS = frozenset({"backend", "frontend", "tests"})


def _third_party_python_imports(files: Mapping[str, str], *, path_prefix: str) -> frozenset[str]:
    """Real top-level package names imported by `path_prefix`'s own *.py
    files, minus stdlib and this candidate's own local roots — a
    mechanical signal of what manifests should declare, not the source
    that imports them.

    golden-work-072 (session evidence, frozen): this only ever scanned
    `backend/*.py` — `tests/test_app.py` wrote real `import pytest` and
    real `@pytest.fixture` usage, a genuinely idiomatic real pytest test
    file, and manifests had no way to know a test file needed anything
    declared at all, since its own reduced context never saw tests/*.py
    imports in any form. The real whole-product gate refused the
    candidate outright: `tests/test_app.py imports undeclared dependency
    'pytest'`.
    """
    names: set[str] = set()
    for path, source in files.items():
        if not (path.startswith(path_prefix) and path.endswith(".py")):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                names.add(node.module.split(".", 1)[0])
    return frozenset(names - sys.stdlib_module_names - _LOCAL_PACKAGE_ROOTS)


def _backend_entrypoint_module(files: Mapping[str, str]) -> str | None:
    """The real backend/*.py file carrying a `if __name__ == '__main__':`
    guard, as its dotted module path (e.g. `backend/app.py` -> `backend.app`)
    — the same real signal `product_preflight._persistence_findings`
    already uses to detect a runnable entrypoint exists at all, here named
    rather than only detected.

    golden-work-067/068 (session evidence, frozen): a real
    qwen2.5-coder:14b's own real backend_implementation output used
    absolute `from backend.db import init_db` / `import backend.db`
    imports — legal, resolving Python (`backend_import_preflight.py` now
    proves it) — that only resolve when the project root is on `sys.path`.
    `python backend/app.py` (direct script invocation) does not put it
    there; `python -m backend.app` (module invocation) does. manifests
    cannot know the real entrypoint's filename from its own reduced
    context otherwise — nothing before this extracted it.
    """
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".py")):
            continue
        if re.search(r"""(?m)^if\s+__name__\s*==\s*['"]__main__['"]\s*:""", source):
            return path[: -len(".py")].replace("/", ".")
    return None


_JS_IMPORT_TARGET = re.compile(r"""(?:from|require\()\s*['"]([^'"]+)['"]""")


def _frontend_import_targets(files: Mapping[str, str]) -> frozenset[str]:
    """Real npm package names imported by frontend/src/*.{js,jsx,ts,tsx} —
    relative imports (./ or ../, this candidate's own local modules) excluded."""
    names: set[str] = set()
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx", ".ts", ".tsx"))):
            continue
        for match in _JS_IMPORT_TARGET.finditer(source):
            target = match.group(1)
            if not target.startswith("."):
                names.add(target.split("/")[0])
    return frozenset(names)


def _manifest_context(visible_files: Mapping[str, str]) -> dict[str, str]:
    """The reduced context manifests actually needs: real bytes for the
    exact paths its own validator reads, plus mechanically-extracted
    (never full-file) import and entrypoint signals for everything else —
    not the whole accumulated candidate. Nothing about the other 10
    stages' own contracts or contexts changes; this applies to manifests
    only.
    """
    reduced: dict[str, str] = {}
    for path in ("backend/requirements.txt", "backend/pyproject.toml", "frontend/package.json"):
        if path in visible_files:
            reduced[path] = visible_files[path]
    if "frontend/public/index.html" in visible_files:
        reduced["frontend/public/index.html"] = visible_files["frontend/public/index.html"]
    python_imports = _third_party_python_imports(
        visible_files, path_prefix="backend/"
    ) | _third_party_python_imports(visible_files, path_prefix="tests/")
    reduced["_extracted/backend_third_party_imports.txt"] = "\n".join(sorted(python_imports))
    reduced["_extracted/frontend_import_targets.txt"] = "\n".join(
        sorted(_frontend_import_targets(visible_files))
    )
    entrypoint = _backend_entrypoint_module(visible_files)
    if entrypoint is not None:
        reduced["_extracted/backend_entrypoint_module.txt"] = entrypoint
    return reduced
