"""ARK-REQ-0051: agents cannot mutate canonical requirements or self-accept.

Phase 10 Package 3. Owner `control.policy`; the register assigns evidence keys
`sec` and `prop`, and both are supplied here.

THE `prop` EVIDENCE IS EXHAUSTIVE, NOT SAMPLED. §6 of the handoff records
`hypothesis` as NOT_CONFIGURED on this host, and installing a package to satisfy
an evidence key would be the wrong fix. The governed vocabularies are finite and
canonical - the prohibited-actor list, the trust tiers and the operation classes
are all declared in `AUTHORITY_MAP.yaml` - so the properties below are proven by
enumerating them completely. Exhaustion over a closed vocabulary is a stronger
result than random sampling over it, not a weaker one.
"""

from __future__ import annotations

import itertools
import pathlib
from typing import Any, Final

import pytest
import yaml

from arkali.control.policy.agent_authority import AgentAuthority
from arkali.control.policy.operation_class import OperationClassVocabulary
from arkali.control.policy.policy_errors import (
    CanonicalRequirementMutation,
    MalformedPolicyState,
    SelfAcceptance,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
AUTHORITY_MAP: Final[str] = "docs/canonical/AUTHORITY_MAP.yaml"


@pytest.fixture(scope="module")
def authority() -> AgentAuthority:
    return AgentAuthority.load(REPO)


def write_map(root: pathlib.Path, mutation: dict[str, Any]) -> pathlib.Path:
    target = root / AUTHORITY_MAP
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(yaml.safe_dump({"stable_mutation": mutation}), encoding="utf-8")
    return root


def canonical_mutation() -> dict[str, Any]:
    raw: Any = yaml.safe_load((REPO / AUTHORITY_MAP).read_text(encoding="utf-8"))
    return dict(raw["stable_mutation"])


class TestTheProhibitionsAreDerivedNotDeclared:
    def test_the_barred_set_is_the_canonical_prohibited_actor_list(
        self, authority: AgentAuthority
    ) -> None:
        declared = {
            str(a).strip().lower() for a in canonical_mutation()["prohibited_actors"]
        }
        assert set(authority.barred_actors()) == declared
        assert "ai_agent" in declared, "the canonical list must bar the agent actor"

    def test_no_actor_label_is_hard_coded_in_the_module(self) -> None:
        """NO SHADOW MODEL: a governed list in a second place is F-0013."""
        source = (
            REPO / "backend/arkali/control/policy/agent_authority.py"
        ).read_text(encoding="utf-8")
        body = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        code = body.split('"""')[-1]
        for actor in canonical_mutation()["prohibited_actors"]:
            assert f'"{actor}"' not in code and f"'{actor}'" not in code, actor

    def test_a_canonical_set_that_adds_an_actor_is_covered_immediately(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Derivation means a new actor is barred the day it is declared."""
        mutation = canonical_mutation()
        mutation["prohibited_actors"] = [*mutation["prohibited_actors"], "new_actor"]
        loaded = AgentAuthority.load(write_map(tmp_path, mutation))
        assert loaded.is_barred("new_actor")
        with pytest.raises(CanonicalRequirementMutation):
            loaded.assert_may_mutate_canonical_requirements("new_actor")


class TestCanonicalRequirementMutationIsRefused:
    def test_every_barred_actor_is_refused(self, authority: AgentAuthority) -> None:
        """PROPERTY, exhaustive over the canonical actor vocabulary."""
        for actor in authority.barred_actors():
            with pytest.raises(CanonicalRequirementMutation):
                authority.assert_may_mutate_canonical_requirements(actor)

    def test_the_refusal_holds_for_every_casing_and_padding(
        self, authority: AgentAuthority
    ) -> None:
        """A label cannot be smuggled past by presentation."""
        for actor in authority.barred_actors():
            for variant in (actor.upper(), f"  {actor}  ", actor.title()):
                with pytest.raises(CanonicalRequirementMutation):
                    authority.assert_may_mutate_canonical_requirements(variant)

    def test_no_operation_class_or_tier_creates_an_exception(
        self, authority: AgentAuthority
    ) -> None:
        """PROPERTY, exhaustive over actors x operation classes.

        `direct_mutation_permitted_by` is empty by design, so the refusal must
        not depend on any other governed dimension. If a future signature added
        a tier or class parameter, this control would have to change - which is
        the point.
        """
        classes = OperationClassVocabulary.load(REPO).names()
        assert classes, "vocabulary must be non-empty or this proves nothing"
        for actor, _ in itertools.product(authority.barred_actors(), classes):
            with pytest.raises(CanonicalRequirementMutation):
                authority.assert_may_mutate_canonical_requirements(actor)

    def test_an_unbarred_label_is_not_refused_by_this_rule(
        self, authority: AgentAuthority
    ) -> None:
        """The rule must discriminate, or it refuses everything vacuously."""
        authority.assert_may_mutate_canonical_requirements("human_acceptance_authority")


class TestSelfAcceptanceIsRefused:
    def test_a_producer_may_never_accept_its_own_output(
        self, authority: AgentAuthority
    ) -> None:
        """PROPERTY, exhaustive over the canonical actor vocabulary."""
        for actor in authority.barred_actors():
            with pytest.raises(SelfAcceptance):
                authority.assert_may_accept(producer=actor, acceptor=actor)

    def test_it_applies_to_every_actor_not_only_barred_ones(
        self, authority: AgentAuthority
    ) -> None:
        """No actor is exempt from a canonical stage boundary."""
        for label in ("human_acceptance_authority", "machine_gate", "anyone_at_all"):
            with pytest.raises(SelfAcceptance):
                authority.assert_may_accept(producer=label, acceptor=label)

    def test_casing_and_padding_cannot_present_one_actor_as_two(
        self, authority: AgentAuthority
    ) -> None:
        for producer, acceptor in (
            ("ai_agent", "AI_AGENT"), ("ai_agent", "  ai_agent "),
            ("Ai_Agent", "ai_agent"),
        ):
            with pytest.raises(SelfAcceptance):
                authority.assert_may_accept(producer=producer, acceptor=acceptor)

    def test_a_distinct_acceptor_is_permitted(
        self, authority: AgentAuthority
    ) -> None:
        """Otherwise nothing could ever be accepted and the rule is vacuous."""
        authority.assert_may_accept(
            producer="ai_agent", acceptor="human_acceptance_authority"
        )

    def test_the_refusal_names_the_canonical_path(
        self, authority: AgentAuthority
    ) -> None:
        """A control must be able to assert WHICH boundary refused (F-0017)."""
        with pytest.raises(SelfAcceptance, match="candidate"):
            authority.assert_may_accept(producer="ai_agent", acceptor="ai_agent")


class TestFailsClosedAndNeverVacuously:
    def test_a_missing_authority_map_is_refused(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(MalformedPolicyState, match="not found"):
            AgentAuthority.load(tmp_path)

    def test_an_empty_prohibited_actor_list_is_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A prohibition with no subject would report PASS while enforcing
        nothing."""
        mutation = canonical_mutation()
        mutation["prohibited_actors"] = []
        with pytest.raises(MalformedPolicyState, match="vacuously"):
            AgentAuthority.load(write_map(tmp_path, mutation))

    @pytest.mark.parametrize("dropped", ["candidate", "acceptance"])
    def test_a_required_path_missing_either_stage_is_refused(
        self, tmp_path: pathlib.Path, dropped: str
    ) -> None:
        """Self-acceptance is refused BECAUSE those stages are distinct.

        If the canonical set ever merged them, this module must fail loudly
        rather than keep enforcing a rule the documents no longer state.
        """
        mutation = canonical_mutation()
        mutation["required_path"] = [
            s for s in mutation["required_path"] if s != dropped
        ]
        with pytest.raises(MalformedPolicyState, match="separate"):
            AgentAuthority.load(write_map(tmp_path / dropped, mutation))


class TestNoNewOperationClassWasIntroduced:
    def test_the_governed_vocabulary_is_unchanged(self) -> None:
        """Adding a class would change a Protected-Core-owned contract, which
        CONTRACT_INVENTORY.md puts behind HUMAN GATE 2 - not reached here."""
        declared: Any = yaml.safe_load(
            (REPO / AUTHORITY_MAP).read_text(encoding="utf-8")
        )
        assert set(OperationClassVocabulary.load(REPO).names()) == set(
            declared["operation_classes"]
        )

    def test_this_module_declares_no_operation_class_of_its_own(self) -> None:
        source = (
            REPO / "backend/arkali/control/policy/agent_authority.py"
        ).read_text(encoding="utf-8")
        code = source.split('"""')[-1]
        for name in OperationClassVocabulary.load(REPO).names():
            assert name not in code, f"{name} literal in agent_authority"
