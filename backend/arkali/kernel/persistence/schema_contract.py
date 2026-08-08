"""C-03 persistence base schema + migration contract - DEFINITION ONLY.

Owner: kernel.persistence. Definition phase 2, implementation phase 5
(CONTRACT_INVENTORY.md governing rule 7).

This module declares the shape every persisted entity and migration must honour.
It deliberately contains NO engine, NO session, NO ORM mapping and NO migration:
those are Phase 5 and would be a forward-phase implementation smuggled into
Phase 2. A validator check fails if `create_engine` or `declarative_base` appear.
"""

from __future__ import annotations

import enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class MigrationDirection(str, enum.Enum):
    FORWARD = "FORWARD"
    ROLLBACK_POINT = "ROLLBACK_POINT"


class PersistedEntityContract(BaseModel):
    """Fields every persisted entity must expose."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity: str
    owning_context: str
    primary_key: str
    immutable_fields: tuple[str, ...] = ()
    content_hashed: bool = False


class MigrationContract(BaseModel):
    """Shape of a migration. Phase 5 supplies instances; Phase 2 fixes the shape."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: str
    down_revision: str | None
    direction: MigrationDirection
    requires_backup: bool = True
    requires_human_gate_6_on_real_data: bool = True


@runtime_checkable
class SupportsRepository(Protocol):
    """Engine-neutral repository surface (ADR-0006).

    Declared so no engine-specific SQL leaks outside kernel.persistence. The
    PostgreSQL-ready abstraction requirement (ARK-REQ-0012) is MANDATORY and is
    satisfied by this neutrality, not by running PostgreSQL.
    """

    def get(self, key: str) -> object | None: ...

    def put(self, key: str, value: object) -> None: ...
