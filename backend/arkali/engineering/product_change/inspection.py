"""Read-only, parser-backed structural inspection of a Managed Product's
own source tree (D-030 Ruling 10).

TWO REAL PARSERS, NEITHER INVENTED HERE. Python files are inspected with
the standard library's own `ast` module -- the identical primitive
`engineering.codeintel.python_builder.PythonGraphBuilder` already trusts,
used directly rather than through that module's own richer graph-building
API, since this composition needs only a flat per-file summary, not a
cross-file symbol/dependency graph; reaching `engineering.codeintel`
directly would add a real cross-context edge for a capability the
standard library already provides identically. JS/JSX/TS/TSX files are
inspected by `scripts/inspect_js_source.mjs`, a real AST walk over the
TypeScript compiler's own `createSourceFile` (already installed via
`frontend/node_modules/typescript` -- no new dependency), run as a
subprocess and never imported, exec'd, or otherwise executed as this
context's own code.

NEVER EXECUTES INSPECTED CONTENT. `ast.parse` does not run module-level
statements; the Node subprocess only ever parses syntax, the same
guarantee `engineering.project_import.static_inspection.StaticInspector`
already established for exactly this reason.
"""

from __future__ import annotations

import ast
import json
import pathlib
import posixpath
import re
import subprocess

from arkali.engineering.product_change.errors import ChangesetValidationError, InspectionFailedError

