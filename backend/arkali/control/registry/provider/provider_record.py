"""C-11 provider / model record.

Owner: `control.registry.provider`.

WHAT THIS IS. The record that makes ARK-REQ-0052 concrete: the Provider/Model
Registry is the sole canonical authority for provider identity, model identity,
configuration, health, availability, cost metadata and fallback. Those seven
concerns are exactly the fields below, and a structural control reconciles the
model against `AUTHORITY_MAP.yaml` `provider_authority.fields_owned` in BOTH
directions, so an eighth field or a missing seventh fails rather than drifts.

C-11 IS `INT`, NOT `DB`. The contract inventory gives C-11 kind `INT` where
C-12 - the Project/Revision Registry - is `DB+INT`. That difference is governed
data and it is why this package adds no table, no migration and no ORM record. A
record is a value.

HEALTH IS NOT REDECLARED HERE. The state vocabulary belongs to the canonical
`ProviderHealth` machine delivered at Phase 3, whose authority
`AUTHORITY_MAP.yaml` already assigns to this context. This module reads
`DEFINITION.states` and refuses anything outside it; it declares no state, no
transition and no second machine, so the canonical machine count stays at 12.
A control asserts that this module contains no state literal.

CONFIGURATION CANNOT CARRY A SECRET, AND HOLDS NO POLICY STATE EITHER.
Provider configuration is where an API key would be smuggled into a governed
record, so `configuration` holds opaque C-09 secret **handles** and every string
the record carries is scanned for raw-secret shapes and refused. ARK-REQ-0100
forbids any automated actor writing or exporting a raw secret.

The handles are plain identifiers, exactly as `control.capability` holds
`provider_refs`, and deliberately NOT `control.policy.SecretReference` objects.
Two reasons, both structural. First, `control.policy` is the same layer rank as
this context: importing it would be the repository's first live edge leaning on
the `policy_callable_from_any_layer` exemption, which
`test_live_repository_uses_no_exempt_edge` refuses precisely so an exemption
cannot quietly become a habit - the same call Phase 6 Package 2 made when it
moved a mechanism to the kernel rather than widen an exemption. Second, and more
importantly, `SecretReference` carries `revoked`, which is POLICY state: storing
it here would mirror another authority's values inside this registry, which is
the very disease ARK-REQ-0053 names. Whether a handle is still usable is asked of
the Permission Broker at query time, by a caller whose layer may legally reach
`control.policy` downward.

WHAT THIS PACKAGE DOES NOT DO. It contacts no provider, issues no request,
measures no live health and simulates none of those things - ARK-REQ-0219
forbids fabricating or simulating an external-provider result, and the honest
position before a runtime exists is that no result exists. It does not activate
the Capability Graph, which is Phase 9B, so `can_perform` keeps returning
`NOT_CONFIGURED` and Phase 8 admission keeps refusing with
`CAPABILITY_NOT_CONFIGURED`.
"""

from __future__ import annotations

import re
from typing import Final

from pydantic import BaseModel, ConfigDict

from arkali.control.registry.provider.errors import (
    InvalidProviderIdentity,
    RawSecretInProviderConfiguration,
    UnknownProviderHealthState,
)
from arkali.control.registry.provider.provider_health_state_machine import DEFINITION

C11_SOURCE: Final[str] = (
    "docs/canonical/CONTRACT_INVENTORY.md C-11 + "
    "MS §Provider and Agent separation"
)

#: Provider and model identifiers are dotted lowercase segments, the same shape
#: C-13 already requires of a capability id, so a reference from the Capability
#: Graph and the identity it names cannot disagree on form.
IDENTIFIER = re.compile(r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9_-]*)*$")

#: A secret HANDLE: an opaque identifier, never a value. Deliberately narrow, so
#: a key pasted into the configuration field cannot pass as a handle.
HANDLE = re.compile(r"^[a-z][a-z0-9._-]{2,63}$")

#: Raw-secret shapes, refused wherever free-form provider metadata is accepted.
#: Detection proves the boundary holds; it never sanitises a value into
#: acceptability, which is why the match raises instead of stripping.
_RAW_SECRET_SHAPES = re.compile(
    r"(?i)(-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9]{16,}|"
    r"\bghp_[A-Za-z0-9]{20,}|\bAKIA[0-9A-Z]{16}\b)"
)


