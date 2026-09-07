"""Generated backend/frontend HTTP contract checks for ``engineering.factory``."""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.javascript_syntax_preflight import _javascript_syntax_findings
from arkali.engineering.factory.semantic_finding import SemanticFinding


def frontend_contract_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    vacuity_findings = _frontend_src_missing_findings(files)
    if vacuity_findings:
        return vacuity_findings
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
    return _cors_findings(backend, frontend) + _contract_drift_findings(backend, frontend)


def _frontend_src_missing_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """ANTI-VACUITY (the same class `_backend_tests_stage_findings`'s own
    `backend_tests_missing_top_level_path` already closed for `tests/`,
    golden-work-048, session evidence): every check in `frontend_contract_
    findings` only ever iterates files already prefixed `frontend/src/` --
    a real attempt that instead wrote its own real frontend source under a
    different path (bare `src/...`, real evidence: `factory-goal-mtqrbyqj-
    5m1bf8` -- the model's own immediately preceding stage had shown it
    that exact bare-path convention, in its own visible prior context, and
    it naturally continued it) would otherwise pass that function on a
    silently EMPTY frontend blob: no syntax findings (nothing to parse),
    no CORS finding (`"http://localhost:" not in ""`), and -- for any
    backend exposing no POST/PUT/DELETE route, as this real one did not --
    no contract-drift finding either, since that loop's own `_exposes`
    check never even runs. The real defect then propagated silently into
    `frontend_ui`'s own visible prior context, which correctly, but for
    the wrong stage, reported every downstream check as missing."""
    if any(path.startswith("frontend/src/") for path in files):
        return []
    return [SemanticFinding(
        code="frontend_client_missing_top_level_path", path="frontend/src/",
        detail=(
            "no file exists under the top-level frontend/src/ path -- every real "
            "frontend file this stage writes must be placed there"
        ),
    )]


def _contract_drift_findings(backend: str, frontend: str) -> list[SemanticFinding]:
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
