"""ARK-REQ-0240: deterministic transformers execute inside the candidate
lifecycle only.

Owner: control.policy. This module is `engineering.repair`'s CONSUMER of that
authority, not a second one — the same shape `engineering.agent.agent_role`
already uses for `ARK-REQ-0051`.

BP §Deterministic repair: "Mechanical, unambiguous fixes should use narrow,
idempotent, tested, versioned deterministic transformers. Transformers execute
inside the candidate lifecycle only; a transformer may never write to a Stable
Core or Stable Product revision."

THE CONFINEMENT RULE IS NOT WRITTEN HERE; IT IS DERIVED. `AUTHORITY_MAP.yaml`
`stable_mutation.prohibited_actors` already names `deterministic_transformer`
— it was added for MS §Constitution 6 ("No actor or mechanism may directly
mutate a Stable Core or Stable Product revision. This includes ... deterministic
transformers ...") before this phase existed. `direct_mutation_permitted_by` is
empty by design, so no actor — including this one — may ever perform a direct
Stable write; the only path to Stable is the canonical `required_path`
(candidate → verification → acceptance → promotion). Confining a transformer
to "inside the candidate lifecycle" and refusing it a direct Stable write are
the same rule stated two ways.

REUSED, NOT DUPLICATED. `control.policy.agent_authority.AgentAuthority`
already parses this exact section of `AUTHORITY_MAP.yaml` and already exposes
`assert_may_directly_mutate_stable(actor)`, generic over the actor label — it
is not specific to `ai_agent` despite its module name. Writing a second parser
of `stable_mutation` here would be the F-0013 defect the rest of this
codebase refuses; this module holds no copy of `prohibited_actors`,
`direct_mutation_permitted_by` or `required_path`, only the one actor label
`ARK-REQ-0240` concerns.

NO LIFECYCLE, RELEASE, STABLE-MUTATION OR ACCEPTANCE AUTHORITY LIVES HERE.
This module cannot promote, accept, roll back or write Stable — it can only
ask `control.policy` whether a named actor may, and the live answer is always
no. `engineering.candidate`'s isolated workspace (C-25) is a same-layer
context this module does not and may not import (`allow_same_layer: false`);
confinement to candidate is therefore enforced at the actor level, exactly as
`ARK-REQ-0051` is, not by inspecting a filesystem path this context has no
authority to name.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.control.policy.agent_authority import AgentAuthority

#: The actor label `ARK-REQ-0240` concerns, spelled exactly as
#: `AUTHORITY_MAP.yaml` `stable_mutation.prohibited_actors` declares it. Not a
#: second copy of the governed list — the one identity this context presents
#: to `control.policy`, the same way `AgentRole.actor` presents `"ai_agent"`.
ACTOR: Final[str] = "deterministic_transformer"

Declared = Annotated[str, Field(min_length=1)]


class DeterministicTransformer(BaseModel):
    """A narrow, idempotent, tested, versioned mechanical fix.

    Carries identity only — no candidate reference, no target path, no Stable
    authority of any kind. Confinement is judged by `control.policy`, never by
    this object: it does not decide whether it may write, it asks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    name: Declared
    version: Declared

    def assert_confined_to_candidate_lifecycle(self, authority: AgentAuthority) -> None:
        """Refuse this transformer a direct Stable mutation.

        Delegated entirely to `control.policy`'s `AgentAuthority` — this
        context does not judge itself. `direct_mutation_permitted_by` is
        empty by design, so this refusal is unconditional for every actor,
        `"deterministic_transformer"` included: the only way work performed
        by this actor reaches Stable is the canonical required path, never a
        direct write this method could be asked to permit.
        """
        authority.assert_may_directly_mutate_stable(ACTOR)
