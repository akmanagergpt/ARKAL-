"""Phase 9 composed journey — C-11 and its two governing invariants.

The smallest journey that proves the three implemented obligations COMPOSE, over
real repository mechanisms. Every authority is loaded from the canonical
documents, every gate is the shipping gate, and the acceptance path is the real
`PhaseGateChecker`.

WHAT THIS DELIBERATELY DOES NOT DO. Nothing here contacts a provider, opens a
socket, measures live health, meters cost, selects a fallback, activates the
Capability Graph or produces a provider result of any kind. `ARK-REQ-0219` is
earned by PREVENTING fabrication, so a journey that fabricated a successful
provider call to demonstrate it would refute the very requirement it claims. No
stand-in provider is used as evidence that an external result occurred.

The journey is one narrative in seven steps:

  1. the registry owns the seven concerns and produces the C-11 record;
  2. no second provider registry exists;
  3. the five reference-only consumers are derived from authority;
  4. no consumer may store, cache, mirror, default, alias or re-derive a concern;
  5. the acceptance path refuses a local or simulated result declared external;
  6. honest no-result outcomes stay honest and accepted;
  7. the Capability Graph is not activated and admission still refuses.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from typing import Final

import pytest

from arkali.acceptance.checker import PhaseGateChecker
from arkali.acceptance.external_result import ExternalProviderResultRule as Rule
from arkali.acceptance.phase_report import PhaseReport, TestExecutionRecord
from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.runner import GateRunner
from arkali.control.capability.capability_graph import CapabilityGraph
from arkali.control.registry.provider.provider_authority import ProviderAuthority
from arkali.control.registry.provider.provider_health_state_machine import DEFINITION
from arkali.control.registry.provider.provider_record import ProviderRecord
from arkali.control.specification.register_parser import RequirementRegister
from arkali.execution.scheduler.admission_result import AdmissionOutcome
from arkali.execution.scheduler.worker_contract import WorkerDeclaration
from arkali.execution.scheduler.worker_vocabulary import WorkerVocabulary
from arkali.kernel.contracts.results import HonestState
from tests.execution.scheduler_admission_harness import (
    ACTIVATION_PHASE,
    PRE_ACTIVATION_PHASE,
    PROFILE,
    build_service,
    node,
    real_graph,
    request,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PHASE: Final[str] = "9"


@pytest.fixture(scope="module")
def authority() -> ProviderAuthority:
    return ProviderAuthority.load(REPO)


@pytest.fixture(scope="module")
def gates() -> dict[str, HonestState]:
    amap = AuthorityMap.load(REPO)
    return {r.check_id: r.state for r in GateRunner(REPO, amap).run_all()}


def phase_9_run(**changes: object) -> TestExecutionRecord:
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


def phase_9_report(*runs: TestExecutionRecord) -> PhaseReport:
    return PhaseReport(
        phase_id=PHASE,
        objective="Phase 9 journey fixture",
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
        evidence_created=("EV-0060",),
        limitations="none",
        blockers="none",
        next_exact_action="continue",
        status=HonestState.PASS,
    )


class TestPhase9Journey:
    """One narrative. Each step depends on the one before it holding."""

    def test_step_1_the_registry_owns_the_seven_concerns_and_records_them(
        self, authority: ProviderAuthority
    ) -> None:
        """The C-11 record carries exactly what the canonical map assigns."""
        concerns = authority.owned_concerns()
        assert set(ProviderRecord.model_fields) >= set(concerns), (
            "the record does not carry every concern the map assigns it"
        )
        record = ProviderRecord(
            identity="acme.local",
            model_identity=("acme.local/small",),
            configuration=(),
            health=DEFINITION.states[0],
            availability="",
            cost_metadata="",
            fallback=(),
        )
        assert record.identity == "acme.local"
        assert record.health in DEFINITION.states, (
            "health must be a state of the canonical Phase 3 machine"
        )

    def test_step_2_no_second_provider_registry_exists(
        self, gates: dict[str, HonestState]
    ) -> None:
        assert gates["duplicate_canonical_authority"] is HonestState.PASS
        assert gates["shadow_registry"] is HonestState.PASS

    def test_step_3_the_five_consumers_are_derived_from_authority(
        self, authority: ProviderAuthority
    ) -> None:
        """Derived at call time; this control names none of them."""
        amap = AuthorityMap.load(REPO)
        consumers = authority.reference_only_consumers()
        assert consumers, "no reference-only consumer is declared"
        assert all(c in amap.contexts for c in consumers)
        assert authority.owner not in consumers
        assert authority.copying_permitted is False
        assert authority.caching_permitted is False

    def test_step_4_no_consumer_may_hold_an_owned_value(
        self, gates: dict[str, HonestState]
    ) -> None:
        """The source half of the gate, over every consumer module on disk."""
        amap = AuthorityMap.load(REPO)
        result = next(
            r for r in GateRunner(REPO, amap).run_all()
            if r.check_id == "shadow_registry"
        )
        assert gates["shadow_registry"] is HonestState.PASS
        assert "consumer modules scanned" in result.summary
        scanned = int("".join(c for c in result.summary.split("scanned")[0]
                             if c.isdigit()))
        assert scanned > 0, "a PASS over zero consumer modules would be vacuous"

    def test_step_5_a_local_or_simulated_result_cannot_be_declared_external(
        self
    ) -> None:
        """The acceptance path refuses it, through the real checker."""
        register = RequirementRegister.load(REPO)
        for declared in (Rule.Declared.NO_EXTERNAL_RESULT,
                         Rule.Declared.SIMULATED_TEST_ONLY):
            honest = phase_9_report(phase_9_run(external_result=declared))
            assert Rule.evaluate(REPO, honest, register)[0] is True
        relabelled = phase_9_report(
            phase_9_run(external_result=Rule.Declared.EXTERNAL_PROVIDER_RESULT)
        )
        passed, summary, _ = Rule.evaluate(REPO, relabelled, register)
        assert passed is False
        assert "no canonical binding can substantiate" in summary

    def test_step_6_honest_no_result_stays_honest_through_the_checker(
        self
    ) -> None:
        checker = PhaseGateChecker(REPO)
        result = checker.check_external_result_integrity(
            phase_9_report(phase_9_run())
        )
        assert result.state is HonestState.PASS
        assert Rule.Declared.NO_EXTERNAL_RESULT.value in result.detail

    def test_step_7_the_capability_graph_is_not_activated(self) -> None:
        graph = CapabilityGraph(
            [node()], activation_phase=ACTIVATION_PHASE,
            current_phase=PRE_ACTIVATION_PHASE,
        )
        assert graph.is_activated is False
        answer = graph.can_perform(node().id)
        assert answer.state is HonestState.NOT_CONFIGURED
        assert answer.is_determinate, "NOT_CONFIGURED must stay a determinate answer"

    def test_step_7b_production_admission_still_refuses(self) -> None:
        """Composed with the shipping AdmissionService, unchanged by Phase 9.

        The worker class is the canonical `provider` class, declared through the
        PEP-governed C-21 contract exactly as Phase 8 requires - declaring it is
        not provider execution, and admission still refuses.
        """
        service = build_service(resolver=real_graph())
        provider_class = next(
            c for c in WorkerVocabulary.load(REPO).classes() if "provider" in c
        )
        service._contract.declare(
            WorkerDeclaration(
                worker_class=provider_class,
                concurrency_limit=1,
                resource_profile=PROFILE,
                required_trust_tier="TRUST-0",
                required_isolation_properties=(),
                heartbeat_interval=dt.timedelta(seconds=30),
            )
        )
        decision = service.evaluate(request(provider_class))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED
        assert not decision.admitted
        assert ACTIVATION_PHASE in decision.reason


class TestTheJourneyClaimsNothingItDidNotDo:
    def test_no_module_in_this_journey_contacts_a_provider(self) -> None:
        """The journey's own IMPORTS may not reach the network.

        Read by AST rather than by substring, or this control would match its
        own vocabulary and pass for the wrong reason - which it did on the first
        run, and which is the F-0017 shape in miniature.
        """
        import ast

        tree = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for stmt in ast.walk(tree):
            if isinstance(stmt, ast.Import):
                imported |= {a.name.split(".")[0] for a in stmt.names}
            elif isinstance(stmt, ast.ImportFrom) and stmt.module:
                imported.add(stmt.module.split(".")[0])
        network = {"httpx", "httpx2", "requests", "urllib", "urllib3", "socket",
                   "aiohttp", "http"}
        assert not (imported & network), f"the journey imports {imported & network}"

    def test_no_external_result_is_claimed_anywhere_in_the_journey(self) -> None:
        register = RequirementRegister.load(REPO)
        report = phase_9_report(phase_9_run(), phase_9_run())
        assert not Rule.external_runs(report)
        assert Rule.evaluate(REPO, report, register)[0] is True

    def test_the_denominator_is_exactly_the_registers_phase_9_set(self) -> None:
        """Nothing outside the denominator may be claimed by this phase."""
        register = RequirementRegister.load(REPO)
        owned = {r.req_id for r in register.for_phase(PHASE)}
        assert len(owned) == 3, owned
        assert Rule.REQUIREMENT in owned
