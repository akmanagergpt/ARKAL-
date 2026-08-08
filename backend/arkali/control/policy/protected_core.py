"""Protected Core boundary enforcement (ARK-REQ-0110, 0112, 0071, 0236).

Owner: control.policy (Protected Core) — enforcement; `control.architecture`
owns membership (`AUTHORITY_MAP.yaml` `protected_core: true`).

NO DUPLICATE PROTECTED-PATH LIST. Membership is parsed from the authority map at
call time. This module names no context and no path. A private list here would be
the shadow-model defect applied to the one boundary that makes acceptance
independence structural: an actor that could maintain its own copy of "what is
protected" could quietly shrink it.

WHAT PHASE 4 ENFORCES. That a direct mutation of a Protected Core path is
refused, and that the only declared route is the Stable Core candidate lifecycle
with HUMAN GATE 2 recorded. Phase 4 does **not** implement promotion, the
candidate lifecycle or the stronger verification profile — those belong to later
phases. It establishes the boundary; it does not build what passes through it.

ARK-REQ-0112 is enforced by omission as much as by code: there is no function
here that adds to, removes from or reinterprets membership.
"""

from __future__ import annotations

import pathlib

from pydantic import BaseModel, ConfigDict

from arkali.control.policy.authority_source import (
    load_authority_map,
    refuse,
    require_section,
)
from arkali.control.policy.policy_errors import (
    HumanGateNotRecorded,
    ProtectedCoreMutation,
)
#: The gate the canonical set requires for a Protected Core change (ADR-0005).
REQUIRED_GATE = "HUMAN_GATE_2"


class MutationAttempt(BaseModel):
    """A proposed change to a repository path, described as facts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    actor: str
    #: True only when the change is travelling the Stable Core candidate
    #: lifecycle. An implementing actor cannot set this and also supply the gate:
    #: the gate must be recorded independently.
    via_stable_core_lifecycle: bool = False
    recorded_human_gates: tuple[str, ...] = ()


class ProtectedCoreBoundary:
    """Answers whether a path is protected, and refuses direct mutation."""

    def __init__(self, members: dict[str, str], source_path: str) -> None:
        if not members:
            raise refuse(
                "no protected-core context declared; refusing a vacuous boundary",
                source_path,
            )
        self._members = members
        self.source_path = source_path

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> ProtectedCoreBoundary:
        raw, source = load_authority_map(repo_root)
        contexts = require_section(raw, "contexts", source)
        members = {
            name: meta["module_root"]
            for name, meta in contexts.items()
            if meta.get("protected_core")
        }
        return cls(members, source)

    @property
    def contexts(self) -> tuple[str, ...]:
        return tuple(sorted(self._members))

    @property
    def module_roots(self) -> tuple[str, ...]:
        return tuple(sorted(self._members.values()))

    def owning_context(self, path: str) -> str | None:
        """Which protected context, if any, owns this repository path."""
        normalised = path.replace("\\", "/").lstrip("./")
        best: str | None = None
        best_len = -1
        for name, root in self._members.items():
            if normalised.startswith(root) and len(root) > best_len:
                best, best_len = name, len(root)
        return best

    def is_protected(self, path: str) -> bool:
        return self.owning_context(path) is not None

    def authorize(self, attempt: MutationAttempt) -> str:
        """Return the owning context if the change is legal; otherwise refuse."""
        owner = self.owning_context(attempt.path)
        if owner is None:
            return ""
        if not attempt.via_stable_core_lifecycle:
            raise ProtectedCoreMutation(
                f"{attempt.actor} attempted a direct change to {attempt.path!r}, "
                f"owned by protected-core context {owner!r}. The only declared "
                "route is the Stable Core candidate lifecycle under the stronger "
                "verification profile (ADR-0005).",
                source=self.source_path,
            )
        if REQUIRED_GATE not in attempt.recorded_human_gates:
            raise HumanGateNotRecorded(
                f"a change to {attempt.path!r} ({owner}) requires "
                f"{REQUIRED_GATE}; no recorded decision was supplied. The gate "
                "is never self-accepted by the actor making the change.",
                source=self.source_path,
            )
        return owner
