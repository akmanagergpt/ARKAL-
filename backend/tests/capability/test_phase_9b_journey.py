"""Phase 9B composed journey — the activated Capability Graph, end to end.

The smallest journey that proves the three Phase 9B obligations COMPOSE over real
repository mechanisms. The graph, the reference binding, the resolution, the
verdict, the PDP, the PEP and the `AdmissionService` are all the shipping
classes; the architecture gate is the shipping gate and the register is the
canonical one. Only the node set, the current phase and the injected reference
authorities are fixtures, because `control.capability` takes its authorities by
injection and a composition root is where a test supplies them.

WHAT THIS DELIBERATELY DOES NOT DO, AND THEREFORE DOES NOT CLAIM. Nothing here
contacts a provider, opens a socket, measures live health, meters cost or
produces a provider result of any kind. No production capability is declared
configured with real identities anywhere in this repository; what is proven is
that the MECHANISM resolves, composes and admits. Every affirmative below runs
against composition-root doubles standing in for `control.registry.provider`,
`control.policy`, `control.specification` and `control.isolation` — except the
evidence-requirement authority, which is the real `RequirementRegister` — because
no provider runtime exists and none may be fabricated (D-023).

The journey is one narrative in eight steps:

  1. the activation phase is governed data, read from the register, not a local
     constant;
  2. before it, the query is `NOT_CONFIGURED` and no authority is consulted;
  3. at it, the reference->authority binding is parsed from the canonical block
     and every authority it names is a declared bounded context;
  4. every declared reference is resolved at query time, by a live authority, and
     only then is the answer `PASS`;
  5. the answer is deterministic and nothing is cached, so a changed authority
     answer is observed on the next query;
  6. references never become copies — the question a resolver may be asked cannot
     carry a value, and the live `shadow_registry` gate passes over the context;
  7. `prerequisites` compose transitively, and an unresolved one refuses the
     capability that depends on it;
  8. through the real `AdmissionService`, a fully resolved capability is
     `ADMITTED` and every refusal is `CAPABILITY_NOT_CONFIGURED` — never a state
     Phase 8's unchanged predicate would misread as success.
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib
from typing import Any, Final, cast, get_type_hints

import pytest

from arkali.acceptance.external_result import ExternalProviderResultRule as Rule
from arkali.acceptance.phase_report import PhaseReport, TestExecutionRecord
from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.authority_gates import ShadowRegistryGate
from arkali.control.architecture.gates.base import GateContext
from arkali.control.capability.capability_graph import CapabilityGraph
from arkali.control.capability.reference_resolution import (
    ReferenceResolver,
    ReferenceResolvers,
)
from arkali.control.specification.register_parser import RequirementRegister
from arkali.execution.scheduler.admission_result import AdmissionOutcome
from arkali.execution.scheduler.worker_contract import WorkerDeclaration
from arkali.kernel.contracts.capability_errors import InvalidCapabilityReference
from arkali.kernel.contracts.results import HonestState
from tests.execution.scheduler_admission_harness import (
    ACTIVATION_PHASE,
    PRE_ACTIVATION_PHASE,
    PROFILE,
    activated_graph,
    activated_node,
    binding,
    build_service,
    request,
    resolving_authorities,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PHASE: Final[str] = "9B"
#: `ARK-REQ-0048` carries the activation phase in the register's Phase column.
ACTIVATION_REQUIREMENT: Final[str] = "ARK-REQ-0048"
WORKER: Final[str] = "agent"
#: The only tier this host can satisfy. Condition (b) is not what is under test.
SATISFIABLE_TIER: Final[str] = "TRUST-0"


@pytest.fixture(scope="module")
def register() -> RequirementRegister:
    return RequirementRegister.load(REPO)


def declaration() -> WorkerDeclaration:
    return WorkerDeclaration(
        worker_class=WORKER,
        concurrency_limit=2,
        resource_profile=PROFILE,
        required_trust_tier=SATISFIABLE_TIER,
        required_isolation_properties=(),
        heartbeat_interval=dt.timedelta(seconds=30),
    )


def admit(graph: CapabilityGraph) -> object:
    """Evaluate one request through the SHIPPING AdmissionService."""
    service = build_service(resolver=graph)
    service._contract.declare(declaration())
    return service.evaluate(request(WORKER))


def deny_declared(spies: dict[str, object], *, containing: str = "") -> int:
    """Make composition-root authorities stop resolving; return how many changed.

    Only the `DeclaredSet` doubles hold a mutable identifier set. The
    evidence-requirement authority is the REAL `RequirementRegister`, which this
    journey must not rewrite, so it is skipped rather than silently missed. The
    count is returned because a mutation that changed nothing would make every
    "the refusal was observed" assertion below pass vacuously (F-0017).
    """
    changed = 0
    for spy in spies.values():
        known = getattr(spy, "known", None)
        if not isinstance(known, set):
            continue
        targeted = {r for r in known if containing in r}
        if targeted:
            cast(Any, spy).known = known - targeted
            changed += 1
    return changed


def journey_run(**changes: object) -> TestExecutionRecord:
    fields: dict[str, object] = {
        "command": "journey step",
        "exit_code": 0,
        "passed": 1,
        "failed": 0,
        "summary": "step",
        "external_result": Rule.Declared.NO_EXTERNAL_RESULT,
    }
    fields.update(changes)
    return TestExecutionRecord(**fields)  # type: ignore[arg-type]


def journey_report(*runs: TestExecutionRecord) -> PhaseReport:
    return PhaseReport(
        phase_id=PHASE,
        objective="Phase 9B journey fixture",
        ark_req_ids_closed=(),
        files_created=("x.py",),
        files_modified=(),
        public_contracts=(),
        migrations=(),
        state_machine_capability_changes="none",
        tests_executed=runs,
        architecture_checks="8 gates PASS",
        duplicate_shadow_check="none",
        security_findings="none",
        fake_success_scan="clean",
        evidence_created=("EV-0061",),
        limitations="none",
        blockers="none",
        next_exact_action="continue",
        status=HonestState.PASS,
    )


class TestPhase9BJourney:
    """One narrative. Each step depends on the one before it holding."""

    def test_step_1_the_activation_phase_is_governed_data(
        self, register: RequirementRegister
    ) -> None:
        """No module decides when the graph activates; the register does.

        Hard-coding the phase would be defect class F-0013 applied to the very
        requirement that states it, so the fixture constant is checked against
        the register rather than trusted.
        """
        assert register.get(ACTIVATION_REQUIREMENT).owning_phase == PHASE
        assert ACTIVATION_PHASE == PHASE
        assert PRE_ACTIVATION_PHASE != PHASE

    def test_step_2_before_activation_nothing_is_consulted(self) -> None:
        """Byte-for-byte the Phase 3 answer, even when fully composed.

        The authorities are supplied and would resolve every reference; the
        pre-activation graph must still refuse to ask them, or activation would
        have leaked backwards into an accepted phase.
        """
        node = activated_node(tier=SATISFIABLE_TIER)
        references, spies = resolving_authorities(node)
        graph = activated_graph(
            node, references=references, current_phase=PRE_ACTIVATION_PHASE
        )
        assert graph.is_activated is False
        answer = graph.can_perform(node.id)
        assert answer.state is HonestState.NOT_CONFIGURED
        assert answer.is_determinate, "NOT_CONFIGURED is a determinate answer"
        for name, spy in spies.items():
            assert not spy.asked, f"{name} was consulted before activation"  # type: ignore[attr-defined]

    def test_step_3_the_binding_is_parsed_and_every_authority_is_declared(
        self,
    ) -> None:
        """The reference->authority map comes from the canonical block."""
        declared = binding()
        contexts = set(AuthorityMap.load(REPO).contexts)
        external = declared.external()
        assert external, "no external reference; the rule would be vacuous"
        assert declared.graph_internal(), "the graph would own no reference"
        for reference in external:
            assert reference.authority in contexts, reference.authority

    def test_step_4_pass_requires_every_reference_resolved_by_a_live_authority(
        self,
    ) -> None:
        node = activated_node(tier=SATISFIABLE_TIER)
        references, spies = resolving_authorities(node)
        answer = activated_graph(node, references=references).can_perform(node.id)
        assert answer.state is HonestState.PASS
        assert spies, "no authority declared; this step would be vacuous"
        for name, spy in spies.items():
            assert spy.asked, f"{name} was never asked yet the answer was PASS"  # type: ignore[attr-defined]

    def test_step_4b_an_uncomposed_graph_invents_no_affirmative(self) -> None:
        """At the activation phase, with no authority at all, still a refusal."""
        node = activated_node(tier=SATISFIABLE_TIER)
        answer = activated_graph(node, references=None).can_perform(node.id)
        assert answer.state is HonestState.NOT_CONFIGURED

    def test_step_5_the_answer_is_deterministic_and_never_cached(self) -> None:
        """ARK-REQ-0046's determinism, and ADR-0003's no-cache rule, together."""
        node = activated_node(tier=SATISFIABLE_TIER)
        references, spies = resolving_authorities(node)
        graph = activated_graph(node, references=references)
        first = graph.can_perform(node.id)
        second = graph.can_perform(node.id)
        assert first == second, "identical inputs produced a different answer"
        asked_twice = {n: len(s.asked) for n, s in spies.items()}  # type: ignore[attr-defined]
        for name, count in asked_twice.items():
            assert count >= 2, f"{name} was asked {count} times across two queries"
        assert deny_declared(spies) > 0, "the mutation changed no authority"
        third = graph.can_perform(node.id)
        assert third.state is HonestState.NOT_CONFIGURED, (
            "a changed authority answer was not observed on the next query"
        )

    def test_step_6_a_reference_can_never_become_a_copy(self) -> None:
        """ARK-REQ-0047, structurally: the question cannot carry a value."""
        hints = get_type_hints(ReferenceResolver.resolves)
        assert hints.get("return") is bool, hints
        result = ShadowRegistryGate().evaluate(
            GateContext(REPO, AuthorityMap.load(REPO))
        )
        assert result.state is HonestState.PASS, result.detail

    def test_step_7_prerequisites_compose_transitively(self) -> None:
        base = activated_node("build.base", tier=SATISFIABLE_TIER)
        dependent = activated_node(
            "build.dependent", tier=SATISFIABLE_TIER, prerequisites=(base.id,)
        )
        references, spies = resolving_authorities(base, dependent)
        graph = activated_graph(base, dependent, references=references)
        assert graph.can_perform(dependent.id).state is HonestState.PASS
        assert deny_declared(spies, containing="build_base") > 0, (
            "no authority stopped resolving the prerequisite's own references"
        )
        refused = graph.can_perform(dependent.id)
        assert refused.state is HonestState.NOT_CONFIGURED
        assert "prerequisite" in refused.reason

    def test_step_7b_a_prerequisite_cycle_fails_closed(self) -> None:
        """A malformed graph is not an unconfigured capability."""
        left = activated_node("build.left", prerequisites=("build.right",))
        right = activated_node("build.right", prerequisites=("build.left",))
        references, _ = resolving_authorities(left, right)
        graph = activated_graph(left, right, references=references)
        with pytest.raises(InvalidCapabilityReference):
            graph.can_perform(left.id)

    def test_step_8_production_admission_can_now_succeed(self) -> None:
        """The mechanism, proven through the shipping AdmissionService."""
        node = activated_node(tier=SATISFIABLE_TIER)
        references, _ = resolving_authorities(node)
        decision = admit(activated_graph(node, references=references))
        assert decision.outcome is AdmissionOutcome.ADMITTED  # type: ignore[attr-defined]

    def test_step_8b_every_refusal_stops_admission_as_not_configured(self) -> None:
        """Never a state Phase 8's unchanged predicate would read as success."""
        node = activated_node(tier=SATISFIABLE_TIER)
        empty = ReferenceResolvers(binding(), {})
        for graph in (
            activated_graph(node, references=empty),
            activated_graph(node, references=None),
            activated_graph(node, references=None, current_phase=PRE_ACTIVATION_PHASE),
        ):
            decision = admit(graph)
            assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED  # type: ignore[attr-defined]


