"""C-12 project registry: project and immutable revision tables.

Revision: 0002_project_registry
Parent:   0001_persistence_base_schema

Identity is enforced by the database, not by pre-insert checks: primary keys on
both tables, a unique constraint on project name, a foreign key from revision to
project, and a unique constraint on (project_id, sequence).

Forward-only per ARCHITECTURE.md section 10.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_project_registry"
down_revision: str | None = "0001_persistence_base_schema"
branch_labels = None
depends_on = None
direction: str = "FORWARD"

PROJECT = "project"
REVISION = "project_revision"


def upgrade() -> None:
    op.create_table(
        PROJECT,
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("project_id", name=f"pk_{PROJECT}"),
        sa.UniqueConstraint("name", name=f"uq_{PROJECT}_name"),
    )
    op.create_table(
        REVISION,
        sa.Column("revision_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provenance_ref", sa.String(length=200), nullable=True),
        sa.PrimaryKeyConstraint("revision_id", name=f"pk_{REVISION}"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            [f"{PROJECT}.project_id"],
            name=f"fk_{REVISION}_project_id_{PROJECT}",
        ),
        sa.UniqueConstraint(
            "project_id", "sequence", name="uq_revision_project_sequence"
        ),
    )


def downgrade() -> None:
    op.drop_table(REVISION)
    op.drop_table(PROJECT)
