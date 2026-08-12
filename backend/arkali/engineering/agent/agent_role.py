"""Agents are roles; providers are backends (ARK-REQ-0050).

Owner: engineering.agent. Concern: `agent_task_bounding_and_context`.

THE SEPARATION, AS THE CANONICAL SET STATES IT. `MS §Provider and Agent
separation`: "Agents are engineering roles. Providers are execution backends. A
Backend Engineer role may use Claude, GPT, Gemini or a local model." So a role is
an engineering identity — what the work IS — and a provider is the backend that
executes it. One role may run on many providers, and the same provider may serve
many roles; neither owns the other.

THE SEPARATION IS STRUCTURAL, NOT DESCRIBED. `AgentRole` has no field that could
hold a provider identity, model identity, configuration, health, availability,
cost metadata or fallback, and `extra="forbid"` means one cannot be attached. It
carries `provider_refs` — REFERENCES, resolved elsewhere at query time — and that
is the whole of its relationship to a backend. A role therefore cannot become a
provider store even by accident, which is what keeps `ARK-REQ-0050` true
structurally rather than by review.

`AUTHORITY_MAP.yaml` already names `engineering.agent` in
`provider_authority.reference_only_consumers`, with `copying_permitted: false`
and `caching_permitted: false`, so the live `shadow_registry` architecture gate
reads this context's source. This module is written to satisfy a gate that
already exists rather than to introduce a second rule about the same thing.

WHAT A ROLE MAY NOT DO IS NOT DECIDED HERE. `ARK-REQ-0051` — an agent cannot
mutate canonical requirements or declare its own output accepted — is owned by
`control.policy`, and `AgentRole.assert_may_accept` DELEGATES to it rather than
re-implementing it. A role that judged its own prohibitions would be the actor
enforcing the rule that constrains it.

A ROLE IS NOT A TASK. C-22 bounds a task; a role is who performs it. The role
carries no task specification, no context package, no workspace and no repair
budget, because duplicating those here would create a second bounding authority.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from arkali.control.policy.agent_authority import AgentAuthority

MS_SOURCE = "MS §Provider and Agent separation (ARK-REQ-0050)"

Declared = Annotated[str, Field(min_length=1)]


class AgentRole(BaseModel):
    """An engineering role. Never a provider, and never a store of one."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    #: The engineering identity, e.g. "Backend Engineer". A role name, never a
    #: model or vendor name - a control asserts the distinction holds.
    role: Declared
    #: The actor label the policy path judges this role by. Kept separate from
    #: `role` because policy reasons about actors and the canonical prohibited
    #: list is a list of actor labels, not of engineering job titles.
    actor: Declared
    #: Provider identifiers this role MAY run on. References only: resolving
    #: them, and everything about their health, cost or availability, belongs to
    #: `control.registry.provider`. `()` is legal and means none is bound yet.
    provider_refs: tuple[str, ...] = ()

    def may_run_on(self, provider_ref: str) -> bool:
        """Whether this role declares that backend. A reference test, not a
        health, availability or capability answer - none of which this context
        may hold or derive."""
        return provider_ref in self.provider_refs

    def assert_may_mutate_canonical_requirements(
        self, authority: AgentAuthority
    ) -> None:
        """Delegated to `control.policy`. This context does not judge itself."""
        authority.assert_may_mutate_canonical_requirements(self.actor)

    def assert_may_accept(self, authority: AgentAuthority, *, producer: str) -> None:
        """Delegated to `control.policy`. This context does not judge itself."""
        authority.assert_may_accept(producer=producer, acceptor=self.actor)
