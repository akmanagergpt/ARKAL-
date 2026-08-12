"""Phase 10 composed journey — the bounded harness task, end to end.

The smallest journey that proves Phase 10's five obligations COMPOSE over real
repository mechanisms. Every authority is loaded from the canonical documents,
the architecture gate is the shipping gate, and the policy authority is the real
one from `control.policy`.

WHAT THIS DELIBERATELY DOES NOT DO. Nothing here contacts a provider, opens a
socket, dispatches work, executes a task or runs an agent. Phase 10 delivers the
CONTRACTS a bounded engineering task is made of and the prohibitions that govern
the actor performing it; it does not deliver a runtime, and a journey that
simulated one would claim capability this phase did not build.

The journey is one narrative in seven steps:

  1. the harness elements come from BOTH canonical documents, reconciled;
  2. a task that omits any element cannot be constructed at all;
  3. the context package admits only canonical kinds and records provenance;
  4. no raw secret can reach the context package, via the C-09 guard;
  5. the task and its context bind through a content address C-14 can consume;
  6. a role is an engineering identity that holds references to backends, never
     backend state;
  7. the role's prohibitions are decided by `control.policy`, not by the role.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Any, Final

import pytest
from pydantic import ValidationError

from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.authority_gates import ShadowRegistryGate
from arkali.control.architecture.gates.base import GateContext
from arkali.control.policy.agent_authority import AgentAuthority
from arkali.control.policy.policy_errors import (
    CanonicalRequirementMutation,
    RawSecretLeak,
    SelfAcceptance,
)
from arkali.control.specification.register_parser import RequirementRegister
from arkali.engineering.agent.agent_role import AgentRole
from arkali.engineering.agent.context_kinds import ContextKindAuthority
from arkali.engineering.agent.context_package import ContextItem, ContextPackage
from arkali.engineering.agent.errors import MalformedHarnessElement
from arkali.engineering.agent.harness_elements import HarnessElementAuthority
from arkali.engineering.agent.harness_task import HarnessTask
from arkali.kernel.contracts.content_address import is_address
from arkali.kernel.contracts.results import HonestState

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PHASE: Final[str] = "10"
#: A real raw-secret shape the C-09 guard recognises. Not a secret.
FAKE_KEY: Final[str] = "sk-" + "A1b2C3d4E5f6G7h8"


@pytest.fixture(scope="module")
def elements() -> HarnessElementAuthority:
    return HarnessElementAuthority.load(REPO)


@pytest.fixture(scope="module")
def kinds() -> ContextKindAuthority:
    return ContextKindAuthority.load(REPO)


@pytest.fixture(scope="module")
def policy() -> AgentAuthority:
    return AgentAuthority.load(REPO)


def context(kinds: ContextKindAuthority, **overrides: Any) -> ContextPackage:
    fields: dict[str, Any] = {
        "package_id": "ctx-7f3a",
        "task_id": "task-91",
        "items": (
            ContextItem(
                kind=kinds.kinds()[0],
                identifier="backend/arkali/engineering/agent/harness_task.py",
                origin="repository revision 1a29e78",
            ),
        ),
    }
    fields.update(overrides)
    return ContextPackage.compiled(kinds, **fields)


def task(**overrides: Any) -> HarnessTask:
    fields: dict[str, Any] = {
        "task_specification": "add the /health route and its test",
        "context_package": "ctx-7f3a",
        "tools": ("read_file", "write_file"),
        "permissions": ("READ_FILE",),
        "workspace": "ws-ephemeral-12",
        "environment": "python-3.13.15",
        "acceptance_target": "tests/surfaces/test_health.py passes",
        "repair_budget": 3,
    }
    fields.update(overrides)
    return HarnessTask(**fields)


class TestPhase10Journey:
    """One narrative. Each step depends on the one before it holding."""

    def test_step_1_the_elements_come_from_both_canonical_documents(
        self, elements: HarnessElementAuthority
    ) -> None:
        """Neither document may be ignored; both are canonical sources."""
        assert len(elements.sources) == 2
        assert len(elements) >= 2, "a vacuous element list proves nothing"
        HarnessTask.reconcile_with_authority(elements)
        assert HarnessTask.element_fields() == elements.field_names()

    @pytest.mark.parametrize("omitted", list(HarnessTask.element_fields()))
    def test_step_2_a_task_missing_any_element_cannot_exist(
        self, omitted: str
    ) -> None:
        """Boundedness is structural: there is no unbounded task to audit."""
        incomplete = {k: v for k, v in task().__dict__.items() if k != omitted}
        with pytest.raises(ValidationError, match=omitted):
            HarnessTask(**incomplete)

    def test_step_3_context_admits_only_canonical_kinds_with_provenance(
        self, kinds: ContextKindAuthority
    ) -> None:
        built = context(kinds)
        assert all(kinds.admits(item.kind) for item in built.items)
        assert all(item.origin for item in built.items)
        with pytest.raises(MalformedHarnessElement, match="not admissible"):
            context(
                kinds,
                items=(
                    ContextItem(
                        kind="slack messages", identifier="x", origin="somewhere"
                    ),
                ),
            )

    def test_step_4_no_raw_secret_can_reach_the_context_package(
        self, kinds: ContextKindAuthority
    ) -> None:
        """The C-09 guard, reached through the shipping contract."""
        with pytest.raises(RawSecretLeak, match="context package"):
            context(
                kinds,
                items=(
                    ContextItem(
                        kind=kinds.kinds()[0], identifier="x", origin=FAKE_KEY
                    ),
                ),
            )

    def test_step_5_the_task_and_its_context_bind_by_content_address(
        self, kinds: ContextKindAuthority
    ) -> None:
        """`ArtifactProvenanceRecord.context_hash` consumes exactly this."""
        built = context(kinds)
        bound = task(context_package=built.package_id)
        assert bound.context_package == built.package_id
        assert is_address(built.context_hash)
        changed = context(
            kinds,
            items=(
                ContextItem(
                    kind=kinds.kinds()[0], identifier="other.py", origin="rev"
                ),
            ),
        )
        assert built.context_hash != changed.context_hash

    def test_step_6_a_role_holds_references_never_backend_state(self) -> None:
        role = AgentRole(
            role="Backend Engineer",
            actor="ai_agent",
            provider_refs=("p-claude", "p-gpt", "p-local"),
        )
        assert all(role.may_run_on(ref) for ref in role.provider_refs)
        assert not role.may_run_on("p-unbound")
        result = ShadowRegistryGate().evaluate(
            GateContext(REPO, AuthorityMap.load(REPO))
        )
        assert result.state is HonestState.PASS, result.detail

    def test_step_7_the_prohibitions_are_decided_by_control_policy(
        self, policy: AgentAuthority
    ) -> None:
        """The role delegates; it never judges itself."""
        role = AgentRole(role="Backend Engineer", actor="ai_agent")
        with pytest.raises(CanonicalRequirementMutation):
            role.assert_may_mutate_canonical_requirements(policy)
        with pytest.raises(SelfAcceptance):
            role.assert_may_accept(policy, producer=role.actor)
        role.assert_may_accept(policy, producer="human_acceptance_authority")


class TestTheJourneyClaimsNothingItDidNotDo:
    def test_no_module_in_this_journey_contacts_a_provider(self) -> None:
        """The journey's own IMPORTS may not reach the network.

        Read by AST rather than by substring, or this control would match its
        own vocabulary and pass for the wrong reason (the F-0017 shape).
        """
        tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for stmt in ast.walk(tree):
            if isinstance(stmt, ast.Import):
                imported |= {a.name.split(".")[0] for a in stmt.names}
            elif isinstance(stmt, ast.ImportFrom) and stmt.module:
                imported.add(stmt.module.split(".")[0])
        network = {"httpx", "httpx2", "requests", "urllib", "urllib3", "socket",
                   "aiohttp", "http", "ssl"}
        assert not (imported & network), f"the journey imports {imported & network}"

    def test_no_agent_runtime_or_dispatch_exists_in_this_context(self) -> None:
        """Phase 10 delivers contracts and prohibitions, not a runtime.

        Asserted over the shipping source rather than promised in prose, so a
        dispatcher added later fails this control instead of quietly widening
        what the phase claimed.
        """
        owner = REPO / "backend/arkali/engineering/agent"
        forbidden = ("def dispatch", "def execute", "def run_task", "def invoke")
        offenders = [
            f"{path.name}: {marker}"
            for path in sorted(owner.rglob("*.py"))
            for marker in forbidden
            if marker in path.read_text(encoding="utf-8")
        ]
        assert not offenders, f"runtime surface present: {offenders}"

    def test_the_denominator_is_exactly_the_registers_phase_10_set(self) -> None:
        """Nothing outside the denominator may be claimed by this phase."""
        owned = {r.req_id for r in RequirementRegister.load(REPO).for_phase(PHASE)}
        assert owned == {
            "ARK-REQ-0050", "ARK-REQ-0051", "ARK-REQ-0054", "ARK-REQ-0055",
            "ARK-REQ-0231",
        }, owned

    def test_the_agent_context_does_not_judge_its_own_prohibitions(self) -> None:
        """ARK-REQ-0051 is control.policy's; a control proves it stayed there."""
        source = (
            REPO / "backend/arkali/engineering/agent/agent_role.py"
        ).read_text(encoding="utf-8")
        code = source.split('"""')[-1]
        assert "prohibited_actors" not in code
        assert "required_path" not in code
