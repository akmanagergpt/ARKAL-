"""`backend_contract`'s own narrow stage check.

Owner: `engineering.factory`. Split out of `component_generation.py`
(ADR-0008 decomposition, not a GATE 8 exception): that module was pushed
to 406 logical lines — over its 400-line ceiling — by this session's
`frontend_ux_preflight` wiring, measured by the real architecture-budget
gate, not assumed. This check has no dependency on anything else in
`component_generation.py` (only `SemanticFinding`), so it is the smallest
clean unit to move, the same shape `stage_prompting.py` was already split
out for.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from arkali.engineering.factory.semantic_finding import SemanticFinding

_HTTP_METHODS = frozenset({"get", "post", "put", "delete", "patch"})


def _backend_contract_json_files(files: Mapping[str, str]) -> list[object]:
    parsed: list[object] = []
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".json")):
            continue
        try:
            parsed.append(json.loads(source))
        except json.JSONDecodeError:
            continue
    return parsed


def _declares_routes(parsed_files: list[object]) -> bool:
    for document in parsed_files:
        if not isinstance(document, list):
            continue
        if any(
            isinstance(item, dict) and "path" in item
            and str(item.get("method", "")).lower() in _HTTP_METHODS
            for item in document
        ):
            return True
    return False


def _declares_a_model(parsed_files: list[object]) -> bool:
    return any(
        isinstance(document, dict) and "fields" in document for document in parsed_files
    )


def _backend_contract_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`backend_contract`'s own narrow rule: a machine-readable route and data
    model schema is declared (JSON, not Python — see
    STAGED_GENERATION_STAGES.md#1)."""
    parsed = _backend_contract_json_files(files)
    findings: list[SemanticFinding] = []
    if not _declares_routes(parsed):
        findings.append(SemanticFinding(
            code="backend_contract_no_routes", path="backend/",
            detail="no backend/*.json file declares a route array with path+method",
        ))
    if not _declares_a_model(parsed):
        findings.append(SemanticFinding(
            code="backend_contract_no_models", path="backend/",
            detail="no backend/*.json file declares a data model with a 'fields' key",
        ))
    return findings


__all__ = ["_backend_contract_findings"]
