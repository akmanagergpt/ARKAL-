"""Whole-product regression check: a candidate must not remove a parent
revision's existing exported symbols.

Owner: `engineering.factory`. Split out of `product_preflight.py`
(ADR-0008 decomposition, not a GATE 8 exception): that module was pushed
to 403 logical lines — over its 400-line ceiling — by this session's
`frontend_ux_preflight` wiring, measured by the real architecture-budget
gate, not assumed. `_module_name`/`_exports` stay in `product_preflight.py`
(also used by `_python_modules` there); this module imports them rather
than duplicating them, since both are already module-private and this is a
one-directional dependency, not a cycle — `product_preflight.py` only
reaches this module through a local import inside `inspect_product_files`,
the same deferred-import shape it already uses for `http_contract_preflight`
and `frontend_manifest_preflight`.
"""

from __future__ import annotations

from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding, _exports, _module_name


def _regression_findings(
    files: Mapping[str, str], baseline: Mapping[str, str] | None
) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for path, original in (baseline or {}).items():
        if _module_name(path) is None or path not in files:
            continue
        try:
            removed = sorted(_exports(original) - _exports(files[path]))
        except SyntaxError:
            continue
        if removed:
            findings.append(
                SemanticFinding(
                    code="removed_parent_symbols",
                    path=path,
                    detail=f"candidate removed existing symbols {removed!r}",
                )
            )
    return findings


__all__ = ["_regression_findings"]
