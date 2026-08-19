"""C-36 child-product version lineage (ARK-REQ-0132, ARK-REQ-0358).

Owner: `lifecycle.evolution`.

WHY A CHILD PRODUCT NEEDS ITS OWN LINEAGE, NOT `StableRevisionPointer`.
`lifecycle.release.StableRevisionPointer` (D-017, Phase 22B) answers "which
revision of ARKALI's own Stable Core is current" - one singleton pointer for
the whole repository. A child product is a different subject entirely: many
products, each with its own independent version history, owned by the
concern that already owns everything else about child products
(`lifecycle.evolution`, per every Phase 24 requirement's Owner column).
Reusing `StableRevisionPointer` itself would conflate two distinct
concerns under one authority and would require the child's own version
bookkeeping to share ARKALI's own core pointer file - not what
`ARK-REQ-0358` ("full core not copied as runtime") or plain single-authority
discipline would produce. This module mirrors `StableRevisionPointer`'s
*discipline* (content-addressed identity, append-only history, no silent
rewrite) without importing or sharing its instance.

EVIDENCE-PLANE DURABILITY, NOT A NEW TABLE OR A NEW FILE FORMAT. Phase 23's
own campaign records are "C-14 artifacts plus C-15 evidence rows, both
reused unmodified" (`docs/contracts/campaign.md`) - no bespoke persistence
was invented for campaigns, and none is invented here either. This module
defines the pure, immutable, content-addressed record shape; a composition
root registers its `rendering()` as a C-14 artifact exactly as an
orchestrator would for any other evidence, the same discipline
`RecoverySupervisor._register_rollback_artifact` already uses. No
`kernel.persistence` import, no engine, no session - a second persistence
mechanism for the same durability property this repository already has one
of is not built here.

ROLLBACK IS A NEW EVENT, NEVER A DELETION. Mirrors `StableRevisionPointer`'s
own "append-only and never rewritten" rule and `RecoverySupervisor`'s "no
novel content" invariant: `restore_to` appends a new `ChildProductVersion`
whose `content_ref` points back at an *already-recorded* version's content,
never truncates or edits history. "Rolled back to v1.4" is itself a fact
in the lineage, not an erasure of v1.5.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from arkali.lifecycle.evolution.content_identity import address_of, is_address
from arkali.lifecycle.evolution.errors import (
    UnknownVersionReferenceError,
    VersionLineageOrderError,
)

LINEAGE_CONTRACT_VERSION: Final[str] = "1.0.0"
Declared = Annotated[str, Field(min_length=1)]


def _validate_content_ref(value: str) -> str:
    if not is_address(value):
        raise ValueError(
            f"content_ref {value!r} is not a canonical content address; a "
            "caller-invented identity is exactly what content addressing "
            "exists to refuse"
        )
    return value


class ChildProductVersion(BaseModel):
    """One version that was, or is, current for one child product.
    Immutable once appended to a `ChildProductVersionLineage`."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    sequence: Annotated[int, Field(ge=1)]
    #: The promoted content's own address (a manifest/candidate reference) -
    #: never a caller-chosen label.
    content_ref: Declared
    #: The campaign that produced this version, traceable back to
    #: `child_product_campaign._child_campaign_id` - a free identifier, not an
    #: embedded object, the same loose-coupling `CampaignAttempt.candidate_id`
    #: already uses.
    campaign_id: Declared
    #: `None` only for the first version in a lineage.
    parent_ref: str | None = None
    #: True when this version's `content_ref` reproduces an earlier version's
    #: content rather than introducing new content - the whole of what makes
    #: a rollback a rollback and not an ordinary forward version.
    is_rollback: bool = False

    @field_validator("content_ref")
    @classmethod
    def _content_ref_is_an_address(cls, value: str) -> str:
        return _validate_content_ref(value)

    def rendering(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode("utf-8")

    @property
    def version_ref(self) -> str:
        """Content-addressed identity of this version record itself -
        distinct from `content_ref`, which addresses the promoted content,
        not the version record describing it."""
        return address_of(self.rendering())


class ChildProductVersionLineage(BaseModel):
    """One child product's complete, append-only version history.

    Mirrors `CampaignLedger`'s immutable-update shape: every mutating method
    returns a *new* lineage rather than mutating this one, and `versions` is
    a tuple no caller can append to except through `append`/`restore_to`,
    both of which validate order before returning anything.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: str = LINEAGE_CONTRACT_VERSION
    product_ref: Declared
    versions: tuple[ChildProductVersion, ...] = ()

    @property
    def current(self) -> ChildProductVersion | None:
        return self.versions[-1] if self.versions else None

    def find(self, version_ref: str) -> ChildProductVersion:
        """The already-recorded version this `version_ref` names, or refuse.
        `restore_to` calls this so a rollback target must already be in
        this lineage's own durable history - a caller's claim that some
        content was "an earlier version" is never trusted on its own."""
        for version in self.versions:
            if version.version_ref == version_ref:
                return version
        raise UnknownVersionReferenceError(
            f"version_ref {version_ref!r} is not in this lineage's own "
            f"recorded history for product {self.product_ref!r}"
        )

    def append(self, version: ChildProductVersion) -> ChildProductVersionLineage:
        """Append one new, forward version. Refuses before returning
        anything if `sequence`/`parent_ref` do not honestly continue this
        lineage - a gap or a rewritten parent is refused, not silently
        accepted."""
        expected_sequence = len(self.versions) + 1
        expected_parent = self.current.version_ref if self.current else None
        if version.sequence != expected_sequence or version.parent_ref != expected_parent:
            raise VersionLineageOrderError(
                f"product {self.product_ref!r}: version {version.sequence} "
                f"(parent={version.parent_ref!r}) does not honestly continue "
                f"this lineage (expected sequence={expected_sequence}, "
                f"parent={expected_parent!r})"
            )
        return type(self).model_validate(
            {**self.model_dump(), "versions": (*self.versions, version)}
        )

    def restore_to(
        self, version_ref: str, *, campaign_id: str
    ) -> ChildProductVersionLineage:
        """ARK-REQ-0132: roll back to an already-recorded version by
        appending a new version whose content reproduces the target's - the
        target must already be in this lineage's own history (`find`
        refuses otherwise). History is never truncated or edited."""
        target = self.find(version_ref)
        rollback_version = ChildProductVersion(
            sequence=len(self.versions) + 1,
            content_ref=target.content_ref,
            campaign_id=campaign_id,
            parent_ref=self.current.version_ref if self.current else None,
            is_rollback=True,
        )
        return self.append(rollback_version)

    def rendering(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode("utf-8")

    @property
    def lineage_ref(self) -> str:
        return address_of(self.rendering())
