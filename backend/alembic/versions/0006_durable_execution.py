"""C-19 durability semantics: execution attempts, retry bound, timeout basis.

Revision: 0006_durable_execution
Parent:   0005_durable_job

Retry accounting is rows, not a counter. `job_execution_attempt` holds one row
per attempt with the primary key (`job_id`, `attempt`), so the count is derived
from what actually happened, cannot be reset by restarting a process, and cannot
be set by a caller. That primary key is also the concurrency backstop: two
writers opening the same next attempt cannot both succeed.

The retry bound and the per-attempt timeout are recorded ON THE JOB, so the terms
a job was admitted under survive a restart and cannot be widened by changing a
default later. The deadline itself is absolute and lives on the attempt: a
remaining-duration counter would silently restart with the process.

`owner` records who is executing. It does not decide who should - allocation is
C-21 at Phase 8, and no queue, priority, capacity or resource column exists here.

Existing rows are backfilled with the declared defaults, because both new job
columns are NOT NULL and `durable_job` may already hold rows from 0005.

Forward-only per ARCHITECTURE.md section 10.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006_durable_execution"
down_revision: str | None = "0005_durable_job"
branch_labels = None
depends_on = None
direction: str = "FORWARD"

JOB = "durable_job"
ATTEMPT = "job_execution_attempt"

IDENTITY = 64
FIELD = 200
STATE = 40

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_ATTEMPT_TIMEOUT_SECONDS = 300


def upgrade() -> None:
    # server_default carries the backfill for rows written under 0005 and is
    # then dropped, so the application supplies the value from the contract
    # rather than the schema quietly supplying one forever.
    with op.batch_alter_table(JOB) as batch:
        batch.add_column(
            sa.Column(
                "max_attempts",
                sa.Integer(),
                nullable=False,
                server_default=str(DEFAULT_MAX_ATTEMPTS),
            )
        )
        batch.add_column(
            sa.Column(
                "attempt_timeout_seconds",
                sa.Integer(),
                nullable=False,
                server_default=str(DEFAULT_ATTEMPT_TIMEOUT_SECONDS),
            )
        )
    with op.batch_alter_table(JOB) as batch:
        batch.alter_column("max_attempts", server_default=None)
        batch.alter_column("attempt_timeout_seconds", server_default=None)

    op.create_table(
        ATTEMPT,
        sa.Column("job_id", sa.String(length=IDENTITY), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("owner", sa.String(length=FIELD), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=STATE), nullable=True),
        sa.Column("detail", sa.String(length=FIELD), nullable=True),
        sa.PrimaryKeyConstraint("job_id", "attempt", name=f"pk_{ATTEMPT}"),
        sa.ForeignKeyConstraint(
            ["job_id"], [f"{JOB}.job_id"], name=f"fk_{ATTEMPT}_job_id_{JOB}"
        ),
    )


def downgrade() -> None:
    op.drop_table(ATTEMPT)
    with op.batch_alter_table(JOB) as batch:
        batch.drop_column("attempt_timeout_seconds")
        batch.drop_column("max_attempts")
