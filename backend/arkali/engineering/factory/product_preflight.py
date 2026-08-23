"""Domain-independent semantic preflight for generated product candidates.

Owner: ``engineering.factory`` (strict model-output validation).  The check
compares a candidate only with its own tests and optional parent revision.  It
contains no Golden-family names and renders no acceptance verdict.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from arkali.engineering.factory.dependency_resolution import (
    _DependencyResolutionOutcome,
    _missing_compatibility_cap_findings,
    _offline_dependency_compatibility_findings,
    _resolve_backend_dependency_contract,
)
from arkali.engineering.factory.errors import ProductSemanticPreflightError
from arkali.engineering.factory.semantic_finding import SemanticFinding


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
    from arkali.engineering.factory.test_contract_preflight import plain_import_findings

    findings.extend(plain_import_findings(path, tree, modules, dependencies))
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
                    detail=f"{path} imports unavailable module {node.module!r}",
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
                    detail=f"{path} requires {missing!r} from {node.module!r}",
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
        from arkali.engineering.factory.test_contract_preflight import (
            fixture_findings,
            _undefined_call_findings,
        )

        findings.extend(fixture_findings(path, tree))
        findings.extend(_undefined_call_findings(path, tree))
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


def _dependency_compatibility_findings(requirements: str) -> list[SemanticFinding]:
    """General, real dependency-compatibility ground truth: `pip`'s own
    resolver (`_resolve_backend_dependency_contract`) is the primary
    check, since it generalizes to any package the model declares, not
    just the pairs this repository happens to have hardcoded. It runs
    alongside, never instead of, `_missing_compatibility_cap_findings` —
    a real, verified, narrower class of gap (an under-declared upper
    bound in a package's own published metadata) that a metadata-only
    resolver can never see (see `dependency_resolution`'s module
    docstring). Only when the resolver itself is genuinely unavailable
    does this fall back entirely to `_offline_dependency_compatibility_
    findings`'s fuller table — never a silent pass on an unavailable
    toolchain."""
    lowered = requirements.lower().replace("-", "_")
    findings: list[SemanticFinding] = []
    result = _resolve_backend_dependency_contract(requirements)
    if result.outcome is _DependencyResolutionOutcome.NOT_CONFIGURED:
        offline = _offline_dependency_compatibility_findings(lowered)
    else:
        if result.outcome is _DependencyResolutionOutcome.CONFLICT:
            findings.append(
                SemanticFinding(
                    code="incompatible_dependency_range",
                    path="backend/requirements.txt",
                    detail=result.detail,
                )
            )
        offline = _missing_compatibility_cap_findings(lowered)
    findings.extend(
        SemanticFinding(code=code, path=path, detail=detail) for code, path, detail in offline
    )
    findings.extend(_target_runtime_findings(lowered))
    return findings


def _target_runtime_findings(requirements: str) -> list[SemanticFinding]:
    httpx_match = re.search(r"(?m)^httpx\s*==\s*(\d+)\.(\d+)", requirements)
    if sys.version_info < (3, 13) or httpx_match is None:
        return []
    if tuple(map(int, httpx_match.groups())) >= (0, 27):
        return []
    return [
        SemanticFinding(
            code="target_runtime_dependency_incompatible",
            path="backend/requirements.txt",
            detail="HTTPX before 0.27 imports cgi, which Python 3.13 removed",
        )
    ]


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
    findings.extend(
        _dependency_compatibility_findings(files.get("backend/requirements.txt", ""))
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
    # golden-work-079 (session evidence, frozen): checked here, not only in
    # `_manifests_stage_findings`, because `manifests`' own real context
    # (`manifest_context._manifest_context`) deliberately strips
    # `frontend/src/*` down to an extracted import-name list -- never full
    # file text -- so a check that needs to see a real `Switch` import
    # (not just that `react-router-dom` was imported at all) is
    # structurally blind by the time `manifests` runs. `frontend_tests_
    # config` (this function's other, unreduced caller) sees full
    # `frontend/src/*` text and runs first, so this fires there for real
    # instead of silently never firing.
    from arkali.engineering.factory.frontend_manifest_preflight import (
        _react_router_version_mismatch_findings,
    )
    findings.extend(_react_router_version_mismatch_findings(files))
    return findings


def _manifests_stage_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    """`manifests`'s own rule: `_manifest_findings` plus `config/README.md`
    — the one thing only `manifests`, never `frontend_tests_config` (which
    runs first and reuses `_manifest_findings` unchanged), is responsible
    for. golden-work-048 (session evidence, frozen): no stage's validator
    had ever required it, so the whole-product gate's required_roots check
    caught the absence first, instead of the stage that owns it."""
    findings = list(_manifest_findings(files))
    if not files.get("config/README.md", "").strip():
        findings.append(SemanticFinding(
            code="missing_startup_documentation", path="config/README.md",
            detail="no stage ever wrote config/README.md with real startup steps",
        ))
    from arkali.engineering.factory.frontend_manifest_preflight import (
        _missing_frontend_scripts_findings,
    )
    findings.extend(_missing_frontend_scripts_findings(files))
    return findings


def _schema_context_findings(backend_text: str) -> list[SemanticFinding]:
    if "flask_sqlalchemy" not in backend_text or "create_all(" not in backend_text:
        return []
    if "app_context()" in backend_text or "create_all(app=" in backend_text:
        return []
    return [
        SemanticFinding(
            code="schema_bootstrap_outside_app_context",
            path="backend/",
            detail="Flask-SQLAlchemy schema bootstrap requires an application context",
        )
    ]


def _framework_api_findings(files: Mapping[str, str]) -> list[SemanticFinding]:
    requirements = files.get("backend/requirements.txt", "").lower()
    flask_match = re.search(r"(?m)^flask\s*==\s*(\d+)", requirements)
    backend = "\n".join(
        source.lower()
        for path, source in files.items()
        if path.startswith("backend/") and path.endswith(".py")
    )
    if flask_match and int(flask_match.group(1)) >= 3 and "before_first_request" in backend:
        return [
            SemanticFinding(
                code="removed_framework_api",
                path="backend/",
                detail="Flask 3 removed the before_first_request hook",
            )
        ]
    return []


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
    findings.extend(_schema_context_findings(backend_text))
    route_markers = (
        "@app.route",
        "@app.get",
        "@app.post",
        "@app.put",
        "@app.delete",
        "@router.",
        "add_url_rule",
    )
    if not any(marker in backend_text for marker in route_markers):
        findings.append(
            SemanticFinding(
                code="missing_api_routes",
                path="backend/",
                detail="backend source declares no HTTP API route",
            )
        )
    has_top_level_app = bool(re.search(r"(?m)^app\s*=", backend_text))
    has_run = ".run(" in backend_text
    if not has_run and not has_top_level_app:
        findings.append(
            SemanticFinding(
                code="missing_backend_entrypoint",
                path="backend/",
                detail="backend has no executable server entrypoint",
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
    from arkali.engineering.factory.test_contract_preflight import lifecycle_findings

    findings.extend(lifecycle_findings(files))
    findings.extend(_persistence_findings(files))
    from arkali.engineering.factory.backend_import_preflight import _backend_import_findings

    findings.extend(_backend_import_findings(files, modules))
    findings.extend(_framework_api_findings(files))
    from arkali.engineering.factory.http_contract_preflight import (
        frontend_contract_findings,
    )

    findings.extend(frontend_contract_findings(files))
    from arkali.engineering.factory.frontend_ux_preflight import (
        _unreachable_module_findings,
        _ux_spec_mutation_findings,
        _ux_spec_shell_findings,
    )

    findings.extend(_unreachable_module_findings(files))
    findings.extend(_ux_spec_shell_findings(files))
    findings.extend(_ux_spec_mutation_findings(files))
    findings.extend(_manifest_findings(files))
    from arkali.engineering.factory.regression_preflight import _regression_findings

    findings.extend(_regression_findings(files, baseline))
    return ProductPreflightReport(findings=tuple(findings))


__all__ = ["ProductPreflightReport", "SemanticFinding", "inspect_product_files"]
