"""C-36 child-product identity and the three canonical modes (ARK-REQ-0131).

Owner: `lifecycle.evolution`.

MS "AI-Native Child Products" declares exactly three modes - Standard,
AI-Assisted, AI-Native Self-Evolving - and states that only mode 3 "uses a
lightweight independent Product Evolution SDK". `ChildProductMode` is that
three-member vocabulary, not invented here: a fourth mode cannot be
constructed, and `ChildProductIdentity.uses_evolution_sdk` is the single
place that decides SDK eligibility, so no caller re-derives the rule from
the mode's name.

IDENTITY, NOT RUNTIME. This module records what a child product *is* -
which product, which mode - never how it runs. `ARK-REQ-0358` ("child
product runs independently; full core not copied as runtime") is a
constraint on the generated child's own deployed artifact, which this
context does not build; nothing here reaches `engineering.candidate` or
any generation authority; a structural control confines this file to
identity/reference concerns.
"""

from __future__ import annotations

import enum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.lifecycle.evolution.content_identity import address_of

Declared = Annotated[str, Field(min_length=1)]


class ChildProductMode(str, enum.Enum):
    """The three canonical modes MS "AI-Native Child Products" names, and
    no others. Only `AI_NATIVE_SELF_EVOLVING` is SDK-eligible."""

    STANDARD = "STANDARD"
    AI_ASSISTED = "AI_ASSISTED"
    AI_NATIVE_SELF_EVOLVING = "AI_NATIVE_SELF_EVOLVING"


#: The one mode MS names as SDK-eligible ("Level 3 uses a lightweight
#: independent Product Evolution SDK"). A frozenset of one, not a bare
#: comparison, so a future canonical widening of eligibility changes one
#: literal rather than an `if` scattered across callers.
_SDK_ELIGIBLE_MODES: Final[frozenset[ChildProductMode]] = frozenset(
    {ChildProductMode.AI_NATIVE_SELF_EVOLVING}
)


class ChildProductIdentity(BaseModel):
    """One child product's canonical identity (C-36).

    `product_id` is the caller-assigned stable identifier (never re-derived,
    never guessed); `product_ref` is the content-addressed identity derived
    from it and the declared mode, the same discipline `CampaignDeclaration.
    campaign_ref` already uses for C-33 evidence keys.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    product_id: Declared
    name: Declared
    mode: ChildProductMode

    @property
    def uses_evolution_sdk(self) -> bool:
        """Whether this product's mode makes it eligible for the Product
        Evolution SDK / bounded campaign machinery at all. `STANDARD` and
        `AI_ASSISTED` products are never eligible - MS reserves the SDK for
        mode 3 only."""
        return self.mode in _SDK_ELIGIBLE_MODES

    def rendering(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode("utf-8")

    @property
    def product_ref(self) -> str:
        """Content-addressed identity of this declared identity."""
        return address_of(self.rendering())
