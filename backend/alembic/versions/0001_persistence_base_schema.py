"""C-03 base schema: the persisted-entity contract table.

Revision: 0001_persistence_base_schema
Parent:   none (root of the chain)

Creates the storage form of `PersistedEntityContract`, which Phase 2 defined and
Phase 5 realises. Column names and types are taken from the mapped model in
`arkali.kernel.persistence.base`, so this revision and the ORM cannot describe
the same table differently.

Forward-only per ARCHITECTURE.md section 10. `downgrade` drops what `upgrade`
created and exists so the revision is reversible in development; it is not a
migration-safety mechanism, which is ARK-REQ-0151 at Phase 20.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001_persistence_base_schema"
down_revision: str | None = None
branch_labels = None
depends_on = None
direction: str = "FORWARD"

TABLE = "persisted_entity_contract"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("entity", sa.String(length=200), nullable=False),
        sa.Column("owning_context", sa.String(length=200), nullable=False),
        sa.Column("primary_key", sa.String(length=200), nullable=False),
        sa.Column("immutable_fields", sa.JSON(), nullable=False),
        sa.Column("content_hashed", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("entity", name=f"pk_{TABLE}"),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
