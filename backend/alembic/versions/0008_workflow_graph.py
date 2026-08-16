"""C-20 canonical workflow graph: workflow identity and immutable revisions.

Revision: 0008_workflow_graph
Parent:   0007_job_type_registry

`workflow` records that a workflow id exists. `workflow_revision` records every
revision ever published for it, keyed (`workflow_id`, `revision_number`) - there
is no "current graph" row a save overwrites, matching C-20's declared
"revision-hashed + semver" versioning. The foreign key means a revision cannot
reference a workflow that was never created.

Nothing here schedules or executes. The derived execution plan (ADR-0004) and
the executor are later Phase 17 packages and appear nowhere in this schema.

Forward-only per ARCHITECTURE.md section 10.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0008_workflow_graph"
down_revision: str | None = "0007_job_type_registry"
branch_labels = None
depends_on = None
direction: str = "FORWARD"

WORKFLOW = "workflow"
REVISION = "workflow_revision"

IDENTITY = 64
SEMVER = 32
HASH = 128


def upgrade() -> None:
    op.create_table(
        WORKFLOW,
        sa.Column("workflow_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workflow_id", name=f"pk_{WORKFLOW}"),
    )
    op.create_table(
        REVISION,
        sa.Column("workflow_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("semver", sa.String(length=SEMVER), nullable=False),
        sa.Column("revision_hash", sa.String(length=HASH), nullable=False),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "workflow_id", "revision_number", name=f"pk_{REVISION}"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            [f"{WORKFLOW}.workflow_id"],
            name=f"fk_{REVISION}_workflow_id_{WORKFLOW}",
        ),
    )


def downgrade() -> None:
    op.drop_table(REVISION)
    op.drop_table(WORKFLOW)
