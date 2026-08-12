"""ARK-REQ-0050: agents are roles, providers are backends, separation maintained.

Phase 10 Package 3. The register assigns evidence key `arch`, so these are
architecture controls over the real repository rather than behavioural tests of
one object: what matters is that the separation cannot be violated, not that a
particular role happens not to violate it today.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any, Final

import pytest
import yaml
from pydantic import ValidationError

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.authority_gates import ShadowRegistryGate
from arkali.control.architecture.gates.base import GateContext
from arkali.control.policy.agent_authority import AgentAuthority
from arkali.engineering.agent.agent_role import AgentRole
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
OWNER: Final[pathlib.Path] = REPO / "backend/arkali/engineering/agent"
AUTHORITY_MAP: Final[str] = "docs/canonical/AUTHORITY_MAP.yaml"


def provider_authority_block() -> dict[str, Any]:
    raw: Any = yaml.safe_load((REPO / AUTHORITY_MAP).read_text(encoding="utf-8"))
    return dict(raw["provider_authority"])


def owner_modules() -> list[pathlib.Path]:
    return sorted(p for p in OWNER.rglob("*.py") if p.name != "__init__.py")


class TestTheContextIsADeclaredReferenceOnlyConsumer:
    def test_the_canonical_map_names_this_context(self) -> None:
        """Derived, not assumed: the gate reads this list, so being on it is
        what puts this context under the shadow-registry rule at all."""
        block = provider_authority_block()
        assert "engineering.agent" in block["reference_only_consumers"]
        assert block["copying_permitted"] is False
        assert block["caching_permitted"] is False

    def test_the_live_shadow_registry_gate_passes_over_this_context(self) -> None:
        """The real gate, over the real repository, after Package 3's modules."""
        result = ShadowRegistryGate().evaluate(
            GateContext(REPO, AuthorityMap.load(REPO))
        )
        assert result.state is HonestState.PASS, result.detail

    def test_no_owned_provider_concern_appears_as_a_field_here(self) -> None:
        """The concern names come from the map, never from a list written here."""
        owned = {str(name) for name in provider_authority_block()["fields_owned"]}
        assert owned, "an empty owned set would make this control vacuous"
        carried = set(AgentRole.model_fields)
        assert not (owned & carried), f"role carries owned concern(s): {owned & carried}"


class TestARoleIsNotAProviderStore:
    def test_the_role_carries_references_and_nothing_else_about_a_backend(
        self,
    ) -> None:
        assert "provider_refs" in AgentRole.model_fields
        for forbidden in ("health", "availability", "cost", "model", "config"):
            assert not any(
                forbidden in name for name in AgentRole.model_fields
            ), forbidden

    def test_an_undeclared_provider_attribute_cannot_be_attached(self) -> None:
        with pytest.raises(ValidationError, match="provider_health"):
            AgentRole(
                role="Backend Engineer", actor="ai_agent",
                provider_health="HEALTHY",  # type: ignore[call-arg]
            )

    def test_a_role_is_immutable(self) -> None:
        role = AgentRole(role="Backend Engineer", actor="ai_agent")
        with pytest.raises(ValidationError):
            role.provider_refs = ("added-later",)

    def test_no_module_in_this_context_retains_anything_provider_derived(
        self,
    ) -> None:
        """Structural no-store: a provider value may be referenced, never kept.

        Targeted at the real risk - a role caching backend state and becoming a
        second registry - rather than at the shape of any dictionary. A first
        draft flagged every dict with two string keys and caught C-23's
        deterministic JSON rendering, which is a serialisation and not a store;
        that control was replaced rather than suppressed, because a control that
        cries wolf is one a future reader will disable.
        """
        offenders: list[str] = []
        for path in owner_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = (
                    node.targets if isinstance(node, ast.Assign) else [node.target]
                )
                if not any(isinstance(t, ast.Attribute) for t in targets):
                    continue
                value = getattr(node, "value", None)
                if value is None:
                    continue
                if "provider" in ast.unparse(value).lower():
                    offenders.append(f"{path.name}:{node.lineno}")
        assert not offenders, f"provider-derived value retained: {offenders}"


class TestOneRoleMayUseManyBackends:
    def test_a_role_may_declare_several_providers(self) -> None:
        """`A Backend Engineer role may use Claude, GPT, Gemini or a local
        model` - so the relationship is one-to-many by construction."""
        role = AgentRole(
            role="Backend Engineer", actor="ai_agent",
            provider_refs=("p-claude", "p-gpt", "p-gemini", "p-local"),
        )
        assert all(role.may_run_on(ref) for ref in role.provider_refs)
        assert not role.may_run_on("p-unbound")

    def test_the_same_provider_may_serve_several_roles(self) -> None:
        shared = "p-claude"
        roles = [
            AgentRole(role=name, actor="ai_agent", provider_refs=(shared,))
            for name in ("Backend Engineer", "QA Engineer", "Architect")
        ]
        assert all(r.may_run_on(shared) for r in roles)
        assert len({r.role for r in roles}) == len(roles)

    def test_a_role_with_no_backend_bound_is_legal(self) -> None:
        """A role exists independently of any backend; that is the separation."""
        assert AgentRole(role="Architect", actor="ai_agent").provider_refs == ()


class TestTheRoleDoesNotJudgeItsOwnProhibitions:
    def test_the_prohibitions_are_delegated_to_control_policy(self) -> None:
        """A role enforcing the rule that constrains it is the actor grading
        its own paper. ARK-REQ-0051 is owned by control.policy."""
        source = (OWNER / "agent_role.py").read_text(encoding="utf-8")
        assert "AgentAuthority" in source
        code = source.split('"""')[-1]
        assert "prohibited_actors" not in code
        assert "required_path" not in code

    def test_the_delegation_actually_refuses(self) -> None:
        """Delegation that never refuses would be decorative."""
        from arkali.control.policy.policy_errors import (
            CanonicalRequirementMutation,
            SelfAcceptance,
        )

        authority = AgentAuthority.load(REPO)
        role = AgentRole(role="Backend Engineer", actor="ai_agent")
        with pytest.raises(CanonicalRequirementMutation):
            role.assert_may_mutate_canonical_requirements(authority)
        with pytest.raises(SelfAcceptance):
            role.assert_may_accept(authority, producer="ai_agent")

    def test_a_role_may_be_accepted_by_a_different_actor(self) -> None:
        authority = AgentAuthority.load(REPO)
        role = AgentRole(role="Backend Engineer", actor="ai_agent")
        role.assert_may_accept(authority, producer="human_acceptance_authority")
