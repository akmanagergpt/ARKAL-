"""Admission condition (a): the capability must resolve, not be unconfigured.

Owner: `execution.scheduler`.

THE CANONICAL PREDICATE, WORD FOR WORD. `EXECUTION_AND_CAPABILITY.md` §4 admits
a job only when "its capability resolves other than `NOT_CONFIGURED`". That is
the predicate implemented here: `state is not NOT_CONFIGURED`. It is deliberately
NOT narrowed to `state is PASS`, which would be a stricter rule than the
canonical set states and therefore just as much an invention as a weaker one.
Post-activation resolution semantics belong to Phase 9B, which owns the graph.

NO SECOND CAPABILITY AUTHORITY. This module holds no capability registry, no
node set, no configured-state vocabulary and no resolution logic. It forwards a
question to `control.capability` and returns that context's own
`CapabilityQueryResult` unchanged, so the verdict a caller sees is the one the
authority produced. `execution.scheduler` is rank 3 and `control.capability` is
rank 1, so the dependency runs strictly downward.

NO CACHED VERDICT - THIS IS LOAD-BEARING. §1 names `execution.scheduler` at
Phase 8 as a consumer that "must handle `NOT_CONFIGURED` and must not cache
capability verdicts". This object therefore stores the RESOLVER and never a
result: there is no verdict field, no memoisation and no "last answer", so every
evaluation is a fresh question to the authority. A cached `NOT_CONFIGURED` would
be merely stale; a cached success surviving past activation, or past a
configuration change, would be a fabricated permission.

ACTIVATION IS NOT THIS CONTEXT'S BUSINESS. The scheduler never calls `activate`,
never reads or writes `configured_state`, and judges no phase. `CapabilityGraph`
already takes its activation phase and current phase from the caller as
authoritative state and "judges neither"; this module follows the same rule one
level up, which is why it depends on the resolver protocol rather than on any
phase fact.
"""

from __future__ import annotations

from typing import Protocol

from arkali.control.capability.capability_graph import CapabilityQueryResult
from arkali.kernel.contracts.results import HonestState


class CapabilityResolver(Protocol):
    """The one question this context asks of `control.capability`.

    A Protocol rather than the concrete class, so the scheduler depends on the
    canonical *question* and cannot reach the graph's construction, validation
    or activation surface. `CapabilityGraph` satisfies it structurally.
    """

    def can_perform(self, capability_id: str) -> CapabilityQueryResult:
        ...


def resolves(result: CapabilityQueryResult) -> bool:
    """Condition (a), exactly as §4 words it."""
    return result.state is not HonestState.NOT_CONFIGURED


class CapabilityAdmission:
    """Asks the canonical authority whether a capability resolves.

    Holds the authority, never its answer.
    """

    def __init__(self, resolver: CapabilityResolver) -> None:
        self._resolver = resolver

    def evaluate(self, capability_id: str) -> CapabilityQueryResult:
        """Ask the authority. Every call is a fresh question.

        An unknown capability raises `control.capability`'s own
        `InvalidCapabilityReference`, unchanged: that context owns capability
        identity, and converting a typo into a governed `NOT_CONFIGURED` answer
        would let a misspelling look like a determinate pre-activation result.
        """
        return self._resolver.can_perform(capability_id)
