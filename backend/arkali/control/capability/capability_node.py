"""C-13 capability node schema (ARK-REQ-0045).

Owner: control.capability.

Authoritative shape: `docs/canonical/EXECUTION_AND_CAPABILITY.md` §1, which
derives it from Master Specification §Capability Graph. Twelve fields, no more:
`extra="forbid"` means an undeclared attribute cannot be attached at all.

REFERENCE, NEVER COPY (ADR-0001, ARK-REQ-0047). The node carries `provider_refs`
and nothing else about a provider. There is no `health`, `availability`, `cost`
or `fallback_configuration` field, so provider state cannot be mirrored here even
by accident — the shadow registry is prevented structurally, not policed after
the fact.

`runtime_requirements` is the one free-form field and therefore the one real
escape hatch: a caller could stuff `{"provider_health": "HEALTHY"}` into it and
recreate the shadow registry inside a dict. `validate_no_shadow_registry` closes
that hatch, and it takes the provider-owned field names as an argument rather
than hard-coding them, because `AUTHORITY_MAP.yaml` `provider_authority.
fields_owned` is the sole store of that list (F-0013).

This module does not import `control.architecture`: both sit in the `control`
layer and `allow_same_layer: false` forbids the edge. Governed vocabularies are
therefore supplied by the caller, never re-derived here.
"""

from __future__ import annotations

import enum
import re
from collections.abc import Iterable, Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arkali.kernel.contracts.capability_errors import (
    MalformedCapabilityIdentity,
    ShadowRegistryViolation,
)

C13_SOURCE = "docs/canonical/EXECUTION_AND_CAPABILITY.md §1 (C-13)"

#: Capability identifiers are dotted lowercase segments, e.g. `build.compile`.
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_]*)*$")

#: `isolation_tier: TRUST-0..4` is part of the C-13 contract itself, so the form
#: is owned here. Which properties each tier requires is NOT owned here - that
#: lives in AUTHORITY_MAP.yaml `isolation.tier_requirements`.
TRUST_TIER = re.compile(r"^TRUST-[0-4]$")


class ConfiguredState(str, enum.Enum):
    """The only two values C-13 declares for `configured_state`."""

    CONFIGURED = "CONFIGURED"
    UNCONFIGURED = "UNCONFIGURED"


class CapabilityNode(BaseModel):
    """One capability node, exactly as C-13 declares it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    version: int
    prerequisites: tuple[str, ...] = ()
    permission_refs: tuple[str, ...] = ()
    evidence_requirement_refs: tuple[str, ...] = ()
    provider_refs: tuple[str, ...] = ()
    isolation_tier: str
    isolation_backend_probe_ref: str | None = None
    runtime_requirements: Mapping[str, Any] = Field(default_factory=dict)
    platform_support: tuple[str, ...] = ()
    fallback_refs: tuple[str, ...] = ()
    configured_state: ConfiguredState = ConfiguredState.UNCONFIGURED

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not CAPABILITY_ID.match(self.id):
            raise MalformedCapabilityIdentity(
                f"capability id {self.id!r} is not a dotted lowercase identifier",
                source=C13_SOURCE,
            )
        if self.version < 1:
            raise MalformedCapabilityIdentity(
                f"{self.id}: version must be >= 1, got {self.version}",
                source=C13_SOURCE,
            )
        if not TRUST_TIER.match(self.isolation_tier):
            raise MalformedCapabilityIdentity(
                f"{self.id}: isolation_tier {self.isolation_tier!r} is not TRUST-0..4",
                source=C13_SOURCE,
            )
        for field_name in ("prerequisites", "fallback_refs"):
            for ref in getattr(self, field_name):
                if not CAPABILITY_ID.match(ref):
                    raise MalformedCapabilityIdentity(
                        f"{self.id}: {field_name} entry {ref!r} is not a capability id",
                        source=C13_SOURCE,
                    )
        if self.id in self.prerequisites or self.id in self.fallback_refs:
            raise MalformedCapabilityIdentity(
                f"{self.id}: a capability may not reference itself", source=C13_SOURCE
            )
        return self


def validate_no_shadow_registry(
    node: CapabilityNode, provider_owned_fields: Iterable[str]
) -> None:
    """Reject provider-owned state smuggled into the free-form fields.

    `provider_owned_fields` must come from AUTHORITY_MAP.yaml
    `provider_authority.fields_owned`. An empty vocabulary fails closed: a check
    with nothing to compare against would pass vacuously (F-0016, F-0017).
    """
    owned = {name.strip().lower() for name in provider_owned_fields if name.strip()}
    if not owned:
        raise ShadowRegistryViolation(
            f"{node.id}: no provider-owned vocabulary supplied; refusing to "
            "report a vacuous PASS",
            source=C13_SOURCE,
        )
    offending = sorted(
        key
        for key in node.runtime_requirements
        if _normalise(key) in owned or _normalise(key).removeprefix("provider_") in owned
    )
    if offending:
        raise ShadowRegistryViolation(
            f"{node.id}: runtime_requirements carries provider-owned state "
            f"{offending}; the Provider/Model Registry is the sole store "
            "(ADR-0001). Hold a provider_ref and resolve at query time.",
            source=C13_SOURCE,
        )


def _normalise(key: str) -> str:
    return key.strip().lower().replace("-", "_")
