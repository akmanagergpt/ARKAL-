"""C-14 artifact descriptor, provenance record and parent edges.

Revision: 0003_artifact_provenance
Parent:   0002_project_registry

Identity is enforced by the database, not by pre-insert checks: the artifact
primary key IS the content address, provenance is keyed one-to-one on it, and
both parent-edge columns are foreign keys, so a chain cannot cite an artifact
that was never registered.

No column here duplicates C-12. `project_revision.provenance_ref` already exists
as a nullable `String(200)` and holds a 71-character address unchanged, so this
revision does not touch the project tables at all.

Forward-only per ARCHITECTURE.md section 10.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_artifact_provenance"
down_revision: str | None = "0002_project_registry"
branch_labels = None
depends_on = None
direction: str = "FORWARD"

ARTIFACT = "artifact"
PROVENANCE = "artifact_provenance"
PARENT = "artifact_parent"

#: `sha256:` + 64 hex characters.
ADDRESS = 71
METADATA = 200


def upgrade() -> None:
    op.create_table(
        ARTIFACT,
        sa.Column("artifact_id", sa.String(length=ADDRESS), nullable=False),
        sa.Column("hash_algorithm", sa.String(length=20), nullable=False),
        sa.Column("digest", sa.String(length=128), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("normalization", sa.String(length=METADATA), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("artifact_id", name=f"pk_{ARTIFACT}"),
    )
    op.create_table(
        PROVENANCE,
        sa.Column("artifact_id", sa.String(length=ADDRESS), nullable=False),
        sa.Column("producer_agent", sa.String(length=METADATA), nullable=False),
        sa.Column("provider_model", sa.String(length=METADATA), nullable=False),
        sa.Column("task_id", sa.String(length=METADATA), nullable=False),
        sa.Column("specification_version", sa.String(length=METADATA), nullable=False),
        sa.Column("context_hash", sa.String(length=METADATA), nullable=False),
        sa.Column("tests", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("artifact_id", name=f"pk_{PROVENANCE}"),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            [f"{ARTIFACT}.artifact_id"],
            name=f"fk_{PROVENANCE}_artifact_id_{ARTIFACT}",
        ),
    )
    op.create_table(
        PARENT,
        sa.Column("artifact_id", sa.String(length=ADDRESS), nullable=False),
        sa.Column("parent_artifact_id", sa.String(length=ADDRESS), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "artifact_id", "parent_artifact_id", name=f"pk_{PARENT}"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_id"],
            [f"{ARTIFACT}.artifact_id"],
            name=f"fk_{PARENT}_artifact_id_{ARTIFACT}",
        ),
        sa.ForeignKeyConstraint(
            ["parent_artifact_id"],
            [f"{ARTIFACT}.artifact_id"],
            name=f"fk_{PARENT}_parent_artifact_id_{ARTIFACT}",
        ),
    )


def downgrade() -> None:
    op.drop_table(PARENT)
    op.drop_table(PROVENANCE)
    op.drop_table(ARTIFACT)
