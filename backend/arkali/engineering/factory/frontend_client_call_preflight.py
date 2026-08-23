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

golden-work-091 (session evidence, frozen): a real qwen2.5-coder:14b
reproduced the identical class in a different file -- `StudentForm.js`
called `getStudent(id)` inside a real `useEffect`, but its own import
line (`import { createStudent, updateStudent } from './apiClient';`)
never named it -- and exhausted all 4 real `frontend_forms` attempts on
it, even with this check's own accurate per-attempt feedback. Unlike
the route-reachability class (real application logic only the model can
decide), this fix is as mechanically unambiguous as the Werkzeug<3 and
react-router-version repairs (golden-work-050/051's own lesson): merge
the missing name(s) into whichever import statement in the same file
already names a `*client*`-matching source path.

golden-work-097 (session evidence, frozen): the mirror image of
golden-work-090/091 -- `TaskDelete.js` wrote a real
`import { deleteTask } from './apiClient'` and called `deleteTask(id)`
inside a real onClick handler, but `apiClient.js`'s own grouped export
statement never named `deleteTask` at all. A real `npm run build`
compiled successfully (an ES-module named import of something the
target module never exports is not a build-time error, it resolves to
`undefined`); only a real click in a real browser would throw
`TypeError: deleteTask is not a function`. No deterministic repair
exists for this direction (unlike the missing-import case, deciding
whether `apiClient.js` should gain a real `deleteTask` calling a real
backend route, or `TaskDelete.js`'s own call should not exist at all,
is real application logic only the model can decide) -- finding-only.

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

from arkali.engineering.factory.semantic_finding import SemanticFinding

_CLIENT_INLINE_EXPORT = re.compile(r"export\s+(?:const|function)\s+(\w+)")
_CLIENT_GROUPED_EXPORT = re.compile(r"export\s*\{([^}]*)\}")
_IMPORT_STATEMENT = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*['"][^'"]+['"]""")
_NAMED_IMPORT = re.compile(r"""import\s*\{([^}]*)\}\s*from\s*['"]([^'"]+)['"]""")
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


def _phantom_imports_in_file(
    path: str, source: str, exported: frozenset[str],
) -> list[SemanticFinding]:
    """One file's own scan: every `*client*`-matching import statement it
    declares, checked for names the client module never actually
    exports. Extracted from `_phantom_client_import_findings` (ADR-0008
    decomposition, not a GATE 8 exception: that function's own measured
    complexity exceeded its ceiling) so the per-file decision logic is
    measured on its own."""
    findings: list[SemanticFinding] = []
    for match in _NAMED_IMPORT.finditer(source):
        if "client" not in match.group(2).lower():
            continue
        imported_names = [
            part.strip().split(" as ")[-1].strip()
            for part in match.group(1).split(",") if part.strip()
        ]
        phantom = sorted(name for name in imported_names if name and name not in exported)
        if phantom:
            findings.append(SemanticFinding(
                code="frontend_phantom_client_import", path=path,
                detail=(
                    f"{path} imports {phantom!r} from {match.group(2)!r} but that "
                    "module never exports them -- a real runtime TypeError "
                    "('is not a function') the moment this is called, not a "
                    "build-time or syntax error"
                ),
            ))
    return findings


def _phantom_client_import_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """The mirror image of `_client_call_missing_import_findings`: there, a
    real call exists with no matching import; here, a real import exists
    naming something the `*client*`-matching module never actually
    exports.

    golden-work-097 (session evidence, frozen): `TaskDelete.js` wrote
    `import { deleteTask } from './apiClient'` and called `deleteTask(id)`
    inside a real onClick handler -- `apiClient.js`'s own grouped export
    statement (`export { getTasks, createTask, getTask, updateTask };`)
    never named `deleteTask` at all. A real `npm run build` compiled
    successfully (a named ES-module import of a name the target module
    never exports resolves to `undefined` at runtime, not a build-time
    error) -- only a real click would throw `TypeError: deleteTask is
    not a function` in a real browser."""
    client_text = "\n".join(
        source for path, source in files.items()
        if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
        and "client" in path.lower()
    )
    if not client_text:
        return []
    exported = _client_exported_names(client_text)
    findings: list[SemanticFinding] = []
    for path, source in files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        if "client" in path.lower():
            continue
        findings.extend(_phantom_imports_in_file(path, source, exported))
    return findings


def _repair_missing_client_call_import_in_source(source: str, exported: frozenset[str]) -> str | None:
    """One file's own repair: merges the missing name(s) into whichever
    real import statement in this file already names a `*client*`-
    matching source path. Returns `None` when nothing is missing, or
    when the file calls a client export but has no existing client-like
    import to merge into at all -- inventing a relative path here could
    easily be wrong (different files sit at different directory depths),
    so that case is left for the model, not guessed."""
    missing = _missing_client_calls_in_file(source, exported)
    if not missing:
        return None
    match = next(
        (m for m in _NAMED_IMPORT.finditer(source) if "client" in m.group(2).lower()), None,
    )
    if match is None:
        return None
    existing_names = [n.strip() for n in match.group(1).split(",") if n.strip()]
    new_import = (
        "import { " + ", ".join(existing_names + missing) + " } from '" + match.group(2) + "'"
    )
    return source[:match.start()] + new_import + source[match.end():]


def _repair_missing_client_call_imports(
    merged_files: Mapping[str, str], stage_files: Mapping[str, str],
) -> dict[str, str] | None:
    """Deterministic repair mirroring `frontend_manifest_preflight.py`'s
    `Werkzeug<3`-style repairs (golden-work-050/051's own lesson: once
    the exact, unambiguous fix for a real, verified defect is known,
    applying it and re-validating is more honest than another blind
    model retry). golden-work-091 (session evidence, frozen): a real
    qwen2.5-coder:14b exhausted all 4 real `frontend_forms` attempts on
    this exact class even with accurate per-attempt feedback. Checked
    against `merged_files` (the real, declared `frontend_client` export
    names live in an earlier stage's own output, not necessarily this
    stage's own `stage_files`) but only ever patches `stage_files` --
    the same shape `frontend_manifest_preflight._repair_react_router_
    version_mismatch` already uses."""
    client_text = "\n".join(
        source for path, source in merged_files.items()
        if path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))
        and "client" in path.lower()
    )
    exported = _client_exported_names(client_text)
    if not exported:
        return None
    patched: dict[str, str] | None = None
    for path, source in stage_files.items():
        if not (path.startswith("frontend/src/") and path.endswith((".js", ".jsx"))):
            continue
        if "client" in path.lower():
            continue
        repaired_source = _repair_missing_client_call_import_in_source(source, exported)
        if repaired_source is None:
            continue
        if patched is None:
            patched = dict(stage_files)
        patched[path] = repaired_source
    return patched
