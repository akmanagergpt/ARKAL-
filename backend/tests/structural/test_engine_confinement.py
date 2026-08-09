"""ARK-REQ-0012 architecture control: no engine-specific SQL escapes its context.

ADR-0006 makes the abstraction property MANDATORY and says it is verified by
architecture test. This is that test.

WHY IT IS NOT A NINTH ARCHITECTURE GATE. The eight gates are declared in
`AUTHORITY_MAP.yaml`, and `GateRunner.reconcile` fails closed if the declared
set and the implemented set disagree. Adding a gate would therefore require
editing the canonical authority map, which is Phase 0B material that may not be
changed without an explicit human ruling. The control is delivered at the test
tier instead, which discharges the requirement without an implementing actor
amending canonical authority to make its own work pass.

The check parses real imports with `ast` and never matches identifiers by name
alone, because the authority map declares an identifier-only checker
insufficient (ARK-REQ-0352).
"""

from __future__ import annotations

import ast
import pathlib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
PACKAGE = REPO / "backend" / "arkali"

#: Distributions whose presence in a module means that module talks to a
#: database engine directly.
ENGINE_PACKAGES = frozenset({"sqlalchemy", "alembic", "sqlite3", "psycopg", "asyncpg"})

#: Callables that emit SQL supplied as a string rather than built from mapped
#: columns. Permitted only inside the owning context.
RAW_SQL_CALLS = frozenset({"text", "exec_driver_sql"})


def owning_context() -> str:
    """The context canonically responsible, read from the register, not named here."""
    import sys

    sys.path.insert(0, str(REPO / "backend"))
    from arkali.control.specification.register_parser import RequirementRegister

    return RequirementRegister.load(REPO).get("ARK-REQ-0012").owning_component


def module_root(context: str) -> pathlib.Path:
    raw = yaml.safe_load(
        (REPO / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
    )
    return REPO / raw["contexts"][context]["module_root"]


def modules() -> list[pathlib.Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def imported_distributions(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def raw_sql_callees(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = None
        if isinstance(node.func, ast.Name):
            name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            name = node.func.attr
        if name in RAW_SQL_CALLS:
            found.add(name)
    return found


@pytest.fixture(scope="module")
def persistence_root() -> pathlib.Path:
    return module_root(owning_context())


class TestEngineAccessIsConfined:
    def test_the_register_assigns_the_requirement_to_one_context(self) -> None:
        assert owning_context() == "kernel.persistence"

    def test_no_module_outside_the_owning_context_imports_a_database_package(
        self, persistence_root: pathlib.Path
    ) -> None:
        offenders = []
        for path in modules():
            if path.is_relative_to(persistence_root):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            leaked = imported_distributions(tree) & ENGINE_PACKAGES
            if leaked:
                offenders.append(f"{path.relative_to(REPO).as_posix()}: {sorted(leaked)}")
        assert offenders == []

    def test_no_module_outside_the_owning_context_emits_raw_sql(
        self, persistence_root: pathlib.Path
    ) -> None:
        offenders = []
        for path in modules():
            if path.is_relative_to(persistence_root):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            leaked = raw_sql_callees(tree)
            if leaked:
                offenders.append(f"{path.relative_to(REPO).as_posix()}: {sorted(leaked)}")
        assert offenders == []

    def test_the_owning_context_does_use_the_engine(
        self, persistence_root: pathlib.Path
    ) -> None:
        """NOT VACUOUS: the rule must have something real to confine.

        A pass over a context that imports no database package would prove
        nothing, which is the F-0008/F-0016 defect shape.
        """
        used: set[str] = set()
        for path in sorted(persistence_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            used |= imported_distributions(tree) & ENGINE_PACKAGES
        assert "sqlalchemy" in used


class TestDetectorRejectsAViolation:
    """NEGATIVE CONTROLS for the detector itself."""

    def test_an_engine_import_outside_the_context_is_detected(self) -> None:
        tree = ast.parse("from sqlalchemy import create_engine\n")
        assert imported_distributions(tree) & ENGINE_PACKAGES == {"sqlalchemy"}

    def test_a_driver_import_is_detected(self) -> None:
        tree = ast.parse("import psycopg\n")
        assert imported_distributions(tree) & ENGINE_PACKAGES == {"psycopg"}

    def test_raw_sql_is_detected_by_call_not_by_substring(self) -> None:
        assert raw_sql_callees(ast.parse('q = text("SELECT 1")\n')) == {"text"}
        assert raw_sql_callees(
            ast.parse('conn.exec_driver_sql("SELECT 1")\n')
        ) == {"exec_driver_sql"}

    def test_a_mention_in_a_string_is_not_a_violation(self) -> None:
        """A docstring naming `text` must not be flagged; only a call counts."""
        assert raw_sql_callees(ast.parse('S = "use text() only in persistence"\n')) == set()

    def test_ordinary_orm_free_code_is_clean(self) -> None:
        tree = ast.parse("import pathlib\nfrom typing import Any\n")
        assert imported_distributions(tree) & ENGINE_PACKAGES == set()
