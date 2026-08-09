"""C-19 job-type contract registry and the heartbeat liveness term.

Revision: 0007_job_type_registry
Parent:   0006_durable_execution

`durable_job_type` is the registry `ARK-REQ-0060`'s Appendix A applicability rule
reads: `job_type.supports_pause == true`. Until it existed the rule was
unevaluable, and governing rule 7 resolves an unwaived unevaluable rule to
APPLICABLE - so the table is what makes the question answerable, not what makes
the requirement go away.

`job_type` is the primary key and is the same value `durable_job.job_type`
already carries. There is deliberately NO foreign key from `durable_job`: one
would make registration a precondition of submitting, which is admission
control, and admission is C-21 at Phase 8. An unregistered type instead fails
closed where the capability is actually asked about.

`heartbeat_timeout_seconds` is a THIRD term, distinct from the two 0006 added.
`attempt_timeout_seconds` bounds elapsed work and `deadline_at` is its absolute
instant; this one bounds SILENCE. The canonical crash-recovery rule
(`EXECUTION_AND_CAPABILITY.md` section 3) keys on a job's heartbeat, and a worker
can fall silent long before its deadline. Recorded on the job for the same reason
as its siblings: the terms a job was admitted under must survive a restart.

Existing rows are backfilled with the declared default, because the new job
column is NOT NULL and `durable_job` may already hold rows from 0005/0006. The
server default is then dropped, so the application supplies the value from the
contract rather than the schema quietly supplying one forever.

Forward-only per ARCHITECTURE.md section 10.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0007_job_type_registry"
down_revision: str | None = "0006_durable_execution"
branch_labels = None
depends_on = None
direction: str = "FORWARD"

JOB = "durable_job"
JOB_TYPE = "durable_job_type"

FIELD = 200

DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 60


def upgrade() -> None:
    op.create_table(
        JOB_TYPE,
        sa.Column("job_type", sa.String(length=FIELD), nullable=False),
        # NOT NULL with no server default: a type cannot be declared without
        # stating the answer, and an undeclared type is an absent row rather
        # than a NULL flag.
        sa.Column("supports_pause", sa.Boolean(), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_type", name=f"pk_{JOB_TYPE}"),
    )

    with op.batch_alter_table(JOB) as batch:
        batch.add_column(
            sa.Column(
                "heartbeat_timeout_seconds",
                sa.Integer(),
                nullable=False,
                server_default=str(DEFAULT_HEARTBEAT_TIMEOUT_SECONDS),
            )
        )
    with op.batch_alter_table(JOB) as batch:
        batch.alter_column("heartbeat_timeout_seconds", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table(JOB) as batch:
        batch.drop_column("heartbeat_timeout_seconds")
    op.drop_table(JOB_TYPE)
