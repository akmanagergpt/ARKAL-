"""C-03 migration impact analysis (ARK-REQ-0151 step 1, ARK-REQ-0337).

Owner: kernel.persistence. Implementation phase 20.

MECHANICS ONLY. This module answers one narrow, structural question about a
migration revision file: does its `upgrade()` body call an Alembic operation
that irreversibly removes a stored column or table. It does not decide what
happens with that answer - refusing to apply, blocking a phase, blocking a
release are all `lifecycle.recovery` and `acceptance.engine` decisions, kept
out of this module the same way `backup.py` moves bytes but never decides a
backup is verified.

WHY AST, NOT IMPORT. `migrations.py` already reads a revision's declared
identity by parsing its module-level literals rather than importing it, so
that a malformed or side-effecting file is inspected without running it. This
module keeps that discipline: `upgrade()` is parsed, never executed, so
analysing a candidate migration cannot itself mutate any database.

WHAT COUNTS AS A KNOWN DATA-LOSS RISK. `op.drop_table`, `op.drop_column` and a
raw `op.execute("DROP ...")` unconditionally destroy stored data with no
declared recovery inside the migration itself - ARCHITECTURE.md section 10
requires the chain to be forward-only with a *recorded rollback point*, not
that every forward step be non-destructive, so a real destructive step is a
legitimate thing to write and an equally legitimate thing to flag. Renaming,
adding, or narrowing a column's nullability are not treated as data-loss here:
none of them discard stored values by themselves, and inventing a heuristic
for "narrowing" without a prior schema to compare against would be a guess,
not a derivation.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

from pydantic import BaseModel, ConfigDict

#: Alembic operation-builder attribute names that discard stored data
#: unconditionally when called. Read off `op.<name>(...)` call sites only.
_DESTRUCTIVE_OPS: Final[frozenset[str]] = frozenset({"drop_table", "drop_column"})

#: A raw-SQL escape hatch. Matched case-insensitively against the leading
#: keyword of a string literal passed to `op.execute(...)`.
_DESTRUCTIVE_SQL_PREFIXES: Final[tuple[str, ...]] = ("drop ", "truncate ")


class MigrationImpactReport(BaseModel):
    """The impact analysis for one migration revision. Never partial."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: str
    data_loss_risk: bool
    reasons: tuple[str, ...] = ()

    def render(self) -> str:
        if not self.data_loss_risk:
            return f"{self.revision}: no known data-loss risk"
        return f"{self.revision}: data-loss risk - {'; '.join(self.reasons)}"


def _upgrade_function(tree: ast.Module) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    return None


def _call_target_name(call: ast.Call) -> str | None:
    """The dotted attribute name of a call, e.g. `op.drop_table` -> `drop_table`."""
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _sql_literal(call: ast.Call) -> str | None:
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _reasons_in(node: ast.AST) -> list[str]:
    reasons: list[str] = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        name = _call_target_name(call)
        if name in _DESTRUCTIVE_OPS:
            reasons.append(f"op.{name} at line {call.lineno}")
            continue
        if name == "execute":
            literal = _sql_literal(call)
            if literal is not None:
                lowered = literal.strip().lower()
                if lowered.startswith(_DESTRUCTIVE_SQL_PREFIXES):
                    reasons.append(f"op.execute({literal.strip()!r}) at line {call.lineno}")
    return reasons


def analyze_revision(revision: str, source: str) -> MigrationImpactReport:
    """The impact report for one revision's already-read source text.

    Refuses nothing: a revision with no `upgrade()` function carries no
    detectable risk under this analysis rather than being treated as an error,
    since malformed-migration refusal is `migrations.py`'s job, not this one's.
    """
    tree = ast.parse(source)
    upgrade = _upgrade_function(tree)
    reasons = tuple(_reasons_in(upgrade)) if upgrade is not None else ()
    return MigrationImpactReport(
        revision=revision, data_loss_risk=bool(reasons), reasons=reasons
    )


def analyze_file(path: pathlib.Path) -> MigrationImpactReport:
    """The impact report for one revision file on disk."""
    return analyze_revision(path.stem, path.read_text(encoding="utf-8"))


def analyze_chain(versions_dir: pathlib.Path) -> tuple[MigrationImpactReport, ...]:
    """The impact report for every declared revision in a versions directory.

    Ordered by filename, matching `migrations.declared_migrations`'s own glob
    order; this module does not re-derive chain order or linearity, which is
    that module's responsibility.
    """
    if not versions_dir.is_dir():
        raise FileNotFoundError(f"no migrations directory at {versions_dir}")
    return tuple(
        analyze_file(p) for p in sorted(versions_dir.glob("*.py"))
        if p.name != "__init__.py"
    )
