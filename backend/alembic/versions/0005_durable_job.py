"""C-19 durable job record and checkpoint.

Revision: 0005_durable_job
Parent:   0004_audit_record

Both identities are enforced by the database, not by pre-insert checks: `job_id`
is the primary key, and (`job_type`, `idempotency_key`) is a named unique
constraint, so a duplicate submission loses to the schema even when two writers
race past the lookup in `JobStore.submit`.

Checkpoint ordering is identity: the primary key is (`job_id`, `sequence`), so
two checkpoints cannot claim one position and an ordinal cannot be reused. The
foreign key means a checkpoint cannot reference a job that was never submitted.

Nothing here schedules. There is no queue, claim, lease, owner or resource
column: admission and allocation are C-21 at Phase 8, and a column added now for
a behaviour that does not exist would be a claim.

Forward-only per ARCHITECTURE.md section 10.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_durable_job"
down_revision: str | None = "0004_audit_record"
branch_labels = None
depends_on = None
direction: str = "FORWARD"

JOB = "durable_job"
CHECKPOINT = "job_checkpoint"

IDENTITY = 64
FIELD = 200
STATE = 40


def upgrade() -> None:
    op.create_table(
        JOB,
        sa.Column("job_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("job_type", sa.String(length=FIELD), nullable=False),
        sa.Column("idempotency_key", sa.String(length=FIELD), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=STATE), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id", name=f"pk_{JOB}"),
        sa.UniqueConstraint(
            "job_type", "idempotency_key", name="uq_durable_job_idempotency"
        ),
    )
    op.create_table(
        CHECKPOINT,
        sa.Column("job_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_id", "sequence", name=f"pk_{CHECKPOINT}"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            [f"{JOB}.job_id"],
            name=f"fk_{CHECKPOINT}_job_id_{JOB}",
        ),
    )


def downgrade() -> None:
    op.drop_table(CHECKPOINT)
    op.drop_table(JOB)
