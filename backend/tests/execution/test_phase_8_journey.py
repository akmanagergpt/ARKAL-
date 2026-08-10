"""Phase 8 final integration: C-21 declaration and admission, composed.

WHAT THIS PROVES. That the two halves Phase 8 delivered work as one plane: a
worker declares itself under C-21, the scheduler validates that declaration
against canonical authority, and an admission decision is then taken over the
real capability, isolation and resource conditions. Every mechanism is the
shipping one - the real PDP loaded from the canonical authority map, a real PEP,
the real `IsolationAuthority`, the real host probes, and the real
`CapabilityGraph`.

THE PRODUCTION ANSWER IS A REFUSAL, AND THAT IS THE POINT. Against the real
pre-activation graph every request returns `CAPABILITY_NOT_CONFIGURED`, because
`EXECUTION_AND_CAPABILITY.md` §1 activates the Capability Graph at **Phase 9B**
and calls the pre-activation answer "a determinate answer, never a stub, default
or assumption". This journey records that as the honest Phase 8 production
result rather than engineering around it.

WHAT IS NOT CLAIMED. No requirement: the register assigns Phase 8 none.
`ARK-REQ-0354` (failure-domain isolation) is **Phase 31** and is not claimed
here or anywhere in Phase 8. No worker is executed, no provider runtime exists,
no capability is activated, and no C-19 record is read or written.

NO PERSISTENCE IS INVOLVED AT ALL. C-21 is INT. This journey opens no database,
builds no engine and runs no migration - unlike the Phase 7 journey, which
needed all three. That absence is asserted rather than assumed.
"""

from __future__ import annotations

import datetime as dt

import pytest

from arkali.control.isolation.isolation_contract import IsolationAuthority
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.execution.scheduler.admission_result import AdmissionOutcome
from arkali.execution.scheduler.worker_contract import WorkerContract, WorkerDeclaration
from arkali.execution.scheduler.worker_vocabulary import WorkerVocabulary
from arkali.kernel.contracts.results import HonestState
from tests.execution.scheduler_admission_harness import (
    ACTIVATION_PHASE,
    PROFILE,
    REPO,
    ResolverSpy,
    build_service,
    denying_pep,
    probed_backends,
    real_graph,
    real_pep,
    request,
)

#: A tier the real host can satisfy, and one it cannot. Both are read back from
#: the canonical authority rather than assumed; the assertions below prove the
#: host posture rather than presuming it.
SATISFIABLE_TIER = "TRUST-0"
UNSATISFIABLE_TIER = "TRUST-4"


def declaration(worker_class: str, **overrides: object) -> WorkerDeclaration:
    fields: dict[str, object] = {
        "worker_class": worker_class,
        "concurrency_limit": 2,
        "resource_profile": PROFILE,
        "required_trust_tier": SATISFIABLE_TIER,
        "required_isolation_properties": (),
        "heartbeat_interval": dt.timedelta(seconds=30),
    }
    fields.update(overrides)
    return WorkerDeclaration(**fields)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def vocabulary() -> WorkerVocabulary:
    return WorkerVocabulary.load(REPO)


class TestTheWholeSchedulerPlane:
    """Declaration and admission, composed over real authorities."""

    def test_every_canonical_worker_class_declares_then_is_honestly_refused(
        self, vocabulary: WorkerVocabulary
    ) -> None:
        """The composed Phase 8 journey, end to end, at its honest outcome.

        Seven canonical classes are declared through the PEP-governed contract,
        read back, and each submitted for admission against the REAL
        pre-activation capability graph. Every one is refused for the same
        canonical reason, and the reason names the activation phase.
        """
        pep = real_pep()
        service = build_service(resolver=real_graph(), pep=pep)
        classes = vocabulary.classes()
        assert len(classes) == 7, f"canonical class list changed: {classes}"

        for name in classes:
            service._contract.declare(declaration(name))
        assert service._contract.declared_classes() == tuple(sorted(classes))

        outcomes = {}
        for name in classes:
            decision = service.evaluate(request(name))
            outcomes[name] = decision.outcome
            assert not decision.admitted
            assert ACTIVATION_PHASE in decision.reason, (
                "the refusal must carry the capability authority's own reason"
            )
            assert decision.worker_class == name

        assert set(outcomes.values()) == {
            AdmissionOutcome.CAPABILITY_NOT_CONFIGURED
        }, f"production admission produced something else: {outcomes}"
        assert pep.audit_trail, "the journey took no audited policy decision"

    def test_the_production_refusal_is_stable_across_repeated_evaluation(
        self,
    ) -> None:
        """Deterministic, and the authority is re-asked every time."""
        service = build_service(resolver=real_graph())
        service._contract.declare(declaration("agent"))
        asked = request("agent")
        answers = {service.evaluate(asked).render() for _ in range(5)}
        assert len(answers) == 1, f"admission is not deterministic: {answers}"
        assert asked.availability.in_flight == 0, "evaluating consumed capacity"

    def test_the_journey_opens_no_database_and_builds_no_engine(self) -> None:
        """C-21 is INT. The whole plane runs with no persistence at all."""
        import arkali.execution.scheduler as scheduler_package

        service = build_service(resolver=real_graph())
        service._contract.declare(declaration("sandbox"))
        service.evaluate(request("sandbox"))
        held = vars(service) | vars(service._contract)
        for value in held.values():
            assert "Session" not in type(value).__name__, type(value)
            assert "Engine" not in type(value).__name__, type(value)
        assert not hasattr(scheduler_package, "metadata")


