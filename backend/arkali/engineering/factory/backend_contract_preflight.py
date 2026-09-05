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


def _backend_contract_json_files(files: Mapping[str, str]) -> list[tuple[str, object]]:
    parsed: list[tuple[str, object]] = []
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".json")):
            continue
        try:
            parsed.append((path, json.loads(source)))
        except json.JSONDecodeError:
            continue
    return parsed


def _declares_routes(parsed_files: list[tuple[str, object]]) -> bool:
    for _path, document in parsed_files:
        if not isinstance(document, list):
            continue
        if any(
            isinstance(item, dict) and "path" in item
            and str(item.get("method", "")).lower() in _HTTP_METHODS
            for item in document
        ):
            return True
    return False


def _declares_a_model(parsed_files: list[tuple[str, object]]) -> bool:
    return any(
        isinstance(document, dict) and "fields" in document for _path, document in parsed_files
    )


#: F-0079 (`UPSTREAM_MODEL_NAME_FALLBACK_GAP`). Real production evidence,
#: `goal-mtoun7ih-7odtyr` (`backend/models.json`, `{"fields": {...}}`, no
#: `table_name`): once a real data-model document carries no `table_name`,
#: `product_ux_spec._backend_declared_models` falls back to the FILENAME's
#: own stem (`_path_stem`) as that model's real, permanent name -- here,
#: the plain, generic "models". `product_ux_spec._resource_matching_name`
#: (F-0068's own fix) only strips a trailing SINGULAR "model" suffix
#: ("task_model" -> "task"); "models" ends in "s", not "model", so it is
#: never touched by that normalization and survives as a real, ordinary
#: English word with no domain content at all. No later stage can ever
#: satisfy `product_ux_spec`'s own reconciliation without literally
#: reproducing that exact technical placeholder as a user-facing module
#: name (proven live: two consecutive real, materially different attempts
#: -- "rented_books", then "book_id" -- both a genuine domain name choice,
#: neither ever "models"). This is the earliest point in the pipeline this
#: is mechanically detectable and correctable: `backend_contract` itself,
#: before any downstream stage ever sees the fallback name, and before the
#: fallback is even computed. A real `table_name` supplied here gives
#: `backend_contract`'s OWN retry loop (F-0077's `previous_attempt_output`
#: now applies to every stage) a genuine chance to converge on a
#: meaningful name; `product_ux_spec`'s own reconciliation rule and
#: `_resource_matching_name`'s own normalization are both untouched.
def _models_missing_table_name(parsed_files: list[tuple[str, object]]) -> list[str]:
    return [
        path for path, document in parsed_files
        if isinstance(document, dict) and "fields" in document
        and not str(document.get("table_name") or "").strip()
    ]


def _backend_contract_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`backend_contract`'s own narrow rule: a machine-readable route and data
    model schema is declared (JSON, not Python — see
    STAGED_GENERATION_STAGES.md#1), and every declared data model carries
    its own real `table_name` (F-0079) rather than leaving downstream
    stages to fall back to a generic, non-domain-specific file name."""
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
    for path in _models_missing_table_name(parsed):
        findings.append(SemanticFinding(
            code="backend_contract_model_missing_table_name", path=path,
            detail=(
                "this data model declares no real \"table_name\" -- add one naming "
                "the real domain concept it represents, so later stages have a "
                "real, stable, meaningful name to reconcile against instead of "
                "falling back to this file's own generic name"
            ),
        ))
    return findings


__all__ = ["_backend_contract_findings"]
