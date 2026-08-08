"""C-10 isolation property / backend descriptor (ARK-REQ-0017, 0113, 0114, 0118-0122).

Owner: control.isolation (Protected Core).

ADR-0002: tiers declare required **properties**; backends declare **provided**
properties; backends compose. Nothing here names Windows Sandbox or Hyper-V as a
requirement - the technology list is governed data in `AUTHORITY_MAP.yaml`
`isolation`, and ARKALI is not bound to any one host feature.

NO SHADOW SECURITY MODEL. The seven properties, the five tier requirement sets,
the backend property tables, `on_unsatisfiable`, `capability_state_when_
unsatisfiable` and `silent_downgrade_permitted` are all parsed at call time.
This module declares none of them.

NEVER SILENTLY DOWNGRADE (ARK-REQ-0122). `resolve` returns a composition only
when the union of its provided properties covers every required property. There
is no partial success, no nearest-match and no default: an unsatisfiable tier
yields UNSUPPORTED and execution DENY, which is what `on_unsatisfiable` says.
"""

from __future__ import annotations

import pathlib
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.errors import AuthoritativeSourceError
from arkali.kernel.contracts.results import HonestState
from arkali.control.isolation.isolation_errors import TrustTierViolation

AUTHORITY_MAP_RELPATH = "docs/canonical/AUTHORITY_MAP.yaml"


class BackendDescriptor(BaseModel):
    """One isolation backend and the properties it declares it provides."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    provides: tuple[str, ...]
    availability: HonestState = HonestState.NOT_TESTED
    detail: str = ""

    @property
    def is_available(self) -> bool:
        """Only a probed PASS counts. NOT_TESTED is not availability."""
        return self.availability is HonestState.PASS


class IsolationResolution(BaseModel):
    """The deterministic answer for one tier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: str
    required: tuple[str, ...]
    satisfied_by: tuple[str, ...]
    missing: tuple[str, ...]
    capability_state: HonestState
    execution_decision: str

    @property
    def satisfied(self) -> bool:
        return not self.missing


class IsolationAuthority:
    """Canonical isolation model, parsed. Construct with `load`."""

    def __init__(self, raw: dict[str, Any], source_path: str) -> None:
        self._raw = raw
        self.source_path = source_path
        for key in ("properties", "tier_requirements", "backends"):
            if key not in raw:
                raise AuthoritativeSourceError(
                    f"isolation section missing {key!r}", source=source_path
                )

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> IsolationAuthority:
        path = repo_root / AUTHORITY_MAP_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError("authority map not found", source=str(path))
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or "isolation" not in raw:
            raise AuthoritativeSourceError(
                "authority map declares no isolation section", source=str(path)
            )
        return cls(raw["isolation"], str(path))

    @property
    def properties(self) -> tuple[str, ...]:
        return tuple(self._raw["properties"])

    @property
    def tiers(self) -> tuple[str, ...]:
        return tuple(sorted(self._raw["tier_requirements"]))

    @property
    def silent_downgrade_permitted(self) -> bool:
        return bool(self._raw.get("silent_downgrade_permitted", False))

    @property
    def on_unsatisfiable(self) -> str:
        return str(self._raw.get("on_unsatisfiable", "DENY"))

    @property
    def capability_state_when_unsatisfiable(self) -> HonestState:
        return HonestState(
            self._raw.get("capability_state_when_unsatisfiable", "UNSUPPORTED")
        )

    @property
    def backend_change_gate(self) -> str:
        return str(self._raw.get("backend_change_gate", ""))

    def required_properties(self, tier: str) -> tuple[str, ...]:
        requirements = self._raw["tier_requirements"]
        if tier not in requirements:
            raise TrustTierViolation(
                f"unknown trust tier {tier!r}; a tier is never inferred",
                source=self.source_path,
            )
        return tuple(requirements[tier])

    def declared_backends(self) -> dict[str, tuple[str, ...]]:
        return {name: tuple(p) for name, p in self._raw["backends"].items()}

    def descriptor(self, name: str) -> BackendDescriptor:
        declared = self.declared_backends()
        if name not in declared:
            raise AuthoritativeSourceError(
                f"unknown isolation backend {name!r}", source=self.source_path
            )
        return BackendDescriptor(name=name, provides=declared[name])

    def validate_provided(self, backend: BackendDescriptor) -> None:
        """A backend may not claim a property the canonical set does not define.

        This is the forged-capability check: an adapter cannot invent
        `KERNEL_ISOLATION` to satisfy a tier it does not really satisfy.
        """
        declared = self.declared_backends()
        canonical = set(self.properties)
        invented = sorted(set(backend.provides) - canonical)
        if invented:
            raise TrustTierViolation(
                f"backend {backend.name!r} claims undefined properties {invented}",
                source=self.source_path,
            )
        expected = declared.get(backend.name)
        if expected is not None and set(backend.provides) - set(expected):
            raise TrustTierViolation(
                f"backend {backend.name!r} claims more than the canonical map "
                f"declares: {sorted(set(backend.provides) - set(expected))}",
                source=self.source_path,
            )

    def resolve(
        self, tier: str, available: tuple[BackendDescriptor, ...]
    ) -> IsolationResolution:
        """Find a composition covering every required property, or fail closed."""
        required = self.required_properties(tier)
        usable = []
        provided: set[str] = set()
        for backend in available:
            self.validate_provided(backend)
            if not backend.is_available:
                continue
            usable.append(backend.name)
            provided |= set(backend.provides)
        missing = tuple(sorted(set(required) - provided))
        contributing = tuple(
            sorted(
                name
                for name in usable
                if set(self.declared_backends()[name]) & set(required)
            )
        )
        if missing:
            return IsolationResolution(
                tier=tier,
                required=required,
                satisfied_by=(),
                missing=missing,
                capability_state=self.capability_state_when_unsatisfiable,
                execution_decision=self.on_unsatisfiable,
            )
        return IsolationResolution(
            tier=tier,
            required=required,
            satisfied_by=contributing,
            missing=(),
            capability_state=HonestState.PASS,
            execution_decision="ALLOW",
        )
