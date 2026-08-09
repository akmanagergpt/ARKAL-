"""C-03 persistence base schema.

Owner: kernel.persistence. Implementation phase 5.

WHAT THE BASE SCHEMA IS. `schema_contract.PersistedEntityContract` fixed, at
Phase 2, the fields every persisted entity must expose. This module is that
contract realised as storage: one table recording the registered contract of
every persisted entity, whose columns are derived from the Pydantic model rather
than restated. `test_persistence_foundation.py` reconciles the two, so the table
and the contract cannot drift into two descriptions of the same thing.

NO SECOND AUTHORITY OVER REVISIONS. Which migration has been applied is
Alembic's `alembic_version` table and is not mirrored here. Duplicating it would
create exactly the shadow store the authority map forbids.

ENGINE-NEUTRAL (ARK-REQ-0012). Column types are `String`, `Boolean` and `JSON`,
all of which SQLAlchemy renders for SQLite and PostgreSQL alike. The naming
convention is explicit so constraint names are deterministic and identical on
both engines - Alembic cannot autogenerate a stable downgrade without it.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import JSON, Boolean, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from arkali.kernel.persistence.schema_contract import PersistedEntityContract

#: Deterministic constraint names, identical across engines.
NAMING_CONVENTION: Final[dict[str, str]] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: The table holding the base schema. Named once, consumed by the migration.
ENTITY_CONTRACT_TABLE: Final[str] = "persisted_entity_contract"


class PersistenceBase(DeclarativeBase):
    """Declarative base for every ARKALI persisted entity."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class PersistedEntityRow(PersistenceBase):
    """Stored form of `PersistedEntityContract`.

    Every column corresponds to exactly one contract field. A field added to the
    contract without a column here is caught by the reconciliation control.
    """

    __tablename__ = ENTITY_CONTRACT_TABLE

    entity: Mapped[str] = mapped_column(String(200), primary_key=True)
    owning_context: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_key: Mapped[str] = mapped_column(String(200), nullable=False)
    immutable_fields: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list
    )
    content_hashed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    def to_contract(self) -> PersistedEntityContract:
        """The stored row read back as its Phase 2 contract."""
        return PersistedEntityContract(
            entity=self.entity,
            owning_context=self.owning_context,
            primary_key=self.primary_key,
            immutable_fields=tuple(self.immutable_fields or ()),
            content_hashed=self.content_hashed,
        )


def row_from_contract(contract: PersistedEntityContract) -> PersistedEntityRow:
    """A storable row for a declared contract. The contract stays authoritative."""
    return PersistedEntityRow(
        entity=contract.entity,
        owning_context=contract.owning_context,
        primary_key=contract.primary_key,
        immutable_fields=list(contract.immutable_fields),
        content_hashed=contract.content_hashed,
    )


def contract_field_names() -> tuple[str, ...]:
    """The contract's own field names, read from the model, never listed here."""
    return tuple(PersistedEntityContract.model_fields)


def stored_column_names() -> tuple[str, ...]:
    """The base-schema column names, read from the mapped table."""
    return tuple(c.name for c in PersistedEntityRow.__table__.columns)
