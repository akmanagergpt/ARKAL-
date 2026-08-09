"""Shared reader for the C-19 `execution.durable` authority controls.

Not a test module. It exists because `module <= 400 logical lines` is a real
architecture budget and ADR-0008 makes decomposition the answer rather than an
exception; it follows the `typescript_reader.py` precedent in this directory.

Everything here reads the DEPLOYED SOURCE with `ast`, so prose cannot satisfy a
check.
"""

from __future__ import annotations

import ast
import pathlib
import re
from typing import Final

from arkali.execution.durable.job_state_machine import DEFINITION
from arkali.execution.durable.job_store import READ, WRITE, JobStore
from arkali.execution.durable.records import (
    DurableJobRecord,
    JobCheckpointRecord,
    JobExecutionAttempt,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PACKAGE: Final[pathlib.Path] = REPO / "backend" / "arkali"
DURABLE: Final[pathlib.Path] = PACKAGE / "execution" / "durable"
MACHINE_MODULE: Final[str] = "job_state_machine.py"
CONTRACT_DOC: Final[pathlib.Path] = REPO / "docs" / "contracts" / "job.md"

#: Names that would mean this context had started building its own engine.
ENGINE_CONSTRUCTORS: Final[tuple[str, ...]] = (
    "create_engine", "create_async_engine", "sessionmaker",
    "async_sessionmaker", "declarative_base",
)
#: Anything that would mean raw or dialect-specific SQL had appeared.
RAW_SQL: Final[tuple[str, ...]] = (
    r"\btext\s*\(", r"\bexecute\s*\(\s*[\"']", r"\bPRAGMA\b", r"\bsqlite3\b",
    r"\bpsycopg", r"sqlalchemy\.dialects",
)
#: The two operation classes this context must never name (structure check 11).
STABLE_CLASSES: Final[tuple[str, ...]] = ("WRITE_STABLE_FILE", "ROLLBACK_STABLE")
#: Calls that actually operate on a session. Merely holding one is not an
#: operation and needs no decision; issuing one of these is.
SESSION_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"execute", "add", "flush", "delete", "merge", "add_all"}
)
#: Phase 8 vocabulary. Present here would mean scheduling had leaked forward.
SCHEDULING_NAMES: Final[tuple[str, ...]] = (
    "admit", "admission", "claim", "lease", "dequeue", "enqueue_to_worker",
    "worker_pool", "resource_budget", "allocate",
)


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


def called(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return names


def _assigns_lifecycle_state(node: ast.AST) -> bool:
    """Whether this function assigns the `lifecycle_state` attribute anywhere."""
    for inner in ast.walk(node):
        targets: list[ast.expr] = []
        if isinstance(inner, ast.Assign):
            targets = list(inner.targets)
        elif isinstance(inner, (ast.AugAssign, ast.AnnAssign)):
            targets = [inner.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and target.attr == "lifecycle_state":
                return True
    return False


def imported(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found
