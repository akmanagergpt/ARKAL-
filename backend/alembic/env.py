"""Alembic environment for ARKALI. C-03, owner kernel.persistence.

NO ENGINE IS CONSTRUCTED HERE. The engine comes from
`arkali.kernel.persistence.engine.create_persistence_engine`, so the single
construction point that ARK-REQ-0012 requires is not bypassed by the migration
tooling. This file resolves configuration and delegates.

The URL is taken from the Alembic config first, then `ARKALI_DATABASE_URL`. It
is never defaulted to a real location: a migration run that does not know its
target refuses rather than inventing one.
"""

from __future__ import annotations

import os
import pathlib
import sys

from alembic import context

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from arkali.kernel.persistence.base import PersistenceBase  # noqa: E402
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
)

target_metadata = PersistenceBase.metadata


def database_url() -> str:
    configured = context.config.get_main_option("sqlalchemy.url", None)
    url = configured or os.environ.get("ARKALI_DATABASE_URL", "")
    if not url.strip():
        raise ValueError(
            "no database URL: set sqlalchemy.url or ARKALI_DATABASE_URL. "
            "Refusing to migrate an unspecified target."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_persistence_engine(database_url())
    try:
        with engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                render_as_batch=True,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
