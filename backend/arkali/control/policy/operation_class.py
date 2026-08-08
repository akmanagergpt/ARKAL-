"""C-08 Computer-Use operation class vocabulary (ARK-REQ-0171 … 0175).

Owner: control.policy (Protected Core).

NO SHADOW SECURITY MODEL. The fourteen classes, their defaults, their fixed
rules and `unmapped_action_resolution` are parsed from `AUTHORITY_MAP.yaml` at
call time. This module contains no class name and no decision value of its own,
so the canonical map alone decides what exists and how it resolves. A private
copy here would be the F-0013 defect applied to security.

The per-tier resolution matrix lives in `SECURITY_ARCHITECTURE.md` §2 and is
parsed by `security_matrix.py`. The two are reconciled by a permanent test:
neither is allowed to drift from the other.

Plugin manifests use this same vocabulary. There is no separate plugin
permission list (SECURITY_ARCHITECTURE.md §2).
"""

from __future__ import annotations

import enum
import pathlib
from typing import Any

from pydantic import BaseModel, ConfigDict

from arkali.control.policy.authority_source import (
    load_authority_map,
    refuse,
    require_section,
)
from arkali.control.policy.policy_errors import UnknownOperationClass


class Decision(str, enum.Enum):
    """The only three answers a policy decision may take."""

    AUTO = "AUTO"
    ASK_USER = "ASK_USER"
    DENY = "DENY"


class OperationClassRule(BaseModel):
    """One canonical class with its declared default and fixed rule."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    default: Decision
    fixed: str | None = None

    @property
    def is_always_denied(self) -> bool:
        return self.fixed == "DENY"

    @property
    def never_auto(self) -> bool:
        """Fixed rules that forbid AUTO unconditionally, at every tier.

        `NEVER_AUTO_OUTSIDE_PREAUTHORIZED_SCOPE` is deliberately absent: it
        forbids AUTO *outside* a pre-authorized scope, and the canonical matrix
        grants AUTO to `ACCESS_SECRET` inside scope at TRUST-0/1. Treating it as
        unconditional would be stricter than the canonical set, which is still a
        misreading of it - the scope condition is enforced separately.
        """
        return self.fixed in ("DENY", "NEVER_AUTO", "RECOVERY_SUPERVISOR_ONLY")

    @property
    def denied_in_local_only(self) -> bool:
        return self.fixed == "DENY_IN_LOCAL_ONLY"


class OperationClassVocabulary:
    """The canonical vocabulary. Construct with `load`; never populated by hand."""

    def __init__(
        self, rules: dict[str, OperationClassRule], unmapped: Decision, source: str
    ) -> None:
        self._rules = rules
        self.unmapped_resolution = unmapped
        self.source_path = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> OperationClassVocabulary:
        raw, source = load_authority_map(repo_root)
        return cls._from_raw(raw, source)

    @classmethod
    def _from_raw(cls, raw: dict[str, Any], source: str) -> OperationClassVocabulary:
        declared = require_section(raw, "operation_classes", source)
        rules = {
            name: OperationClassRule(
                name=name,
                default=Decision(meta["default"]),
                fixed=meta.get("fixed"),
            )
            for name, meta in declared.items()
        }
        unmapped_raw = raw.get("unmapped_action_resolution")
        if unmapped_raw is None:
            raise refuse(
                "authority map declares no unmapped_action_resolution", source
            )
        return cls(rules, Decision(unmapped_raw), source)

    def __len__(self) -> int:
        return len(self._rules)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._rules))

    def get(self, name: str) -> OperationClassRule:
        """An unmappable action is refused, never treated as unclassified."""
        rule = self._rules.get(name)
        if rule is None:
            raise UnknownOperationClass(
                f"action {name!r} maps to no canonical operation class; "
                f"unmapped_action_resolution is "
                f"{self.unmapped_resolution.value}",
                source=self.source_path,
            )
        return rule

    def contains(self, name: str) -> bool:
        return name in self._rules
