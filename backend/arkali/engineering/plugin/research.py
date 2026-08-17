"""C-30 sibling capability: Research (ARK-REQ-0163).

Owner: engineering.plugin.

"Research uses official sources first and never directly mutates
production" (MS §Import / Rescue / Research / Plugins). Two structural
guarantees, neither a domain allowlist this module invents:

1. OFFICIAL SOURCES FIRST. `ResearchSource.kind` is declared by the caller
   from governed data this module does not own - which concrete domains are
   "official" for a given research task is a future provider/domain-pack
   registry concern, out of Phase 21's denominator (`REQUIREMENT_REGISTER.md`
   row ARK-REQ-0163 names evidence keys `sec, prop`, not a data-registry
   requirement). What this module owns and proves is the resolution ORDER:
   `resolve_sources` always attempts every `OFFICIAL` source before any
   `COMMUNITY` source, deterministically, and never silently skips straight
   to an unofficial source while an official one remains untried.

2. NEVER MUTATES PRODUCTION. `ResearchResult.mutation_applied` is
   `Literal[False]` - the same `StaticInspectionReport.executed` idiom Phase
   19 established for a structural, type-level no-execution proof. This
   module imports no persistence-write authority and no stable-mutation
   path; there is no code path here by which a research fetch could reach
   `WRITE_STABLE_FILE`, and `attempt_fetch` never performs a real network
   call itself - it only classifies the attempt and asks the real PDP
   whether it is governed to proceed.

EVERY FETCH IS A GOVERNED `NETWORK_EXTERNAL` OPERATION, decided by the real
PDP through `PolicyDecisionSource` - a structural `Protocol` mirroring
`control.policy.pdp.PolicyDecisionPoint.decide_network_egress` exactly
(primitive facts in, a plain decision string out), not an import: this
context's live edges already reach `control.policy.operation_class`,
`control.policy.workflow_approval` and `control.isolation.isolation_
contract`, and `control.policy.policy_contract` sits at its fan-in ceiling
(15 of 15) - `decide_network_egress`'s own docstring records the identical
constraint. `SECURITY_ARCHITECTURE.md` §2's "DENY in Local-Only" fixed rule
for `NETWORK_EXTERNAL` is therefore enforced by the one real PDP, never
re-declared here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from arkali.engineering.plugin.content_ref import address_of

OFFICIAL: Literal["OFFICIAL"] = "OFFICIAL"
COMMUNITY: Literal["COMMUNITY"] = "COMMUNITY"


@runtime_checkable
class PolicyDecisionSource(Protocol):
    """Structural mirror of `PolicyDecisionPoint.decide_network_egress`."""

    def decide_network_egress(
        self,
        *,
        actor: str,
        trust_tier: str,
        local_only: bool,
        target_is_loopback: bool | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class ResearchSource:
    """One candidate source for a research task. `kind` is declared by the
    caller from governed data this module does not own or invent."""

    name: str
    kind: Literal["OFFICIAL", "COMMUNITY"]
    url: str


@dataclass(frozen=True)
class ResearchResult:
    """The outcome of attempting one source. Structurally read-only:
    `mutation_applied` admits only `False` - no caller of this module can
    construct a result claiming production was mutated."""

    source: ResearchSource
    decision: str
    mutation_applied: Literal[False] = False

    @property
    def permitted(self) -> bool:
        return self.decision == "AUTO"


def resolve_sources(
    sources: tuple[ResearchSource, ...],
) -> tuple[ResearchSource, ...]:
    """Every `OFFICIAL` source, in the order given, before any `COMMUNITY`
    source, in the order given. A stable partition, not a re-sort: relative
    order within each kind is preserved, so this decides only "official
    first," never "which official source first.\""""
    official = tuple(s for s in sources if s.kind == OFFICIAL)
    community = tuple(s for s in sources if s.kind == COMMUNITY)
    return official + community


def attempt_fetch(
    source: ResearchSource,
    policy_source: PolicyDecisionSource,
    *,
    actor: str,
    trust_tier: str,
    local_only: bool,
) -> ResearchResult:
    """Ask the real PDP whether this source's fetch is governed to proceed.

    Never performs a real network call - this module classifies the attempt
    as `NETWORK_EXTERNAL` and records the PDP's decision; the real transport
    is a future capability's concern, and it never authorises itself.
    """
    decision = policy_source.decide_network_egress(
        actor=actor, trust_tier=trust_tier, local_only=local_only,
        target_is_loopback=False,
    )
    return ResearchResult(source=source, decision=decision)


def research_task_ref(*, task: str, sources: tuple[ResearchSource, ...]) -> str:
    """Content address of one research task's declared scope - the same
    provenance idiom every other C-contract's `*_ref` property uses."""
    payload = json.dumps(
        {
            "task": task,
            "sources": [
                {"name": s.name, "kind": s.kind, "url": s.url} for s in sources
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return address_of(payload)


__all__ = [
    "OFFICIAL",
    "COMMUNITY",
    "PolicyDecisionSource",
    "ResearchSource",
    "ResearchResult",
    "resolve_sources",
    "attempt_fetch",
    "research_task_ref",
]
