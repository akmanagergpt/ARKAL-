"""Real check: every frontend_client export a UI file calls is imported there.

Owner: `engineering.factory`. Split out as its own module from
`frontend_manifest_preflight.py` (ADR-0008 decomposition, not a GATE 8
exception: that module reached its own 400-logical-line ceiling, measured
live by the real architecture gate, not assumed, the moment this check
was added there).

golden-work-090 (session evidence, frozen): App.js's real student list
gained a real, correct `<Link to={`/students/edit/${student.id}`}>` and a
real inline delete button calling `deleteStudent(student.id)` directly on
click -- but App.js's own import line
(`import { getStudents, getCourses, getPayments } from './apiClient';`)
was never updated to include `deleteStudent`, a real export `apiClient.js`
genuinely declares. A real, hard `ReferenceError: deleteStudent is not
defined` the moment a real user clicks Delete -- syntactically legal JS,
`node --check` (javascript_syntax_preflight.py) cannot see a bare
identifier reference.

Duplicates a small export-name extractor rather than importing
`frontend_ux_preflight._exported_js_names`: that module already imports
from `frontend_manifest_preflight.py`, and this module sits alongside it,
so importing across would risk a cycle for no real benefit -- the same
shape this pipeline's own `_CORS_MARKERS`-style duplication already uses
elsewhere.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from arkali.engineering.factory.product_preflight import SemanticFinding

_CLIENT_INLINE_EXPORT = re.compile(r"export\s+(?:const|function)\s+(\w+)")
_CLIENT_GROUPED_EXPORT = re.compile(r"export\s*\{([^}]*)\}")
_IMPORT_STATEMENT = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*['"][^'"]+['"]""")
_LOCAL_DECLARATION = re.compile(r"(?:function|const|let|var)\s+(\w+)")


def _client_exported_names(client_text: str) -> frozenset[str]:
    names = set(_CLIENT_INLINE_EXPORT.findall(client_text))
    for block in _CLIENT_GROUPED_EXPORT.findall(client_text):
        for part in block.split(","):
            local_name = part.strip().split(" as ")[0].strip()
            if local_name:
                names.add(local_name)
    return frozenset(names)


def _file_imported_locals(source: str) -> set[str]:
    imported: set[str] = set()
    for block in _IMPORT_STATEMENT.findall(source):
        for part in block.split(","):
            local_name = part.strip().split(" as ")[-1].strip()
            if local_name:
                imported.add(local_name)
    return imported


def _missing_client_calls_in_file(source: str, exported: frozenset[str]) -> list[str]:
    imported = _file_imported_locals(source)
    declared = set(_LOCAL_DECLARATION.findall(source))
    return sorted(
        name for name in exported
        if name not in imported and name not in declared
        and re.search(rf"\b{name}\s*\(", source)
    )


def _client_call_missing_import_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """Every real `frontend_client` export a UI file actually calls must
    be imported in that same file -- checked per file, since an import
    in one component never brings a name into scope in another, the same
    shape `frontend_manifest_preflight._react_router_missing_import_findings`
    already uses. A name also declared locally in the same file (a real,
    if unlikely, shadowing case) is never flagged."""
    client_text = "\n".join(
        source for path, source in files.items()
        if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
        and "client" in path.lower()
    )
    exported = _client_exported_names(client_text)
    if not exported:
        return []
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        if "client" in path.lower():
            continue
        missing = _missing_client_calls_in_file(source, exported)
        if missing:
            findings.append(SemanticFinding(
                code="frontend_client_call_missing_import", path=path,
                detail=(
                    f"{path} calls {missing!r} but never imports them from the real "
                    "frontend_client module that declares them -- a real runtime "
                    "ReferenceError, not a syntax error `node --check` can see"
                ),
            ))
    return findings
