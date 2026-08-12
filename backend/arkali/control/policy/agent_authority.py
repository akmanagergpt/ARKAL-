"""Agent prohibitions in the policy path (ARK-REQ-0051).

Owner: control.policy (Protected Core).

WHY THIS LIVES HERE AND NOT IN `engineering.agent`. The register assigns
`ARK-REQ-0051` to `control.policy`, and the reason is structural rather than
clerical: a rule about what an agent may not do, enforced inside the agent
context, is enforced by the actor it constrains. `engineering.agent` is layer
rank 4 and this is rank 1, so the agent context can call this and can never
replace, subclass or shadow it.

THE TWO PROHIBITIONS ARE THE CANONICAL SENTENCE, SPLIT. `MS §Provider and Agent
separation`: "Agents operate under bounded task/context/permissions and cannot
mutate canonical requirements or declare their own output accepted." This module
enforces the second half of that sentence — the two prohibitions — and nothing
else. Boundedness itself is C-22's, already enforced structurally.

NEITHER PROHIBITION IS WRITTEN DOWN HERE; BOTH ARE DERIVED.

  - WHICH ACTORS ARE BARRED comes from `AUTHORITY_MAP.yaml`
    `stable_mutation.prohibited_actors`, the canonical list of actors barred
    from mutating stable state. `ai_agent` is on it. Writing "ai_agent" into
    this module would put a governed value in a second place (F-0013) and would
    silently stop covering an actor the canonical set adds later.
  - WHY SELF-ACCEPTANCE IS REFUSED comes from `stable_mutation.required_path`,
    which lists candidate production and acceptance as SEPARATE stages. An actor
    occupying both collapses a canonical stage boundary. The rule is therefore
    derived from the path's shape, not asserted as a preference — and it is
    checked against the path rather than assumed, so a canonical set that ever
    merged those stages would fail this module loudly instead of leaving it
    enforcing a rule the documents no longer state.

SELF-ACCEPTANCE IS REFUSED FOR EVERY ACTOR, NOT ONLY BARRED ONES. The canonical
sentence constrains agents, and `stable_mutation.direct_mutation_permitted_by`
is empty by design, so no actor is exempt from the stage boundary. Narrowing the
refusal to the barred list would have created an actor label that could accept
its own output simply by not appearing on a list about a different concern.

NO NEW OPERATION CLASS, AND THAT IS DELIBERATE. `AUTHORITY_MAP.yaml` declares
the governed operation classes and `unmapped_action_resolution: DENY` already
makes an unmapped action fail closed. Adding a class here would change a
Protected-Core-owned contract, which `CONTRACT_INVENTORY.md` puts behind HUMAN
GATE 2 — a gate this phase has not reached and may not assume. This module
therefore composes the existing vocabulary and adds none.
"""

from __future__ import annotations

import pathlib
from typing import Any, Final

import yaml

from arkali.control.policy.policy_errors import (
    CanonicalRequirementMutation,
    MalformedPolicyState,
    SelfAcceptance,
)

AUTHORITY_MAP_RELPATH: Final[str] = "docs/canonical/AUTHORITY_MAP.yaml"

#: The two canonical stages whose separation makes self-acceptance a violation.
#: Read out of `required_path` rather than assumed to be present.
_CANDIDATE_STAGE: Final[str] = "candidate"
_ACCEPTANCE_STAGE: Final[str] = "acceptance"


class AgentAuthority:
    """What an agent actor may not do. Construct with `load`."""

    def __init__(
        self,
        barred_actors: frozenset[str],
        required_path: tuple[str, ...],
        source: str,
    ) -> None:
        self._barred = barred_actors
        self._required_path = required_path
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> AgentAuthority:
        path = repo_root / AUTHORITY_MAP_RELPATH
        if not path.is_file():
            raise MalformedPolicyState(
                "authority map not found; refusing to invent the agent "
                "prohibitions",
                source=str(path),
            )
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        mutation = (raw or {}).get("stable_mutation") or {}
        barred = frozenset(
            str(actor).strip().lower()
            for actor in (mutation.get("prohibited_actors") or [])
            if str(actor).strip()
        )
        required_path = tuple(
            str(stage).strip().lower()
            for stage in (mutation.get("required_path") or [])
            if str(stage).strip()
        )
        cls._validate(barred, required_path, str(path))
        return cls(barred, required_path, str(path))

    @staticmethod
    def _validate(
        barred: frozenset[str], required_path: tuple[str, ...], source: str
    ) -> None:
        """Fail closed, and never vacuously.

        An empty barred set would make the first prohibition unfalsifiable, and
        a path missing either stage would remove the ground the second stands
        on. Both are refused rather than defaulted, because a prohibition that
        cannot refuse anything reports PASS while enforcing nothing (F-0016).
        """
        if not barred:
            raise MalformedPolicyState(
                "the authority map declares no prohibited actor; a prohibition "
                "with no subject would pass vacuously",
                source=source,
            )
        missing = [
            stage
            for stage in (_CANDIDATE_STAGE, _ACCEPTANCE_STAGE)
            if stage not in required_path
        ]
        if missing:
            raise MalformedPolicyState(
                f"the canonical required path {list(required_path)} does not "
                f"separate {missing}; self-acceptance is refused because those "
                "stages are distinct, so this rule cannot be enforced without "
                "them",
                source=source,
            )

    def barred_actors(self) -> tuple[str, ...]:
        """Every actor the canonical set bars, in sorted order."""
        return tuple(sorted(self._barred))

    def is_barred(self, actor: str) -> bool:
        return actor.strip().lower() in self._barred

    def assert_may_mutate_canonical_requirements(self, actor: str) -> None:
        """Refuse a barred actor changing the governed requirement set.

        There is no permitted case for a barred actor: `direct_mutation_
        permitted_by` is empty by design, so this never consults a tier, a
        capability or a trust level. A rule with an escape hatch is not this
        rule.
        """
        if self.is_barred(actor):
            raise CanonicalRequirementMutation(
                f"{actor!r} may not mutate a canonical requirement; the "
                "authority map bars it from mutating stable state and "
                "direct_mutation_permitted_by is empty by design",
                source=self.source,
            )

    def assert_may_accept(self, *, producer: str, acceptor: str) -> None:
        """Refuse the producer of an output declaring that output accepted.

        Applies to EVERY actor, not only barred ones: the canonical required
        path separates candidate production from acceptance, and no actor is
        exempt from a stage boundary. Comparison is on the normalised label, so
        casing or surrounding whitespace cannot be used to present one actor as
        two.
        """
        if producer.strip().lower() == acceptor.strip().lower():
            raise SelfAcceptance(
                f"{producer!r} produced this output and may not also accept it; "
                f"the canonical required path {list(self._required_path)} "
                "separates candidate production from acceptance",
                source=self.source,
            )
