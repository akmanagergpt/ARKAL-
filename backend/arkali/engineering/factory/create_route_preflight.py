"""Real, general check for one create-route response-shape gap.

Owner: `engineering.factory`. golden-work-052 and golden-work-053 (session
evidence, frozen, byte-identical across two separate real
`qwen2.5-coder:14b` runs): the same real model's `create_task` handler
executed a SQL `INSERT` and returned `jsonify(data), 201` — the client's
own submitted request body, verbatim, never the row id SQLite actually
assigned — while that same model's own generated test asserted the
response includes `'id'`. A real cross-file (test vs. implementation)
consistency gap only real execution caught (`_backend_tests_stage_
findings`'s own AST checks have no way to know what a route handler
elsewhere in the file actually returns).

GENERAL, NOT GOLDEN-SPECIFIC. This checks for the pattern — a function
whose body contains both a SQL `INSERT` and a `jsonify` call but never
references `cursor.lastrowid` — not any specific route path, table or
field name. Any Flask+`sqlite3` backend this pipeline's own stack always
produces can trip or satisfy this check identically.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding


def _missing_generated_id_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("backend/") and path.endswith(".py")):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            segment = (ast.get_source_segment(source, node) or "").lower()
            if "insert into" not in segment or "jsonify" not in segment:
                continue
            if "lastrowid" in segment:
                continue
            findings.append(SemanticFinding(
                code="missing_generated_id_in_create_response", path=path,
                detail=(
                    f"function {node.name!r} executes a SQL INSERT and returns "
                    "JSON but never references cursor.lastrowid — add the row's "
                    "own generated id (e.g. cursor.lastrowid) to the response "
                    "instead of only the submitted request body"
                ),
            ))
    return findings