class TestTheJourneyClaimsNothingItDidNotDo:
    def test_the_activated_graph_produces_only_pass_and_not_configured(self) -> None:
        """The safety property Phase 8's accepted predicate depends on.

        Composed over every refusal shape this journey can construct, because a
        single `FAIL` or `UNSUPPORTED` would be read as condition (a) satisfied.
        """
        node = activated_node(tier=SATISFIABLE_TIER)
        unconfigured = activated_node("build.unconfigured", configured=False)
        references, spies = resolving_authorities(node, unconfigured)
        graph = activated_graph(node, unconfigured, references=references)
        seen = {
            graph.can_perform(node.id).state,
            graph.can_perform(unconfigured.id).state,
        }
        assert deny_declared(spies) > 0, "the mutation changed no authority"
        seen.add(graph.can_perform(node.id).state)
        seen.add(activated_graph(node, references=None).can_perform(node.id).state)
        assert seen <= {HonestState.PASS, HonestState.NOT_CONFIGURED}, seen

    def test_no_module_in_this_journey_contacts_a_provider(self) -> None:
        """The journey's own IMPORTS may not reach the network.

        Read by AST rather than by substring, or this control would match its own
        vocabulary and pass for the wrong reason (the F-0017 shape in miniature).
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

    def test_no_external_result_is_claimed_anywhere_in_the_journey(
        self, register: RequirementRegister
    ) -> None:
        report = journey_report(journey_run(), journey_run())
        assert not Rule.external_runs(report)
        assert Rule.evaluate(REPO, report, register)[0] is True

    def test_the_denominator_is_exactly_the_registers_phase_9b_set(
        self, register: RequirementRegister
    ) -> None:
        """Nothing outside the denominator may be claimed by this phase."""
        owned = {r.req_id for r in register.for_phase(PHASE)}
        assert owned == {"ARK-REQ-0046", "ARK-REQ-0047", "ARK-REQ-0048"}, owned
