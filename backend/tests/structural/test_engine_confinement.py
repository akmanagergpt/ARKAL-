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
from collections.abc import Callable

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[3]
PACKAGE = REPO / "backend" / "arkali"

#: WHAT THE CANONICAL RULE ACTUALLY SAYS. ARCHITECTURE.md section 10 forbids
#: "raw SQL outside `kernel.persistence`", and ADR-0006 registers "engine-neutral
#: repository interfaces; no engine-specific SQL outside `kernel.persistence`".
#: Neither forbids the ORM: ADR-0006 presupposes it, placing SQLite "behind
#: SQLAlchemy 2.x repositories".
#:
#: Defect F-0030. Package 1 banned the `sqlalchemy` import outright, which is
#: stricter than the requirement it claims to verify and would have refused
#: `control.registry.project` the declarative mapping ADR-0006 assumes - the
#: F-0027 shape again, in a control written to prevent it. The rule is restated
#: to the canonical property and strengthened where it was actually weak:
#: drivers and dialect modules are now named, and engine construction is
#: asserted here as well as by structure check 12.

#: DBAPI drivers and dialect-specific modules. A module importing one of these
#: has chosen an engine.
DRIVER_PACKAGES = frozenset({"sqlite3", "psycopg", "psycopg2", "asyncpg", "pysqlite2"})

#: Dotted module prefixes that name a specific engine.
DIALECT_PREFIXES = ("sqlalchemy.dialects", "sqlalchemy.ext.asyncio")

#: Callables that emit SQL supplied as a string rather than built from mapped
#: columns, or that construct an engine. Permitted only inside the owning context.
RAW_SQL_CALLS = frozenset({"text", "exec_driver_sql"})
ENGINE_CONSTRUCTION_CALLS = frozenset(
    {"create_engine", "create_async_engine", "sessionmaker", "async_sessionmaker",
     "declarative_base"}
)

#: The engine-neutral ORM surface every persisting context may use. Named so the
#: control can prove the rule permits it rather than merely not forbidding it.
NEUTRAL_ORM_NAMES = frozenset({"Mapped", "mapped_column", "select", "relationship"})


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


