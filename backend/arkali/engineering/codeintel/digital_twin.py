"""C-24 Digital Twin composition (ARK-REQ-0067).

The view vocabulary belongs to ``ARCHITECTURE.md`` and is supplied by
``GraphVocabulary``.  This module therefore composes contributions; it does not
carry a second list of view names.  A contribution is either backed by one or
more derived artifact addresses, or explicitly declares why the view is absent.
An empty contribution is refused because it is indistinguishable from a claim
that a view was inspected and contained nothing.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from arkali.engineering.codeintel.errors import (
    DerivedStoreTreatedAsAuthority,
    IncompleteDigitalTwin,
)
from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.kernel.contracts.content_address import is_address

Declared = Annotated[str, Field(min_length=1)]


class TwinView(BaseModel):
    """One honestly declared Digital Twin view contribution.

    ``artifact_addresses`` references derived material without making the twin
    its authority.  ``absent_reason`` is the honest representation for a view
    whose owning source cannot yet be composed.  Exactly one form is required.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    view: Declared
    sources: tuple[Declared, ...]
    artifact_addresses: tuple[Declared, ...] = ()
    absent_reason: Declared | None = None

    @field_validator("artifact_addresses")
    @classmethod
    def _addresses_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not is_address(value) for value in values):
            raise ValueError("derived artifacts must use canonical content addresses")
        return values

    @model_validator(mode="after")
    def _is_backed_or_declared_absent(self) -> TwinView:
        if not self.sources:
            raise ValueError("a derived Digital Twin view must name its source")
        backed = bool(self.artifact_addresses)
        absent = self.absent_reason is not None
        if backed == absent:
            raise ValueError(
                "a Digital Twin view must have artifact addresses or one explicit "
                "absence reason, never neither or both"
            )
        return self


class DigitalTwin:
    """A complete composition of the view set declared by the architecture."""

    def __init__(self, views: tuple[TwinView, ...]) -> None:
        self._views = views

    @classmethod
    def compose(
        cls, vocabulary: GraphVocabulary, contributions: Iterable[TwinView]
    ) -> DigitalTwin:
        expected = vocabulary.view_ids()
        by_id: dict[str, TwinView] = {}
        for contribution in contributions:
            identifier = vocabulary.require_view(contribution.view)
            if identifier in by_id:
                raise IncompleteDigitalTwin(
                    f"Digital Twin view {identifier!r} was composed more than once",
                    source=vocabulary.source,
                )
            by_id[identifier] = contribution.model_copy(update={"view": identifier})

        missing = tuple(view for view in expected if view not in by_id)
        if missing:
            raise IncompleteDigitalTwin(
                f"Digital Twin omits specified view(s) {list(missing)}; every view "
                "must be backed by derived material or explicitly declared absent",
                source=vocabulary.source,
            )
        return cls(tuple(by_id[view] for view in expected))

    def views(self) -> tuple[TwinView, ...]:
        """Contributions in canonical declaration order."""
        return self._views

    def view_ids(self) -> tuple[str, ...]:
        return tuple(view.view for view in self._views)

    def absent_view_ids(self) -> tuple[str, ...]:
        return tuple(view.view for view in self._views if view.absent_reason is not None)

    def resolve_authority(self, concern: str) -> None:
        """Always refuse: the twin is a derived navigation aid, never authority."""
        raise DerivedStoreTreatedAsAuthority(
            f"the Digital Twin is derived and cannot answer {concern!r}; consult "
            "the owning source recorded by the view contribution",
            source="ARCHITECTURE.md §11",
        )

    def __len__(self) -> int:
        return len(self._views)
