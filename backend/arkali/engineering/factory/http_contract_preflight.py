"""Generated backend/frontend HTTP contract checks for ``engineering.factory``."""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding


def frontend_contract_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    backend = "\n".join(
        source.lower()
        for path, source in files.items()
        if path.startswith("backend/") and path.endswith(".py")
    )
    frontend = "\n".join(
        source.lower()
        for path, source in files.items()
        if path.startswith("frontend/src/")
    )
    findings: list[SemanticFinding] = []
    for method in ("post", "put", "delete"):
        if not _exposes(backend, method):
            continue
        direct_call = f"axios.{method}(" in frontend
        fetch_option = re.search(rf"method\s*:\s*['\"]{method}['\"]", frontend)
        if not direct_call and fetch_option is None:
            findings.append(
                SemanticFinding(
                    code="frontend_backend_contract_drift",
                    path="frontend/src/",
                    detail=f"backend exposes {method.upper()} but frontend has no matching call",
                )
            )
    return findings


def _exposes(backend: str, method: str) -> bool:
    quoted = f"'{method}'" in backend or f'"{method}"' in backend
    decorated = f"@app.{method}" in backend or f"@router.{method}" in backend
    return quoted or decorated


__all__ = ["frontend_contract_findings"]
