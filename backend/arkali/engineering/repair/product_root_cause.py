"""Mechanical root-cause evidence for a generated Python product defect.

Owner: ``engineering.repair``. This analyzer decides no repair and mutates no
candidate. It compares the failing test's import contract with the generated
backend's real AST/path and records independent schema-bootstrap evidence for
the existing C-26 fingerprint and failure-protocol pipeline.
"""

from __future__ import annotations

import ast
import hashlib

from pydantic import BaseModel, ConfigDict


class ProductRootCause(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    failure_signature: str
    root_cause_classes: tuple[str, ...]
    imported_module: str | None
    backend_module: str
    expected_exports: tuple[str, ...]
    actual_exports: tuple[str, ...]
    missing_exports: tuple[str, ...]
    uses_sqlite: bool
    creates_schema: bool

    @property
    def primary_class(self) -> str:
        return self.root_cause_classes[0]


def _test_contract(tree: ast.AST) -> tuple[str | None, set[str]]:
    imported_module: str | None = None
    expected: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_module = imported_module or node.module
            expected.update(alias.name for alias in node.names if alias.name != "*")
    return imported_module, expected


def _backend_exports(tree: ast.Module) -> set[str]:
    exports = {
        node.name for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    exports.update(
        target.id for node in tree.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name)
    )
    return exports


def _classify(
    imported_module: str | None, backend_module: str, missing: set[str],
    uses_sqlite: bool, creates_schema: bool,
) -> tuple[str, ...]:
    classes: list[str] = []
    if imported_module is not None and imported_module != backend_module:
        classes.append("assembly_import_path_defect")
    if missing:
        classes.append("generated_test_backend_contract_drift")
    if uses_sqlite and not creates_schema:
        classes.append("schema_runtime_mismatch")
    return tuple(classes or ["unclassified_runtime_failure"])


def analyze_python_product_failure(
    backend_path: str, backend_source: str, test_source: str, failure_output: str,
) -> ProductRootCause:
    backend_tree = ast.parse(backend_source)
    test_tree = ast.parse(test_source)
    backend_module = backend_path.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".py")
    imported_module, expected = _test_contract(test_tree)
    actual = _backend_exports(backend_tree)
    missing = expected - actual
    lowered = backend_source.lower()
    uses_sqlite = "sqlite3" in lowered or "sqlite://" in lowered
    creates_schema = "create table" in lowered or "create_all(" in lowered
    classes = _classify(
        imported_module, backend_module, missing, uses_sqlite, creates_schema
    )
    signature = hashlib.sha256(failure_output.encode("utf-8")).hexdigest()
    return ProductRootCause(
        failure_signature=f"sha256:{signature}",
        root_cause_classes=classes,
        imported_module=imported_module,
        backend_module=backend_module,
        expected_exports=tuple(sorted(expected)),
        actual_exports=tuple(sorted(actual)),
        missing_exports=tuple(sorted(missing)),
        uses_sqlite=uses_sqlite,
        creates_schema=creates_schema,
    )


__all__ = ["ProductRootCause", "analyze_python_product_failure"]
