"""The canonical provider-authority declaration, parsed.

Owner: `control.registry.provider`.

NO SHADOW MODEL. This module names none of the seven owned concerns and none of
the reference-only consumers. Both lists, the owner and the copying/caching
permissions are parsed from `AUTHORITY_MAP.yaml` `provider_authority` at call
time, so the canonical map alone decides what this registry owns. A private copy
here would be the F-0013 defect applied to the very requirement this phase
exists to satisfy - ARK-REQ-0052 says the Registry is the *sole authority*, and a
registry that transcribed its own scope would be asserting that scope rather
than deriving it.

WHY THE MAP AND NOT THE MASTER SPECIFICATION. `MS §Provider and Agent
separation` states the rule in prose - "sole canonical authority for provider
identity, model identity, provider configuration, health, availability, cost
metadata and provider fallback configuration" - and `AUTHORITY_MAP.yaml` is the
machine-readable declaration of exactly that, which ADR-0001 makes the artifact
all eight architecture gates evaluate against. Reading the map is reading the
same rule in the form the repository already treats as authoritative.

THIS MODULE GRANTS NOTHING. It reports what the map declares. It does not decide
whether a consumer is behaving, which is the `shadow_registry` gate's question
and, for source-level enforcement, a later Phase 9 package's.
"""

from __future__ import annotations

import pathlib
from typing import Any, Final

import yaml

from arkali.kernel.contracts.error_base import AuthoritativeSourceError

AUTHORITY_MAP_RELPATH: Final[str] = "docs/canonical/AUTHORITY_MAP.yaml"
SECTION: Final[str] = "provider_authority"


class ProviderAuthority:
    """What `AUTHORITY_MAP.yaml` declares about provider ownership."""

    def __init__(self, raw: dict[str, Any], source_path: str) -> None:
        self._raw = raw
        self.source_path = source_path
        for key in ("owner", "fields_owned", "reference_only_consumers"):
            if key not in raw:
                raise AuthoritativeSourceError(
                    f"{SECTION} section missing {key!r}", source=source_path
                )
        if not raw["fields_owned"]:
            raise AuthoritativeSourceError(
                f"{SECTION} declares no owned concern; a registry that owns "
                "nothing cannot be a sole authority",
                source=source_path,
            )

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> ProviderAuthority:
        path = repo_root / AUTHORITY_MAP_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError("authority map not found", source=str(path))
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or SECTION not in raw:
            raise AuthoritativeSourceError(
                f"authority map declares no {SECTION} section", source=str(path)
            )
        return cls(raw[SECTION], str(path))

    @property
    def owner(self) -> str:
        return str(self._raw["owner"])

    def owned_concerns(self) -> tuple[str, ...]:
        """The concerns ARK-REQ-0052 makes this registry the sole authority for."""
        return tuple(self._raw["fields_owned"])

    def reference_only_consumers(self) -> tuple[str, ...]:
        """Contexts that may hold a reference and never a copy (ARK-REQ-0053)."""
        return tuple(self._raw["reference_only_consumers"])

    @property
    def copying_permitted(self) -> bool:
        return bool(self._raw.get("copying_permitted", False))

    @property
    def caching_permitted(self) -> bool:
        return bool(self._raw.get("caching_permitted", False))

    def owns(self, concern: str) -> bool:
        return concern in self.owned_concerns()
