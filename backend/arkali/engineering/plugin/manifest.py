"""C-30 plugin manifest domain contract (ARK-REQ-0164).

Owner: engineering.plugin.

MANIFEST/PERMISSION/VERSION GOVERNED. Version is validated against semver
2.0.0 (`CONTRACT_INVENTORY.md` row C-30: versioning is `semver`). Declared
permissions are carried here as opaque strings - `engineering.plugin`
declares no operation-class vocabulary of its own.
`control.policy.operation_class.OperationClassVocabulary` remains the sole
store of the fourteen canonical classes (its own docstring: "Plugin
manifests use this same vocabulary. There is no separate plugin permission
list."); a private copy here would be the F-0013 shadow-model defect applied
to security. Mapping declared permissions against that live vocabulary is
wired through the pre-existing `permission_mapping_guard` on the
`PluginLifecycle` state machine's `PERMISSIONS_DECLARED -> APPROVED`
transition (`plugin_lifecycle_state_machine.py`, built Phase 3, unmodified
by this module) - not re-implemented here.

C-30 IS `MANIFEST`: no table, no migration, no ORM record - the same shape
C-29's `INT` category established for content-addressed, frozen domain
objects with no DB persistence (`engineering.import.contracts`).
"""

from __future__ import annotations

import json
import re
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arkali.engineering.plugin.content_ref import address_of
from arkali.engineering.plugin.errors import PluginManifestVersionError

CONTRACT_VERSION: Final[str] = "1.0.0"

#: Semver 2.0.0 (semver.org #13); CONTRACT_INVENTORY.md row C-30 "semver".
_SEMVER: Final[re.Pattern[str]] = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

Declared = Annotated[str, Field(min_length=1)]


def is_semver(candidate: str) -> bool:
    """Whether `candidate` is a valid semver 2.0.0 version string."""
    return bool(_SEMVER.match(candidate))


class PluginManifest(BaseModel):
    """The C-30 manifest: one plugin revision's declared identity, version
    and requested permissions - the whole of what a third-party plugin
    submits before the `PluginLifecycle` machine evaluates it."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    contract_version: str = CONTRACT_VERSION
    plugin_id: Declared
    name: Declared
    version: Declared
    #: Requested permissions, as declared by the plugin author. Opaque
    #: strings here; mapped against the live 14-class vocabulary elsewhere
    #: (`control.policy.operation_class`), never duplicated in this context.
    declared_permissions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _version_is_semver(self) -> PluginManifest:
        if not is_semver(self.version):
            raise PluginManifestVersionError(
                f"plugin {self.plugin_id!r} declares version {self.version!r}, "
                "which is not valid semver 2.0.0 (CONTRACT_INVENTORY.md row "
                "C-30: versioning is semver)"
            )
        return self

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def manifest_ref(self) -> str:
        return address_of(self.rendering())


__all__ = ["PluginManifest", "CONTRACT_VERSION", "is_semver"]
