"""Generated backend/frontend HTTP contract checks for ``engineering.factory``."""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.javascript_syntax_preflight import _javascript_syntax_findings
from arkali.engineering.factory.product_preflight import SemanticFinding


def frontend_contract_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    syntax_findings = _javascript_syntax_findings(files, path_prefix="frontend/src/")
    if syntax_findings:
        return syntax_findings
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
    findings: list[SemanticFinding] = [*_cors_findings(backend, frontend)]
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


#: FastAPI/Starlette (`CORSMiddleware`) and Flask (`flask_cors`/`CORS(app)`) -
#: real evidence this session (golden-work-045) showed a genuine Flask CORS
#: gap; the marker set covers Flask's own idiom too, not just FastAPI's, so a
#: correctly-CORS'd Flask backend is not flagged as if it were the same defect.
_CORS_MARKERS = ("corsmiddleware", "flask_cors", "cors(app")


def _cors_findings(backend: str, frontend: str) -> list[SemanticFinding]:
    if "http://localhost:" not in frontend:
        return []
    if any(marker in backend for marker in _CORS_MARKERS):
        return []
    return [
        SemanticFinding(
            code="missing_browser_origin_boundary",
            path="backend/",
            detail="frontend uses a separate localhost origin but backend has no CORS policy",
        )
    ]


def _exposes(backend: str, method: str) -> bool:
    quoted = f"'{method}'" in backend or f'"{method}"' in backend
    decorated = f"@app.{method}" in backend or f"@router.{method}" in backend
    return quoted or decorated


__all__ = ["frontend_contract_findings"]
