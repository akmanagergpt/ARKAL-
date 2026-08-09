"""C-15 append-only evidence record chain.

Revision: 0004_audit_record
Parent:   0003_artifact_provenance

The chain's shape is enforced by the database, not by pre-insert checks: the
primary key IS the integrity digest, `sequence` is unique so two records cannot
claim one position, `artifact_id` is a foreign key into C-14 so evidence cannot
reference an artifact that was never registered, and `supersedes` is a
self-referential foreign key so a supersession cannot name a record that does
not exist.

Nothing here duplicates C-14. `artifact_id` is a reference; no artifact metadata
is copied into this table.

Forward-only per ARCHITECTURE.md section 10.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_audit_record"
down_revision: str | None = "0003_artifact_provenance"
branch_labels = None
depends_on = None
direction: str = "FORWARD"

AUDIT = "audit_record"
ARTIFACT = "artifact"

DIGEST = 71
FIELD = 200


def upgrade() -> None:
    op.create_table(
        AUDIT,
        sa.Column("record_hash", sa.String(length=DIGEST), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("previous_hash", sa.String(length=DIGEST), nullable=True),
        sa.Column("requirement_id", sa.String(length=FIELD), nullable=False),
        sa.Column("contract_id", sa.String(length=FIELD), nullable=True),
        sa.Column("artifact_id", sa.String(length=DIGEST), nullable=False),
        sa.Column("test_id", sa.String(length=FIELD), nullable=True),
        sa.Column("producer", sa.String(length=FIELD), nullable=False),
        sa.Column("result", sa.String(length=40), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes", sa.String(length=DIGEST), nullable=True),
        sa.PrimaryKeyConstraint("record_hash", name=f"pk_{AUDIT}"),
        sa.UniqueConstraint("sequence", name=f"uq_{AUDIT}_sequence"),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            [f"{ARTIFACT}.artifact_id"],
            name=f"fk_{AUDIT}_artifact_id_{ARTIFACT}",
        ),
        sa.ForeignKeyConstraint(
            ["supersedes"],
            [f"{AUDIT}.record_hash"],
            name=f"fk_{AUDIT}_supersedes_{AUDIT}",
        ),
    )


def downgrade() -> None:
    op.drop_table(AUDIT)
