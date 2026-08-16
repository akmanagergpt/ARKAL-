"""C-20 workflow execution state and per-node execution evidence.

Revision: 0009_workflow_execution
Parent:   0008_workflow_graph

`workflow_execution` tracks one running (or finished) execution of one
workflow graph revision, mutable by the canonical `WorkflowExecution` machine
(Phase 3). `workflow_node_execution` is append-only, per-node execution
evidence - `(execution_id, sequence)` as primary key so the same node id
visited more than once (a `LOOP` body) leaves distinct rows, mirroring
`job_checkpoint`'s `(job_id, sequence)` shape.

Nothing here is a second graph-identity or lifecycle authority: the executor
composes `workflow_revision` (0008) for the canonical content and the
canonical `WorkflowExecution` machine for legal transitions.

Forward-only per ARCHITECTURE.md section 10.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0009_workflow_execution"
down_revision: str | None = "0008_workflow_graph"
branch_labels = None
depends_on = None
direction: str = "FORWARD"

EXECUTION = "workflow_execution"
NODE_EXECUTION = "workflow_node_execution"

IDENTITY = 64
STATE = 32
HASH = 128
KIND = 32
OUTCOME = 200


def upgrade() -> None:
    op.create_table(
        EXECUTION,
        sa.Column("execution_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("workflow_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("bound_revision_hash", sa.String(length=HASH), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=STATE), nullable=False),
        sa.Column("frontier", sa.JSON(), nullable=False),
        sa.Column("loop_counts", sa.JSON(), nullable=False),
        sa.Column("merge_arrivals", sa.JSON(), nullable=False),
        sa.Column("pending_approval_node_id", sa.String(length=IDENTITY), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("execution_id", name=f"pk_{EXECUTION}"),
    )
    op.create_table(
        NODE_EXECUTION,
        sa.Column("execution_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("kind", sa.String(length=KIND), nullable=False),
        sa.Column("control_construct", sa.String(length=KIND), nullable=True),
        sa.Column("revision_hash", sa.String(length=HASH), nullable=False),
        sa.Column("outcome", sa.String(length=OUTCOME), nullable=False),
        sa.Column("job_id", sa.String(length=IDENTITY), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("execution_id", "sequence", name=f"pk_{NODE_EXECUTION}"),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            [f"{EXECUTION}.execution_id"],
            name=f"fk_{NODE_EXECUTION}_execution_id_{EXECUTION}",
        ),
    )


def downgrade() -> None:
    op.drop_table(NODE_EXECUTION)
    op.drop_table(EXECUTION)