def imported_modules(tree: ast.Module) -> set[str]:
    """Every dotted module a file imports, at full depth."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
    return found


def engine_bound_imports(tree: ast.Module) -> set[str]:
    """Imports that choose a database engine: a driver or a dialect module."""
    found: set[str] = set()
    for module in imported_modules(tree):
        if module.split(".")[0] in DRIVER_PACKAGES:
            found.add(module)
        elif module.startswith(DIALECT_PREFIXES):
            found.add(module)
    return found


def _callee_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def raw_sql_callees(tree: ast.Module) -> set[str]:
    return _callee_names(tree) & RAW_SQL_CALLS


def engine_construction_callees(tree: ast.Module) -> set[str]:
    return _callee_names(tree) & ENGINE_CONSTRUCTION_CALLS


@pytest.fixture(scope="module")
def persistence_root() -> pathlib.Path:
    return module_root(owning_context())


class TestEngineAccessIsConfined:
    def test_the_register_assigns_the_requirement_to_one_context(self) -> None:
        assert owning_context() == "kernel.persistence"

    @staticmethod
    def _outside(
        persistence_root: pathlib.Path, detector: Callable[[ast.Module], set[str]]
    ) -> list[str]:
        offenders = []
        for path in modules():
            if path.is_relative_to(persistence_root):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            leaked = detector(tree)
            if leaked:
                offenders.append(f"{path.relative_to(REPO).as_posix()}: {sorted(leaked)}")
        return offenders

    def test_no_module_outside_the_owning_context_binds_to_an_engine(
        self, persistence_root: pathlib.Path
    ) -> None:
        assert self._outside(persistence_root, engine_bound_imports) == []

    def test_no_module_outside_the_owning_context_emits_raw_sql(
        self, persistence_root: pathlib.Path
    ) -> None:
        assert self._outside(persistence_root, raw_sql_callees) == []

    def test_no_module_outside_the_owning_context_constructs_an_engine(
        self, persistence_root: pathlib.Path
    ) -> None:
        assert self._outside(persistence_root, engine_construction_callees) == []

    def test_the_owning_context_does_construct_the_engine(
        self, persistence_root: pathlib.Path
    ) -> None:
        """NOT VACUOUS: the rule must have something real to confine.

        A pass over a context that builds no engine would prove nothing, which
        is the F-0008/F-0016 defect shape.
        """
        used: set[str] = set()
        for path in sorted(persistence_root.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            used |= engine_construction_callees(tree) | raw_sql_callees(tree)
        assert "create_engine" in used
        assert "text" in used

    def test_the_neutral_orm_is_permitted_outside_the_owning_context(self) -> None:
        """The rule confines the engine, not the ORM (ADR-0006, F-0030).

        C-12 maps its own tables in `control.registry.project`, which is what
        "SQLite behind SQLAlchemy repositories" means. A rule that forbade this
        would refuse the architecture it claims to protect.
        """
        registry = REPO / "backend/arkali/control/registry/project/records.py"
        tree = ast.parse(registry.read_text(encoding="utf-8"), filename=str(registry))
        imported = {n for module in imported_modules(tree) for n in [module]}
        assert any(m.startswith("sqlalchemy") for m in imported)
        assert engine_bound_imports(tree) == set()
        assert engine_construction_callees(tree) == set()
        assert raw_sql_callees(tree) == set()


class TestDetectorRejectsAViolation:
    """NEGATIVE CONTROLS for the detector itself."""

    def test_a_driver_import_is_detected(self) -> None:
        assert engine_bound_imports(ast.parse("import psycopg\n")) == {"psycopg"}
        assert engine_bound_imports(ast.parse("import sqlite3\n")) == {"sqlite3"}

    def test_a_dialect_import_is_detected(self) -> None:
        tree = ast.parse("from sqlalchemy.dialects.sqlite import insert\n")
        assert engine_bound_imports(tree) == {"sqlalchemy.dialects.sqlite"}

    def test_engine_construction_is_detected(self) -> None:
        assert engine_construction_callees(
            ast.parse('e = create_engine("sqlite://")\n')
        ) == {"create_engine"}
        assert engine_construction_callees(
            ast.parse("f = sessionmaker(bind=e)\n")
        ) == {"sessionmaker"}

    def test_raw_sql_is_detected_by_call_not_by_substring(self) -> None:
        assert raw_sql_callees(ast.parse('q = text("SELECT 1")\n')) == {"text"}
        assert raw_sql_callees(
            ast.parse('conn.exec_driver_sql("SELECT 1")\n')
        ) == {"exec_driver_sql"}

    def test_a_mention_in_a_string_is_not_a_violation(self) -> None:
        """A docstring naming `text` must not be flagged; only a call counts."""
        assert raw_sql_callees(ast.parse('S = "use text() only in persistence"\n')) == set()

    def test_the_neutral_orm_surface_is_not_flagged(self) -> None:
        """The restated rule must not re-forbid what ADR-0006 assumes."""
        tree = ast.parse(
            "from sqlalchemy import select\n"
            "from sqlalchemy.orm import Mapped, mapped_column, relationship\n"
            "rows = select(Thing)\n"
        )
        assert engine_bound_imports(tree) == set()
        assert engine_construction_callees(tree) == set()
        assert raw_sql_callees(tree) == set()
        assert NEUTRAL_ORM_NAMES & _callee_names(
            ast.parse("select(Thing)\nmapped_column()\n")
        ) != set()

    def test_ordinary_engine_free_code_is_clean(self) -> None:
        tree = ast.parse("import pathlib\nfrom typing import Any\n")
        assert engine_bound_imports(tree) == set()
