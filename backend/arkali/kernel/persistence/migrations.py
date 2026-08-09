"""C-03 migration runner (ARCHITECTURE.md section 10).

Owner: kernel.persistence. Implementation phase 5.

THE MIGRATION CONTRACT IS NOT REDEFINED HERE. `schema_contract.MigrationContract`
was fixed at Phase 2 and this module only instantiates it, one instance per
Alembic revision, read from the revision files themselves. A migration whose
declared identity disagrees with its filename, or whose chain is not linear and
forward-only, is refused rather than run.

REVISION STATE HAS ONE STORE. Which revision is applied is read from Alembic's
own `alembic_version` table. Nothing here keeps a second copy.

HUMAN GATE 6 IS NOT ENFORCED HERE. `MigrationContract` carries
`requires_human_gate_6_on_real_data`, and the operation class `APPLY_MIGRATION`
is fixed to `HUMAN_GATE_6_ON_REAL_OR_STABLE_DATA` in the authority map. Both are
policy decisions owned by `control.policy` at layer rank 1, unreachable from
rank 0. The flag is carried and surfaced; the decision belongs to the call site.
The nine-step migration safety sequence is ARK-REQ-0151 at Phase 20 and is not
implemented here.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

from sqlalchemy import Engine, inspect, text

from arkali.kernel.persistence.schema_contract import (
    MigrationContract,
    MigrationDirection,
)

#: Paths relative to `backend/`. Declared once; the controls read them from here.
ALEMBIC_INI: Final[str] = "alembic.ini"
VERSIONS_DIR: Final[str] = "alembic/versions"

#: Alembic's own applied-revision table. Read, never written by this module.
ALEMBIC_VERSION_TABLE: Final[str] = "alembic_version"

_DECLARED: Final[tuple[str, ...]] = ("revision", "down_revision", "direction")


def _literals(source: str) -> dict[str, object]:
    """Module-level literal assignments, read without importing the module."""
    found: dict[str, object] = {}
    for node in ast.parse(source).body:
        target: str
        value: ast.expr | None
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        else:
            continue
        if target not in _DECLARED or value is None:
            continue
        try:
            found[target] = ast.literal_eval(value)
        except ValueError:
            continue
    return found


def contract_of(path: pathlib.Path) -> MigrationContract:
    """The `MigrationContract` a revision file declares.

    Fails closed: a file missing `revision` or `direction`, or declaring a
    revision that disagrees with its own filename, is refused. A migration the
    runner cannot identify must not be applied.
    """
    declared = _literals(path.read_text(encoding="utf-8"))
    missing = [key for key in ("revision", "direction") if key not in declared]
    if missing:
        raise ValueError(f"{path.name} declares no {missing}")
    revision = str(declared["revision"])
    if path.stem != revision:
        raise ValueError(
            f"{path.name} declares revision {revision!r}; filename and revision "
            "must agree so a migration cannot be identified two ways"
        )
    down = declared.get("down_revision")
    return MigrationContract(
        revision=revision,
        down_revision=None if down is None else str(down),
        direction=MigrationDirection(str(declared["direction"])),
    )


def declared_migrations(backend_root: pathlib.Path) -> tuple[MigrationContract, ...]:
    """Every declared migration, ordered from root to head."""
    versions = backend_root / VERSIONS_DIR
    if not versions.is_dir():
        raise FileNotFoundError(f"no migrations directory at {versions}")
    contracts = [contract_of(p) for p in sorted(versions.glob("*.py"))
                 if p.name != "__init__.py"]
    return tuple(_ordered(contracts))


def _ordered(contracts: list[MigrationContract]) -> list[MigrationContract]:
    """Order the chain from its single root, refusing anything not linear."""
    if not contracts:
        return []
    roots = [c for c in contracts if c.down_revision is None]
    if len(roots) != 1:
        raise ValueError(
            f"migration chain must have exactly one root; found {len(roots)}"
        )
    by_parent: dict[str | None, list[MigrationContract]] = {}
    for contract in contracts:
        by_parent.setdefault(contract.down_revision, []).append(contract)
    chain = [roots[0]]
    while True:
        children = by_parent.get(chain[-1].revision, [])
        if not children:
            break
        if len(children) > 1:
            raise ValueError(
                f"revision {chain[-1].revision!r} has {len(children)} successors; "
                "a branched chain has no single head"
            )
        chain.append(children[0])
    if len(chain) != len(contracts):
        raise ValueError("migration chain is not connected; some revision is orphaned")
    return chain


def head_revision(backend_root: pathlib.Path) -> str:
    """The revision at the end of the declared chain."""
    chain = declared_migrations(backend_root)
    if not chain:
        raise ValueError("no migrations are declared; there is no head")
    return chain[-1].revision


def applied_revision(engine: Engine) -> str | None:
    """The revision Alembic records as applied, or None if never migrated."""
    if not inspect(engine).has_table(ALEMBIC_VERSION_TABLE):
        return None
    with engine.connect() as connection:
        result = connection.execute(
            text(f"SELECT version_num FROM {ALEMBIC_VERSION_TABLE}")  # noqa: S608
        ).scalars().all()
    return None if not result else str(result[0])


def is_forward_only(chain: tuple[MigrationContract, ...]) -> bool:
    """ARCHITECTURE section 10: migrations are forward-only.

    A `ROLLBACK_POINT` is a recorded marker, not a reverse migration, so it is a
    legal member of a forward-only chain. Any other direction is not.
    """
    legal = {MigrationDirection.FORWARD, MigrationDirection.ROLLBACK_POINT}
    return all(contract.direction in legal for contract in chain)
