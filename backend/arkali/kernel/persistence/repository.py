"""C-03 engine-neutral repository abstraction (ARK-REQ-0012).

Owner: kernel.persistence. Implementation phase 5.

WHAT MAKES THIS POSTGRESQL-READY. Every statement is built with the SQLAlchemy
expression language against mapped columns. There is no `text()`, no string
concatenation into SQL, and no dialect branch: the same repository renders for
SQLite and PostgreSQL because it never names either. ADR-0006 registers exactly
this property as MANDATORY and registers verified operation on PostgreSQL as NOT
a requirement, so the abstraction is claimed and the runtime is not.

The Protocol this satisfies is `schema_contract.SupportsRepository`, defined at
Phase 2. It is implemented, not restated: a control asserts the concrete class
is an instance of the Protocol, so a signature change breaks the control rather
than passing silently.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from arkali.kernel.persistence.base import PersistenceBase

ModelT = TypeVar("ModelT", bound=PersistenceBase)


class SqlRepository(Generic[ModelT]):
    """Engine-neutral store for one mapped entity, keyed by its primary key.

    Satisfies `SupportsRepository`: `get` returns the stored object or None and
    `put` stores one. Nothing here is SQLite-specific.
    """

    def __init__(self, session: Session, model: type[ModelT],
                 key_attribute: str) -> None:
        if not hasattr(model, key_attribute):
            raise ValueError(
                f"{model.__name__} has no attribute {key_attribute!r} to key on"
            )
        self._session = session
        self._model = model
        self._key = key_attribute

    @property
    def model(self) -> type[ModelT]:
        return self._model

    def get(self, key: str) -> object | None:
        """The stored entity, or None. Never raises for a missing key."""
        column = getattr(self._model, self._key)
        return self._session.execute(
            select(self._model).where(column == key)
        ).scalar_one_or_none()

    def put(self, key: str, value: object) -> None:
        """Store an entity under `key`, replacing any existing row.

        The key must agree with the value's own key attribute. A mismatch is
        refused rather than silently resolved in favour of one of them, because
        either choice would store something the caller did not ask for.
        """
        if not isinstance(value, self._model):
            raise TypeError(
                f"expected {self._model.__name__}, got {type(value).__name__}"
            )
        actual = getattr(value, self._key)
        if actual != key:
            raise ValueError(
                f"key {key!r} does not match {self._key}={actual!r}; "
                "refusing to store an entity under a key it does not carry"
            )
        self._session.merge(value)

    def delete(self, key: str) -> bool:
        """Remove an entity. True when a row was actually removed."""
        found = self.get(key)
        if found is None:
            return False
        self._session.delete(found)
        return True

    def list_all(self) -> tuple[ModelT, ...]:
        """Every stored entity, ordered by key for deterministic output."""
        column = getattr(self._model, self._key)
        return tuple(
            self._session.execute(
                select(self._model).order_by(column)
            ).scalars().all()
        )

    def count(self) -> int:
        return len(self.list_all())