class TestTheThreeConditionsComposeOverRealAuthorities:
    """With capability answered, the other two are decided by the real host."""

    def test_the_real_host_posture_is_what_the_isolation_authority_reports(
        self,
    ) -> None:
        """Anti-vacuity for the tier cases below: prove the posture, do not assume it."""
        authority = IsolationAuthority.load(REPO)
        probed = probed_backends()
        assert authority.resolve(SATISFIABLE_TIER, probed).satisfied
        unsatisfiable = authority.resolve(UNSATISFIABLE_TIER, probed)
        assert not unsatisfiable.satisfied
        assert unsatisfiable.capability_state is HonestState.UNSUPPORTED
        assert unsatisfiable.execution_decision == "DENY"

    def test_a_satisfiable_worker_is_admitted_once_capability_answers(self) -> None:
        """The ADMITTED branch, reachable only with a test-only resolver.

        This is NOT a claim that production capability is configured. It proves
        that conditions (b) and (c) and the composition are correct, so that
        when Phase 9B activates the graph the decision is already right.
        """
        service = build_service(resolver=ResolverSpy(state=HonestState.PASS))
        service._contract.declare(declaration("build/test"))
        decision = service.evaluate(request("build/test"))
        assert decision.outcome is AdmissionOutcome.ADMITTED

    def test_an_unsatisfiable_tier_refuses_on_the_real_host(self) -> None:
        service = build_service(resolver=ResolverSpy(state=HonestState.PASS))
        service._contract.declare(
            declaration("browser", required_trust_tier=UNSATISFIABLE_TIER)
        )
        decision = service.evaluate(request("browser"))
        assert decision.outcome is AdmissionOutcome.ISOLATION_UNSATISFIED
        assert "UNSUPPORTED" in decision.reason

    def test_an_exhausted_budget_refuses(self) -> None:
        service = build_service(resolver=ResolverSpy(state=HonestState.PASS))
        service._contract.declare(declaration("provider", concurrency_limit=1))
        decision = service.evaluate(request("provider", in_flight=1))
        assert decision.outcome is AdmissionOutcome.RESOURCE_UNAVAILABLE

    def test_capability_is_re_asked_on_every_evaluation_of_the_journey(self) -> None:
        """The no-cache rule, asserted on the composed plane and not only in unit."""
        spy = ResolverSpy(state=HonestState.PASS)
        service = build_service(resolver=spy)
        service._contract.declare(declaration("local-AI"))
        for _ in range(4):
            service.evaluate(request("local-AI"))
        assert len(spy.calls) == 4, (
            f"the capability authority was asked {len(spy.calls)} times for 4 "
            "evaluations; a cached verdict would show fewer"
        )


class TestTheBoundariesHoldOnTheComposedPlane:
    """What Phase 8 must not do, asserted while it is actually running."""

    def test_a_policy_denial_stops_the_whole_journey(
        self, tmp_path: object
    ) -> None:
        spy = ResolverSpy(state=HonestState.PASS)
        service = build_service(
            resolver=spy,
            pep=denying_pep(tmp_path),  # type: ignore[arg-type]
            root=tmp_path,  # type: ignore[arg-type]
        )
        with pytest.raises(PolicyDenied):
            service.evaluate(request("agent"))
        assert spy.calls == [], "a denied evaluation still asked the authority"

    def test_the_journey_imports_no_durable_or_evidence_module(self) -> None:
        """Asserted on the loaded modules, not only on the source text."""
        import sys

        service = build_service(resolver=real_graph())
        service._contract.declare(declaration("computer-use"))
        service.evaluate(request("computer-use"))
        scheduler_modules = [
            name for name in sys.modules
            if name.startswith("arkali.execution.scheduler")
        ]
        assert scheduler_modules, "the scheduler package was never imported"
        for name in scheduler_modules:
            module = sys.modules[name]
            for attribute in vars(module).values():
                origin = getattr(attribute, "__module__", "") or ""
                assert not origin.startswith("arkali.execution.durable"), (
                    f"{name} holds {attribute!r} from execution.durable"
                )
                assert not origin.startswith("arkali.evidence"), (
                    f"{name} holds {attribute!r} from evidence.*"
                )

    def test_the_capability_graph_is_never_activated_by_the_journey(self) -> None:
        graph = real_graph()
        service = build_service(resolver=graph)
        service._contract.declare(declaration("agent"))
        service.evaluate(request("agent"))
        assert not graph.is_activated, "the journey activated the capability graph"
        assert graph.activation_phase == ACTIVATION_PHASE
