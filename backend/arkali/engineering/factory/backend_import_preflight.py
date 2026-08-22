"""Whole-product check: every backend/*.py file's own imports resolve.

Owner: `engineering.factory`. Split out of `product_preflight.py`
(ADR-0008 decomposition, not a GATE 8 exception): that module was pushed
to 423 logical lines — over its 400-line ceiling — by this check,
measured by the real architecture-budget gate, not assumed.
`_import_findings`/`_declared_dependencies` stay in `product_preflight.py`
(also used there for `tests/*.py`); this module imports them rather than
duplicating them — a one-directional dependency, not a cycle:
`product_preflight.py` only reaches this module through a local import
inside `inspect_product_files`, the same deferred-import shape it already
uses for `frontend_ux_preflight`/`regression_preflight`.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import (
    SemanticFinding,
    _declared_dependencies,
    _import_findings,
)


def _backend_import_findings(
    files: Mapping[str, str], modules: Mapping[str, tuple[str, set[str]]]
) -> list[SemanticFinding]:
    """Every backend/*.py file's own imports must resolve to a real local
    module or a declared/stdlib package — the same rule `_import_findings`
    already enforces for tests/*.py, applied to backend-internal imports
    too.

    golden-work-067 (real repository evidence, real qwen2.5-coder:14b,
    frozen): `backend/db.py` and `backend/app.py` both wrote
    `from backend.data_model import data_model` — never used anywhere in
    either file — against `backend/data_model.json`, a real
    backend_contract schema *document*, not a Python module.
    `ModuleNotFoundError: No module named 'backend.data_model'` on the
    real, first `pytest` collection of this real candidate; nothing
    before this checked whether a backend module's own import actually
    resolved, only whether its syntax parsed (`ast.parse` alone is blind
    to this — the import is syntactically valid Python).

    Whole-product-gate only, deliberately not a per-stage check:
    `backend/requirements.txt` (declaring real third-party dependencies
    like flask) does not exist until `manifests`, the very last stage —
    checking this earlier would misreport every real, not-yet-declared
    third-party import as a missing local module.
    """
    findings: list[SemanticFinding] = []
    dependencies = _declared_dependencies(files)
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".py")):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue  # a python_syntax finding elsewhere already covers this
        findings.extend(_import_findings(path, tree, modules, dependencies))
    return findings


__all__ = ["_backend_import_findings"]
