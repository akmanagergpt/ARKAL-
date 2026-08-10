"""Shared reader for the C-21 `execution.scheduler` authority controls.

Not a test module. It exists because `module <= 400 logical lines` is a real
architecture budget and ADR-0008 makes decomposition the answer rather than an
exception; it follows the `durable_reader.py` and `typescript_reader.py`
precedents in this directory.

Everything here reads the DEPLOYED SOURCE with `ast`, so prose cannot satisfy a
check. Subjects are DERIVED - the module set, the declaration fields, the
canonical vocabularies and the documented tables are all read at call time, so a
module, field or class added later is covered without editing a control. That is
the F-0032 lesson: a transcribed subject goes stale silently.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE: Final[pathlib.Path] = REPO / "backend" / "arkali"
SCHEDULER: Final[pathlib.Path] = PACKAGE / "execution" / "scheduler"
DURABLE: Final[pathlib.Path] = PACKAGE / "execution" / "durable"
CONTRACT_DOC: Final[pathlib.Path] = REPO / "docs" / "contracts" / "worker.md"
MIGRATIONS: Final[pathlib.Path] = REPO / "backend" / "alembic" / "versions"

#: Names that would mean this context had started building persistence.
ENGINE_CONSTRUCTORS: Final[tuple[str, ...]] = (
    "create_engine", "create_async_engine", "sessionmaker",
    "async_sessionmaker", "declarative_base", "create_persistence_engine",
    "create_session_factory", "unit_of_work",
)
#: Anything that would mean raw or dialect-specific SQL had appeared.
RAW_SQL: Final[tuple[str, ...]] = (
    r"\btext\s*\(", r"\bexecute\s*\(\s*[\"']", r"\bPRAGMA\b", r"\bsqlite3\b",
    r"\bpsycopg", r"sqlalchemy",
)
#: Vocabulary that would mean a state machine or transition table had appeared.
MACHINE_NAMES: Final[tuple[str, ...]] = (
    "state_machine", "StateMachine", "transition", "Transition",
    "TransitionOutcome", "lifecycle_state", "terminal_state", "forbidden_pair",
)
#: Package 2 and later behaviour. Present here would mean scope had run ahead.
ADMISSION_NAMES: Final[tuple[str, ...]] = (
    "admit", "admission", "allocate", "dispatch", "claim", "lease",
    "dequeue", "enqueue", "can_perform", "capability_state",
)
#: Concepts the canonical set does not give Phase 8 at all.
FORWARD_NAMES: Final[tuple[str, ...]] = (
    "priority", "fairness", "autoscal", "queue", "worker_pool", "backlog",
    "kubernetes", "consensus", "broker", "failure_domain",
)
#: C-19 concerns this context must never name.
DURABLE_NAMES: Final[tuple[str, ...]] = (
    "lifecycle_state", "idempotency", "checkpoint", "dead_letter",
    "retry_budget", "max_attempts", "deadline_at", "heartbeat_at",
    "resume", "recoverable", "attempt",
)
#: The PEP's decision methods, matched on the RECEIVER too - naming the class
#: proves nothing, because a module can import a type and never ask it anything.
PEP_DECISION_CALLS: Final[tuple[str, ...]] = ("require_auto", "enforce", "evaluate")


def modules(root: pathlib.Path) -> list[pathlib.Path]:
    found = sorted(p for p in root.rglob("*.py") if p.name != "__init__.py")
    assert found, f"no module under {root}; this control would be vacuous"
    return found


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def code_only(text: str) -> str:
    """Source with docstrings and comments removed."""
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                text = text.replace(doc, "")
    return re.sub(r"#[^\n]*", "", text)


def imported(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def called(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def takes_a_policy_decision(path: pathlib.Path) -> bool:
    """Whether this module CALLS a decision method ON a PEP.

    The receiver is checked as well as the method name, because `evaluate`
    belongs to other objects too - the same trap `test_pep_and_bypass` records.
    """
    for node in ast.walk(ast.parse(read(path))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in PEP_DECISION_CALLS:
            continue
        if "pep" in ast.unparse(node.func.value).lower():
            return True
    return False


def declared_names(path: pathlib.Path) -> set[str]:
    """Every identifier this module DEFINES or CALLS.

    The subject for vocabulary checks is the mechanism, not the prose. An
    earlier draft matched raw source text and fired on the word "admitting"
    inside a refusal message - a control that cannot tell a sentence from a
    method is measuring the wrong thing.
    """
    tree = ast.parse(read(path))
    found: set[str] = set(called(tree))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found.add(node.name)
        elif isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.arg):
            found.add(node.arg)
    return found


def creates_table_named(path: pathlib.Path, needle: str) -> bool:
    """Whether a migration creates or alters a table whose name matches.

    The subject is the schema the migration builds, not its prose: `0007`
    explains that "a worker can fall silent", which is commentary about C-19
    and not a scheduler table.
    """
    for node in ast.walk(ast.parse(read(path))):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if not node.func.attr.endswith(("_table", "_column", "_index")):
            continue
        for argument in node.args:
            if (
                isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
                and needle in argument.value.lower()
            ):
                return True
    return False


def string_constants(path: pathlib.Path) -> set[str]:
    """Every string literal in a module, for vocabulary-leak checks."""
    return {
        node.value
        for node in ast.walk(ast.parse(read(path)))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def documented_dimensions() -> dict[str, str]:
    """The §2 dimension table, as canonical dimension -> field name.

    Parsed from the shipping document, so the document cannot drift from the
    code without a control seeing it.
    """
    rows = re.findall(
        r"^\|\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|", read(CONTRACT_DOC), re.M
    )
    found = {dimension: field for dimension, field in rows if "_" in field}
    assert found, "no dimension table parsed from the C-21 document"
    return found


def documented_classes() -> tuple[str, ...]:
    """The §3 worker-class table, parsed from the shipping document."""
    section = read(CONTRACT_DOC).split("## 3.")[1].split("\n## ")[0]
    found = tuple(re.findall(r"^\|\s*`([^`]+)`\s*\|\s*$", section, re.M))
    assert found, "no worker-class table parsed from the C-21 document"
    return found
