"""Admission condition (b): isolation must satisfy what the worker declared.

Owner: `execution.scheduler`.

WHAT §4 REQUIRES. "An isolation composition satisfies its tier." The worker's
declared TRUST tier is resolved by `control.isolation`, which owns tiers,
properties, backends and composition. C-21 also lets a worker declare required
isolation *properties*, and those are part of the same question - what isolation
this worker needs - not a fourth admission condition.

NO COPIED ISOLATION TRUTH. This module holds no tier, no property name, no
backend and no tier-to-property table. It calls `IsolationAuthority.resolve`,
which already refuses to compose a partial answer, and reads the probe results
live. Nothing is stored between evaluations, so a backend that stops being
available cannot keep admitting work on the strength of an old probe.

NEVER SILENTLY UPGRADE A REFUSAL. `resolve` returns `UNSUPPORTED`/`DENY` for a
tier this host cannot satisfy - on the current host that is TRUST-2 and above -
and this module reports that unchanged. It composes no backend of its own,
probes nothing itself, and writes no isolation configuration.

FAIL CLOSED ON AN UNKNOWN TIER. An unrecognised tier raises `control
.isolation`'s `TrustTierViolation`, unchanged. A declaration requiring a property
the canonical set does not define is likewise reported as unmet rather than
ignored: an unknown requirement is not a satisfied one.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from arkali.control.isolation.isolation_contract import (
    BackendDescriptor,
    IsolationAuthority,
    IsolationResolution,
)

#: Supplies the backends currently believed available. Injected so the canonical
#: prober is used in production and no probe result is ever held between calls.
BackendSource = Callable[[], tuple[BackendDescriptor, ...]]


class IsolationAssessment(BaseModel):
    """Whether the declared isolation requirement is satisfiable right now."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tier: str
    satisfied: bool
    missing_for_tier: tuple[str, ...] = ()
    unmet_declared_properties: tuple[str, ...] = ()
    reason: str = ""


class IsolationAdmission:
    """Asks `control.isolation` whether a declaration's isolation can be met."""

    def __init__(self, authority: IsolationAuthority, backends: BackendSource) -> None:
        self._authority = authority
        self._backends = backends

    def evaluate(
        self, tier: str, required_properties: tuple[str, ...]
    ) -> IsolationAssessment:
        """Resolve the tier and check the declared properties, live."""
        available = self._backends()
        resolution = self._authority.resolve(tier, available)
        provided: set[str] = set()
        for backend in available:
            if backend.is_available:
                provided |= set(backend.provides)
        unmet = tuple(sorted(set(required_properties) - provided))
        satisfied = resolution.satisfied and not unmet
        return IsolationAssessment(
            tier=tier,
            satisfied=satisfied,
            missing_for_tier=resolution.missing,
            unmet_declared_properties=unmet,
            reason=self._reason(tier, unmet, resolution),
        )

    @staticmethod
    def _reason(
        tier: str, unmet: tuple[str, ...], resolution: IsolationResolution
    ) -> str:
        """The canonical refusal, reported rather than reworded."""
        if resolution.satisfied and not unmet:
            return f"{tier} is satisfiable by the available isolation composition"
        parts = []
        if resolution.missing:
            parts.append(
                f"{tier} requires unavailable properties {list(resolution.missing)}"
            )
        if unmet:
            parts.append(f"the worker requires unavailable properties {list(unmet)}")
        return (
            f"{'; '.join(parts)} "
            f"({resolution.capability_state.value}/{resolution.execution_decision})"
        )
