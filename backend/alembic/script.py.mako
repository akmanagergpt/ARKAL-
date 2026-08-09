"""${message}

Revision: ${up_revision}
Parent:   ${down_revision | comma,n}

Every ARKALI revision declares `direction`, which the C-03 migration runner
reads to build its `MigrationContract`. The filename and `revision` must match.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}
direction: str = "FORWARD"


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
