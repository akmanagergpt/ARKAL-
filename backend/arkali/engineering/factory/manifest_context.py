"""Reduced model-context construction for the `manifests` staged-generation stage.

Owner: `engineering.factory`. Split out of `component_generation.py`
(ADR-0008 decomposition, not a GATE 8 exception): adding this reduction
pushed that module to 452 logical lines against its 400 ceiling, measured
by the real architecture-budget gate, not assumed.

WHY THIS EXISTS. `manifests` declares all 9 prior stages as inputs —
every route, test, UI and UX-planning file this pipeline produces —
because reconciling dependencies genuinely needs to know what every
stage actually imports. Sending all of it as full file bytes caused a
real HTTP-level timeout, 4/4 attempts, at exactly this stage (the
largest prompt of the ten) — session evidence, golden-work-046.
`product_preflight._manifest_findings` (verified by reading its source,
not assumed) only ever reads three things: `backend/requirements.txt`,
`frontend/package.json`, and whether `frontend/public/index.html` exists —
never route/test/UI bytes. Everything this module returns instead of
those bytes is a mechanically-extracted signal, never a paraphrase and
never invented: real top-level package names actually imported by the
real source, nothing else.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Mapping

_LOCAL_PACKAGE_ROOTS = frozenset({"backend", "frontend", "tests"})


def _third_party_python_imports(files: Mapping[str, str]) -> frozenset[str]:
    """Real top-level package names imported by backend/*.py, minus stdlib
    and this candidate's own local roots — a mechanical signal of what
    manifests should declare, not the source that imports them."""
    names: set[str] = set()
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".py")):
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
    (never full-file) import signals for everything else — not the whole
    accumulated candidate. Nothing about the other 8 stages' own contracts
    or contexts changes; this applies to manifests only.
    """
    reduced: dict[str, str] = {}
    for path in ("backend/requirements.txt", "backend/pyproject.toml", "frontend/package.json"):
        if path in visible_files:
            reduced[path] = visible_files[path]
    if "frontend/public/index.html" in visible_files:
        reduced["frontend/public/index.html"] = visible_files["frontend/public/index.html"]
    reduced["_extracted/backend_third_party_imports.txt"] = "\n".join(
        sorted(_third_party_python_imports(visible_files))
    )
    reduced["_extracted/frontend_import_targets.txt"] = "\n".join(
        sorted(_frontend_import_targets(visible_files))
    )
    return reduced