_PYTHON_SUFFIXES = frozenset({".py"})
_JS_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx"})
_LOCAL_RESOURCE_SUFFIXES = frozenset({".css", ".scss", ".sass", ".less", ".json", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp"})
_SKIP_DIR_NAMES = frozenset({"node_modules", "build", "dist", ".git", "__pycache__", ".venv", "venv"})
_INSPECT_JS_SCRIPT = pathlib.Path(__file__).resolve().parents[4] / "scripts" / "inspect_js_source.mjs"
_MAX_GROUNDED_SOURCE_FILES = 12
_MAX_GROUNDED_SOURCE_BYTES = 96 * 1024
_SENSITIVE_NAMES = frozenset({"credentials", "credential", "secrets", "secret", "private_key"})
_SOURCE_SUFFIXES = _PYTHON_SUFFIXES | _JS_SUFFIXES
_LOCAL_RESOLUTION_SUFFIXES = _SOURCE_SUFFIXES | _LOCAL_RESOURCE_SUFFIXES


class PythonFileSummary:
    __slots__ = ("path", "imports", "functions", "classes", "byte_length")

    def __init__(
        self, path: str, imports: list[str], functions: list[str], classes: list[str],
        byte_length: int,
    ) -> None:
        self.path = path
        self.imports = imports
        self.functions = functions
        self.classes = classes
        self.byte_length = byte_length


class SourceInspectionReport:
    """The real, structural facts this composition's model-planning step
    reads -- never lifecycle truth, never persisted by this module itself
    (the orchestration layer registers a rendering of it as evidence)."""

    __slots__ = ("python_files", "js_files", "js_errors")

    def __init__(
        self, python_files: list[PythonFileSummary], js_files: list[dict[str, object]],
        js_errors: list[dict[str, object]],
    ) -> None:
        self.python_files = python_files
        self.js_files = js_files
        self.js_errors = js_errors


class _GroundedSourceContext:
    """A bounded projection of authoritative current source, never a store."""

    __slots__ = ("paths", "_contents")

    def __init__(self, contents: tuple[tuple[str, str], ...]) -> None:
        self.paths = tuple(path for path, _ in contents)
        self._contents = contents

    def render(self) -> str:
        blocks = []
        for path, content in self._contents:
            blocks.append(
                f"--- BEGIN AUTHORITATIVE CURRENT SOURCE: {path} ---\n"
                f"{content}"
                f"{'\n' if content and not content.endswith(chr(10)) else ''}"
                f"--- END AUTHORITATIVE CURRENT SOURCE: {path} ---"
            )
        return "\n\n".join(blocks)


def _is_sensitive_path(relative: str) -> bool:
    parts = pathlib.PurePosixPath(relative).parts
    for part in parts:
        lowered = part.lower()
        if lowered.startswith(".") or lowered.endswith((".pem", ".key", ".p12", ".pfx")):
            return True
        stem = pathlib.PurePosixPath(lowered).stem
        if stem in _SENSITIVE_NAMES or any(token in stem for token in ("credential", "secret")):
            return True
    return False


def _request_terms(request_text: str) -> frozenset[str]:
    return frozenset(term.lower() for term in re.findall(r"[A-Za-z0-9_]+", request_text) if len(term) >= 3)


def _resolve_relative_import(source_path: str, imported: str, available: set[str]) -> str | None:
    if not imported.startswith("."):
        return None
    candidate = posixpath.normpath(posixpath.join(posixpath.dirname(source_path), imported))
    choices = [candidate, *(candidate + suffix for suffix in sorted(_LOCAL_RESOLUTION_SUFFIXES))]
    choices.extend(f"{candidate}/index{suffix}" for suffix in sorted(_SOURCE_SUFFIXES))
    return next((choice for choice in choices if choice in available), None)


def _source_facts(
    report: SourceInspectionReport,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    metadata: dict[str, tuple[str, ...]] = {}
    imports: dict[str, tuple[str, ...]] = {}
    for item in report.python_files:
        metadata[item.path] = (item.path, *item.functions, *item.classes, *item.imports)
        imports[item.path] = tuple(item.imports)
    for item in report.js_files:
        path = str(item["path"])
        metadata[path] = (
            path, *(str(d["name"]) for d in item.get("declarations", [])),
            *(str(x) for x in item.get("jsxElements", [])),
            *(str(x) for x in item.get("imports", [])),
        )
        imports[path] = tuple(str(x) for x in item.get("imports", []))
    return (
        {path: facts for path, facts in metadata.items() if not _is_sensitive_path(path)},
        imports,
    )


def _ranked_seeds(metadata: dict[str, tuple[str, ...]], request_text: str) -> list[str]:
    terms = _request_terms(request_text)
    ranked = [
        (-sum(1 for term in terms if term in " ".join(facts).lower()), path)
        for path, facts in metadata.items()
    ]
    return [path for score, path in sorted(ranked) if score < 0]


def _read_bounded_source(
    root: pathlib.Path, selected: set[str], max_total_bytes: int,
) -> _GroundedSourceContext:
    contents: list[tuple[str, str]] = []
    total = 0
    for relative in sorted(selected):
        content = (root / pathlib.PurePosixPath(relative)).read_text(encoding="utf-8")
        size = len(content.encode("utf-8"))
        if total + size > max_total_bytes:
            raise ChangesetValidationError(
                f"source context budget of {max_total_bytes} bytes cannot include required file {relative!r} in full"
            )
        total += size
        contents.append((relative, content))
    return _GroundedSourceContext(tuple(contents))


def _select_authoritative_source(
    root: pathlib.Path, report: SourceInspectionReport, request_text: str, *,
    max_files: int = _MAX_GROUNDED_SOURCE_FILES,
    max_total_bytes: int = _MAX_GROUNDED_SOURCE_BYTES,
) -> _GroundedSourceContext:
    """Select bounded real source using the existing inspection facts.

    Request-matching files are discovery seeds. Their directly imported
    relative modules are included as contract context. Required files are
    never truncated: an impossible file-count or byte budget is one typed
    refusal before inference.
    """
    if max_files <= 0 or max_total_bytes <= 0:
        raise ChangesetValidationError("source context budget must be positive")
    metadata, imports = _source_facts(report)
    available = set(metadata)
    seeds = _ranked_seeds(metadata, request_text)
    if not seeds:
        # A request such as "change it" carries no mechanical filename or
        # symbol signal. A genuinely small source tree can still be grounded
        # without guessing: include every eligible source file, subject to the
        # identical hard budgets below. A larger tree refuses instead of
        # degrading to summary-only regeneration.
        if len(available) > max_files:
            raise ChangesetValidationError(
                "source-grounded planning found no bounded target and the full eligible "
                f"source set needs {len(available)} files (budget {max_files})"
            )
        seeds = sorted(available)
    selected: set[str] = set(seeds[:max_files])
    for path in tuple(sorted(selected)):
        for imported in imports.get(path, ()):
            resolved = _resolve_relative_import(path, imported, available)
            if resolved is not None:
                selected.add(resolved)
    if len(selected) > max_files:
        raise ChangesetValidationError(
            f"source context budget allows {max_files} files but required selection needs {len(selected)}"
        )
    return _read_bounded_source(root, selected, max_total_bytes)


def _inspect_python(root: pathlib.Path) -> list[PythonFileSummary]:
    summaries: list[PythonFileSummary] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in _SKIP_DIR_NAMES for part in path.relative_to(root).parts[:-1]):
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        imports: list[str] = []
        functions: list[str] = []
        classes: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
        summaries.append(PythonFileSummary(
            path=path.relative_to(root).as_posix(),
            imports=sorted(set(imports)), functions=functions, classes=classes,
            byte_length=len(text.encode("utf-8")),
        ))
    return summaries


def _inspect_js(root: pathlib.Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    if not any(root.rglob(f"*{suffix}") for suffix in _JS_SUFFIXES):
        return [], []
    try:
        result = subprocess.run(
            ["node", str(_INSPECT_JS_SCRIPT), str(root)],
            capture_output=True, text=True, timeout=60.0,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise InspectionFailedError(f"JS/TS inspection subprocess failed: {error}") from error
    if result.returncode != 0:
        raise InspectionFailedError(f"JS/TS inspection refused: {result.stderr.strip()}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise InspectionFailedError(f"JS/TS inspection produced malformed JSON: {error}") from error
    return payload.get("files", []), payload.get("errors", [])


def inspect_source(root: pathlib.Path) -> SourceInspectionReport:
    """Every real Python and JS/JSX/TS/TSX file under `root`, summarised
    structurally. Read-only; raises `InspectionFailedError` only for a
    genuine tooling failure, never for a file this inspector simply finds
    nothing interesting in (an unparseable Python file is silently
    skipped, matching `ast.parse`'s own honest "not valid Python" case
    rather than aborting the whole inspection over one file)."""
    if not root.is_dir():
        raise InspectionFailedError(f"inspection root does not exist: {root}")
    python_files = _inspect_python(root)
    js_files, js_errors = _inspect_js(root)
    return SourceInspectionReport(python_files=python_files, js_files=js_files, js_errors=js_errors)


def render_for_prompt(report: SourceInspectionReport, *, max_files: int = 40) -> str:
    """A compact, deterministic text rendering of the inspection report,
    suitable for bounded discovery only -- never implementation authority."""
    lines: list[str] = []
    for summary in report.python_files[:max_files]:
        lines.append(
            f"- {summary.path} (python, {summary.byte_length}B): "
            f"functions={summary.functions[:8]} classes={summary.classes[:8]}"
        )
    for entry in report.js_files[:max_files]:
        lines.append(
            f"- {entry['path']} ({entry['kind']}, {entry['byteLength']}B): "
            f"declarations={[d['name'] for d in entry['declarations'][:8]]} "
            f"jsx={entry['jsxElements'][:8]}"
        )
    return "\n".join(lines)
