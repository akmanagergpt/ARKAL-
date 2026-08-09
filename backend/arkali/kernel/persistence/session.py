"""C-03 session foundation and unit of work.

Owner: kernel.persistence. Implementation phase 5.

A unit of work either commits or rolls back. There is no path that leaves a
session open on failure, and no `commit()` that swallows an exception - a write
that did not land must not be reportable as one that did, which is the
persistence form of the false-success rule the Build Protocol states.

NO POLICY IMPORT. Whether a write is permitted is a `control.policy` decision,
and `control.policy` is layer rank 1 while this context is rank 0. Enforcement
therefore happens at the call site in a higher layer; this module governs
transaction boundaries only and holds no opinion about authorisation.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from arkali.kernel.persistence.base import PersistenceBase


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Session factory bound to one engine.

    `expire_on_commit=False` so a committed object stays readable without a
    further query; the durability evidence reopens the database instead of
    trusting an identity-map hit.
    """
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def create_base_schema(engine: Engine) -> None:
    """Create the base schema directly, for tests and first-run bootstrap.

    This is NOT the migration path. Alembic owns schema evolution; this creates
    the same metadata in one step so a control can prove the two agree.
    """
    PersistenceBase.metadata.create_all(engine)


def drop_base_schema(engine: Engine) -> None:
    """Drop the base schema. Used only by controls, never by shipping flow."""
    PersistenceBase.metadata.drop_all(engine)


@contextmanager
def unit_of_work(factory: sessionmaker[Session]) -> Iterator[Session]:
    """A transaction that commits on success and rolls back on any exception.

    The exception is re-raised, never converted. A caller cannot obtain a
    committed transaction from a failed block.
    """
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
