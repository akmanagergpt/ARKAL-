"""Per-stage narrow validation for the backend half of staged generation.

Owner: `engineering.factory`. Moved out of `component_generation.py`
(ADR-0008 decomposition, not a GATE 8 exception: that module's own retry
orchestration plus this session's `product_ux_spec` flat-envelope repair
pushed it to 419/400 measured logical lines) — the same shape every
frontend-side stage validator was already split out into its own module
for earlier this session. Self-contained: needs nothing from
`component_generation.py` itself (no `_StageEnvelope`, no model
orchestration), only the same real, whole-product findings helpers
`product_preflight.py`/`route_response_preflight.py`/
`test_contract_preflight.py` already expose.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import (
    SemanticFinding, _persistence_findings, _schema_context_findings,
)
from arkali.engineering.factory.route_response_preflight import (
    _missing_generated_id_findings, _raw_row_jsonify_findings,
)
from arkali.engineering.factory.test_contract_preflight import _fixture_findings, _lifecycle_findings


def _backend_text(files: Mapping[str, str]) -> str:
    return "\n".join(
        source.lower() for path, source in files.items()
        if path.startswith("backend/") and path.endswith(".py")
    )


def _python_syntax_findings(files: Mapping[str, str], *, path_prefix: str) -> list[SemanticFinding]:
    """Real `ast.parse` on every `.py` file under `path_prefix`.

    golden-work-045's real backend_implementation output (session evidence)
    passed every substring/regex check here while containing an actual
    `SyntaxError` (an unterminated multi-line string) — none of the checks
    below ever parse the code they inspect. This is the gap that closes;
    same finding code (`python_syntax`) `product_preflight.python_modules`
    already uses for the same defect at the final whole-product gate, so a
    caller sees one vocabulary either way.
    """
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith(path_prefix) and path.endswith(".py")):
            continue
        try:
            ast.parse(source)
        except SyntaxError as error:
            findings.append(SemanticFinding(
                code="python_syntax", path=path,
                detail=f"line {error.lineno}: {error.msg}",
            ))
    return findings


def _schema_only_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Schema/persistence only — no route or entrypoint requirement.

    backend_contract no longer declares any Python (see
    STAGED_GENERATION_STAGES.md#1), so `product_preflight._persistence_findings`
    (which bundles schema together with route markers and an entrypoint check)
    cannot pass at this stage by construction — those belong to
    backend_implementation, not backend_schema. This duplicates
    `_persistence_findings`'s own sqlite/schema pair (not its route/entrypoint
    half) rather than promoting a fourth product_preflight helper to public:
    the real architecture-budget gate already measured this context at its
    40/40 public-surface ceiling once this session (see
    `component_generation.py`'s own docstring) and every net-new promotion
    was reverted for exactly that reason.
    """
    syntax_findings = _python_syntax_findings(files, path_prefix="backend/")
    if syntax_findings:
        return syntax_findings
    backend_text = _backend_text(files)
    findings: list[SemanticFinding] = []
    uses_sqlite = "sqlite3" in backend_text or "sqlite://" in backend_text
    creates_schema = "create table" in backend_text or "create_all(" in backend_text
    if not uses_sqlite:
        findings.append(SemanticFinding(
            code="missing_persistence_code", path="backend/",
            detail="backend Python source contains no executable SQLite persistence",
        ))
    elif not creates_schema:
        findings.append(SemanticFinding(
            code="missing_schema_bootstrap", path="backend/",
            detail="SQLite is selected but no schema creation or migration is present",
        ))
    findings.extend(_schema_context_findings(backend_text))
    return findings


#: Same marker set `http_contract_preflight.frontend_contract_findings` checks
#: for (FastAPI/Starlette's CORSMiddleware, Flask's flask_cors/CORS(app)).
#: Duplicated here (3 short strings) rather than imported, since that
#: function's own marker tuple is a local, unexported detail — promoting it
#: to module level there would cost another public-surface symbol this
#: context has no room for.
_CORS_MARKERS = ("corsmiddleware", "flask_cors", "cors(app")


def _backend_implementation_stage_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Full persistence+routes+entrypoint — CORS is not this stage's concern
    (see backend_cors_boundary, immediately after). A real local model
    reliably produced routes+schema+entrypoint together but did not
    reliably add CORS in the same bounded attempt even when this stage's
    own rule explicitly required it (golden-work-045, two consecutive real
    runs) — narrowed to its own stage instead of raised attempts or
    repeated whole-stage retries on the same combined requirement.
    """
    syntax_findings = _python_syntax_findings(files, path_prefix="backend/")
    if syntax_findings:
        return syntax_findings
    return _persistence_findings(files) + _schema_context_findings(_backend_text(files)) + _missing_generated_id_findings(files) + _raw_row_jsonify_findings(files)


def _cors_boundary_stage_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """backend_cors_boundary's sole narrow rule: real CORS middleware exists.

    Checked unconditionally (not "only if a frontend already exists"): this
    stage runs before any frontend stage, by design, so no frontend bytes
    are available yet to condition on.
    """
    syntax_findings = _python_syntax_findings(files, path_prefix="backend/")
    if syntax_findings:
        return syntax_findings
    backend_text = _backend_text(files)
    if any(marker in backend_text for marker in _CORS_MARKERS):
        return []
    return [SemanticFinding(
        code="missing_browser_origin_boundary", path="backend/",
        detail="backend declares no CORS middleware for its separate-origin frontend",
    )]


def _backend_tests_stage_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    syntax_findings = _python_syntax_findings(files, path_prefix="tests/")
    if syntax_findings:
        return syntax_findings
    test_paths = [p for p in files if p.startswith("tests/") and p.endswith(".py")]
    if not test_paths:
        # ANTI-VACUITY. golden-work-048 (session evidence, frozen): a real
        # qwen2.5-coder:14b placed its tests under backend/tests/test_app.py
        # instead — a reasonable convention this stage's rule never ruled
        # out — and this check, only ever iterating paths that already
        # start with tests/, silently found nothing to reject. The
        # whole-product gate's required_roots checks the top-level path
        # segment; failing here, at the stage that owns it, is cheaper and
        # more specific than only discovering it at the final gate.
        return [SemanticFinding(
            code="backend_tests_missing_top_level_path", path="tests/",
            detail="no test file exists under the top-level tests/ path")]
    findings: list[SemanticFinding] = []
    for path in test_paths:
        tree = ast.parse(files[path])
        findings.extend(_fixture_findings(path, tree))
        findings.extend(_lifecycle_findings(files))
    return findings
