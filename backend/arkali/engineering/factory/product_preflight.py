"""Domain-independent semantic preflight for generated product candidates.

Owner: ``engineering.factory`` (strict model-output validation).  The check
compares a candidate only with its own tests and optional parent revision.  It
contains no Golden-family names and renders no acceptance verdict.
"""

from __future__ import annotations

import ast
import pathlib
import sys
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from arkali.engineering.factory.errors import ProductSemanticPreflightError


class SemanticFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    path: str
    detail: str


class ProductPreflightReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    findings: tuple[SemanticFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    def require_pass(self) -> None:
        if self.findings:
            rendered = "; ".join(f"{item.code}:{item.path}:{item.detail}" for item in self.findings)
            raise ProductSemanticPreflightError(rendered)


def _module_name(path: str) -> str | None:
    pure = pathlib.PurePosixPath(path)
    if pure.suffix != ".py" or not pure.parts or pure.parts[0] != "backend":
        return None
    relative = list(pure.with_suffix("").parts[1:])
    if relative and relative[0] == "src":
        relative.pop(0)
    if relative and relative[-1] == "__init__":
        relative.pop()
    return ".".join(relative) if relative else None


def _module_aliases(path: str) -> tuple[str, ...]:
    short = _module_name(path)
    if short is None:
        return ()
    qualified = pathlib.PurePosixPath(path).with_suffix("")
    parts = list(qualified.parts)
    if parts[-1] == "__init__":
        parts.pop()
    full = ".".join(parts)
    return tuple(dict.fromkeys((short, full)))


def _exports(source: str) -> set[str]:
    tree = ast.parse(source)
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets.extend(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets.append(node.target)
        names.update(target.id for target in targets if isinstance(target, ast.Name))
    return names


def _python_modules(
    files: Mapping[str, str], findings: list[SemanticFinding]
) -> dict[str, tuple[str, set[str]]]:
    modules: dict[str, tuple[str, set[str]]] = {}
    for path, source in files.items():
        aliases = _module_aliases(path)
        if not aliases:
            continue
        try:
            exported = _exports(source)
            for alias in aliases:
                modules[alias] = (path, exported)
        except SyntaxError as error:
            findings.append(
                SemanticFinding(
                    code="python_syntax", path=path, detail=f"line {error.lineno}: {error.msg}"
                )
            )
    return modules


def _import_findings(
    path: str,
    tree: ast.AST,
    modules: Mapping[str, tuple[str, set[str]]],
    dependencies: frozenset[str],
) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for node in _nonstdlib_from_imports(tree):
        assert node.module is not None
        if node.module.split(".", 1)[0].lower() in dependencies:
            continue
        target = modules.get(node.module)
        if target is None:
            findings.append(
                SemanticFinding(
                    code="missing_local_module",
                    path=path,
                    detail=f"test imports unavailable module {node.module!r}",
                )
            )
            continue
        missing = sorted(
            alias.name for alias in node.names if alias.name != "*" and alias.name not in target[1]
        )
        if missing:
            findings.append(
                SemanticFinding(
                    code="missing_imported_symbols",
                    path=target[0],
                    detail=f"test requires {missing!r} from {node.module!r}",
                )
            )
    return findings


def _nonstdlib_from_imports(tree: ast.AST) -> tuple[ast.ImportFrom, ...]:
    return tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and not node.level
        and node.module not in sys.stdlib_module_names
    )


def _has_assertion(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            return True
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr.startswith("assert")
        ):
            return True
    return False


def _test_findings(
    files: Mapping[str, str], modules: Mapping[str, tuple[str, set[str]]]
) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    dependencies = _declared_dependencies(files)
    for path, source in files.items():
        if not path.startswith("tests/") or not path.endswith(".py"):
            continue
        try:
            tree = ast.parse(source)
        except SyntaxError as error:
            findings.append(
                SemanticFinding(
                    code="test_syntax", path=path, detail=f"line {error.lineno}: {error.msg}"
                )
            )
            continue
        has_test = any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test")
            for node in ast.walk(tree)
        )
        if not has_test or not _has_assertion(tree):
            findings.append(
                SemanticFinding(
                    code="vacuous_tests",
                    path=path,
                    detail="Python test files require a test function and an assertion",
                )
            )
        findings.extend(_import_findings(path, tree, modules, dependencies))
    return findings


def _declared_dependencies(files: Mapping[str, str]) -> frozenset[str]:
    names: set[str] = set()
    requirements = files.get("backend/requirements.txt", "")
    for line in requirements.splitlines():
        declared = line.split("#", 1)[0].strip()
        if not declared or declared.startswith(("-", ".")):
            continue
        name = declared.split("[", 1)[0]
        for marker in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            name = name.split(marker, 1)[0]
        names.add(name.strip().replace("-", "_").lower())
    return frozenset(names)


def _manifest_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    stdlib = sorted(_declared_dependencies(files) & sys.stdlib_module_names)
    if stdlib:
        findings.append(
            SemanticFinding(
                code="stdlib_dependency",
                path="backend/requirements.txt",
                detail=f"standard-library modules are not installable packages: {stdlib!r}",
            )
        )
    package = files.get("frontend/package.json", "")
    if "react-scripts" in package and "frontend/public/index.html" not in files:
        findings.append(
            SemanticFinding(
                code="missing_frontend_entry",
                path="frontend/public/index.html",
                detail="react-scripts requires a public HTML entry document",
            )
        )
    return findings


def _persistence_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    backend_text = "\n".join(
        source.lower()
        for path, source in files.items()
        if path.startswith("backend/") and path.endswith(".py")
    )
    uses_sqlite = "sqlite3" in backend_text or "sqlite://" in backend_text
    creates_schema = "create table" in backend_text or "create_all(" in backend_text
    findings: list[SemanticFinding] = []
    if not uses_sqlite:
        findings.append(
            SemanticFinding(
                code="missing_persistence_code",
                path="backend/",
                detail="backend Python source contains no executable SQLite persistence",
            )
        )
    elif not creates_schema:
        findings.append(
            SemanticFinding(
                code="missing_schema_bootstrap",
                path="backend/",
                detail="SQLite is selected but no schema creation or migration is present",
            )
        )
    if not any(marker in backend_text for marker in ("@app.route", "@router.", "add_url_rule")):
        findings.append(
            SemanticFinding(
                code="missing_api_routes",
                path="backend/",
                detail="backend source declares no HTTP API route",
            )
        )
    return findings


def _regression_findings(
    files: Mapping[str, str], baseline: Mapping[str, str] | None
) -> list[SemanticFinding]:
    findings: list[SemanticFinding] = []
    for path, original in (baseline or {}).items():
        if _module_name(path) is None or path not in files:
            continue
        try:
            removed = sorted(_exports(original) - _exports(files[path]))
        except SyntaxError:
            continue
        if removed:
            findings.append(
                SemanticFinding(
                    code="removed_parent_symbols",
                    path=path,
                    detail=f"candidate removed existing symbols {removed!r}",
                )
            )
    return findings


def inspect_product_files(
    files: Mapping[str, str], *, baseline: Mapping[str, str] | None = None
) -> ProductPreflightReport:
    """Inspect model bytes before they can be promoted as a viable revision."""
    findings: list[SemanticFinding] = []
    modules = _python_modules(files, findings)
    findings.extend(_test_findings(files, modules))
    findings.extend(_persistence_findings(files))
    findings.extend(_manifest_findings(files))
    findings.extend(_regression_findings(files, baseline))
    return ProductPreflightReport(findings=tuple(findings))


__all__ = ["ProductPreflightReport", "SemanticFinding", "inspect_product_files"]