def _strings_in(value: object) -> tuple[str, ...]:
    """Every string a field holds, whether it is one or a tuple of them.

    Derived rather than field-by-field, so a concern the canonical map adds
    later is scanned the day it appears, in either shape.
    """
    if isinstance(value, str):
        return (value,)
    if isinstance(value, tuple):
        return tuple(item for item in value if isinstance(item, str))
    return ()


class ProviderRecord(BaseModel):
    """One provider, carrying exactly the seven concerns C-11 assigns here.

    Frozen and `extra="forbid"`: a consumer cannot attach an eighth concern, and
    STRICT compatibility means the canonical set adds fields, not callers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: `identity`
    identity: str
    #: `model_identity` - the models this provider serves.
    model_identity: tuple[str, ...] = ()
    #: `configuration` - opaque C-09 secret handles. Never values, never policy
    #: state: the broker owns whether a handle is still usable.
    configuration: tuple[str, ...] = ()
    #: `health` - a state of the canonical ProviderHealth machine.
    health: str = DEFINITION.states[0]
    #: `availability` - free-form, secret-scanned.
    availability: str = ""
    #: `cost_metadata` - free-form, secret-scanned.
    cost_metadata: str = ""
    #: `fallback` - identities of providers to fall back to. References, not copies.
    fallback: tuple[str, ...] = ()

    def validate_record(self) -> None:
        """Refuse a record that could not be a truthful provider record."""
        self._validate_identities()
        self._validate_no_raw_secret()
        self._validate_configuration()
        self._validate_health()

    def _validate_configuration(self) -> None:
        """Handles are opaque identifiers. A value cannot masquerade as one."""
        for handle in self.configuration:
            if not HANDLE.match(handle):
                raise RawSecretInProviderConfiguration(
                    f"{self.identity}: configuration entry {handle!r} is not an "
                    "opaque secret handle. The registry holds C-09 references, "
                    "never values",
                    source=C11_SOURCE,
                )

    def _validate_identities(self) -> None:
        if not IDENTIFIER.match(self.identity):
            raise InvalidProviderIdentity(
                f"provider identity {self.identity!r} is not a dotted lowercase "
                "identifier",
                source=C11_SOURCE,
            )
        for model in self.model_identity:
            if not IDENTIFIER.match(model):
                raise InvalidProviderIdentity(
                    f"{self.identity}: model identity {model!r} is malformed",
                    source=C11_SOURCE,
                )
        for target in self.fallback:
            if not IDENTIFIER.match(target):
                raise InvalidProviderIdentity(
                    f"{self.identity}: fallback {target!r} is not a provider "
                    "identity",
                    source=C11_SOURCE,
                )
            if target == self.identity:
                raise InvalidProviderIdentity(
                    f"{self.identity}: a provider may not fall back to itself",
                    source=C11_SOURCE,
                )

    def _validate_health(self) -> None:
        """The vocabulary is the canonical machine's, read and never restated."""
        if self.health not in DEFINITION.states:
            raise UnknownProviderHealthState(
                f"{self.identity}: health {self.health!r} is not a state of the "
                f"canonical {DEFINITION.machine} machine; its states are "
                f"{list(DEFINITION.states)}",
                source=DEFINITION.authoritative_source,
            )

    def _validate_no_raw_secret(self) -> None:
        """Scan every free-form string this record carries.

        The fields are DERIVED from the model rather than named, so a concern
        the canonical map adds later is scanned the day it appears. Naming them
        here would also have restated part of the owned-concern vocabulary,
        which is the one thing this context must never do - a control caught
        exactly that in the first draft.
        """
        for field, value in self.__dict__.items():
            for candidate in _strings_in(value):
                if _RAW_SECRET_SHAPES.search(candidate) is None:
                    continue
                raise RawSecretInProviderConfiguration(
                    f"{self.identity}: {field} carries something shaped like a "
                    "raw secret. Provider configuration holds C-09 references, "
                    "never values",
                    source=C11_SOURCE,
                )

