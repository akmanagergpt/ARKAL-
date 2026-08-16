"""C-28 reusable-component metadata (ARK-REQ-0128).

MS §Knowledge: "Reusable components require isolated tests/security/
compatibility metadata." `ReusableComponentDescriptor` requires all three
categories as typed, non-empty sub-records — a descriptor missing any one
of them fails at construction (pydantic required-field refusal, the same
shape `RepairFingerprint`'s six required fields use).

METADATA IS NECESSARY BUT NOT SUFFICIENT. Carrying the three metadata
categories is what ARK-REQ-0128 requires and this module never hides a
component's metadata, however unfavourable — `test`, `security` and
`compatibility` are always readable. But `is_verified_reusable` is a
narrower, honest question ("may this be reused as verified"): it is True
only when the carried metadata itself reports no failing test and no open
security finding. A component whose own declared metadata reports a
failure is not verified reusable — it is still fully described.
"""

from __future__ import annotations

import json
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from arkali.engineering.knowledge.errors import IncompleteComponentMetadataError
from arkali.kernel.contracts.content_address import address_of

CONTRACT_VERSION: Final[str] = "1.0.0"
Declared = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(ge=0)]


class ComponentTestMetadata(BaseModel):
    """Isolated test evidence for one reusable component."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    suite_ref: Declared
    passed: Count
    failed: Count = 0


class SecurityMetadata(BaseModel):
    """Isolated security-review evidence for one reusable component."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    review_ref: Declared
    findings_cleared: bool


class CompatibilityMetadata(BaseModel):
    """Declared compatibility surface for one reusable component."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    contract_version: Declared
    compatible_with: tuple[Declared, ...]

    @field_validator("compatible_with")
    @classmethod
    def _at_least_one_declared_target(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise IncompleteComponentMetadataError(
                "a reusable component must declare at least one "
                "compatible consumer or version"
            )
        return value


class ReusableComponentDescriptor(BaseModel):
    """A reusable component carrying all three canonical metadata
    categories (ARK-REQ-0128). `test`, `security` and `compatibility` are
    all mandatory fields — an attempt to construct a descriptor missing any
    one of them is refused by pydantic before this class's own logic runs."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    contract_version: str = CONTRACT_VERSION
    component_id: Declared
    test: ComponentTestMetadata
    security: SecurityMetadata
    compatibility: CompatibilityMetadata

    @property
    def is_verified_reusable(self) -> bool:
        """Whether the component's own carried metadata supports reuse:
        zero failing tests and no open security finding. False is not an
        error — an unverified component is still fully described."""
        return self.test.failed == 0 and self.security.findings_cleared

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def descriptor_ref(self) -> str:
        return address_of(self.rendering())
