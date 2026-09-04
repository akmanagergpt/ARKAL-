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
import subprocess

from arkali.engineering.product_change.errors import InspectionFailedError

_PYTHON_SUFFIXES = frozenset({".py"})
_JS_SUFFIXES = frozenset({".js", ".jsx", ".ts", ".tsx"})
_SKIP_DIR_NAMES = frozenset({"node_modules", "build", "dist", ".git", "__pycache__", ".venv", "venv"})
_INSPECT_JS_SCRIPT = pathlib.Path(__file__).resolve().parents[4] / "scripts" / "inspect_js_source.mjs"


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
    suitable for embedding in a real model prompt -- never the raw file
    bytes themselves (the model requests specific file content separately
    if it needs it; this is a table of contents, not the whole book)."""
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
