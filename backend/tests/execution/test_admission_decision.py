"""C-21 admission behaviour: the three canonical conditions (Package 2).

`EXECUTION_AND_CAPABILITY.md` §4 admits a job only when (a) its capability
resolves other than `NOT_CONFIGURED`, (b) an isolation composition satisfies its
tier, and (c) resource budget is available. Every case below is one of those
three, their conjunction, or the boundary the decision must not cross.

THE PRODUCTION ANSWER IS A REFUSAL, AND THAT IS CORRECT. With the real
pre-activation `CapabilityGraph`, admission returns
`CAPABILITY_NOT_CONFIGURED`. That is designed behaviour until Phase 9B, not a
substitute for one, and the success path below is reached only with a
test-only resolver.
"""

from __future__ import annotations

import datetime as dt

import pytest

from arkali.control.capability.capability_graph import CapabilityGraph
from arkali.control.isolation.isolation_errors import TrustTierViolation
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.execution.scheduler.admission_result import AdmissionOutcome
from arkali.execution.scheduler.capability_admission import CapabilityAdmission
from arkali.execution.scheduler.errors import InvalidResourceAvailability
from arkali.execution.scheduler.isolation_admission import IsolationAdmission
from arkali.execution.scheduler.resource_admission import (
    ResourceAdmission,
    ResourceAvailability,
)
from arkali.execution.scheduler.worker_contract import WorkerDeclaration
from arkali.kernel.contracts.capability_errors import (
    InvalidCapabilityReference,
    PrematureActivation,
)
from arkali.kernel.contracts.results import HonestState
from arkali.control.isolation.isolation_contract import IsolationAuthority
from tests.execution.scheduler_admission_harness import (
    CAPABILITY_ID,
    PROFILE,
    REPO,
    ResolverSpy,
    build_service,
    denying_pep,
    probed_backends,
    real_graph,
    request,
    unavailable_backends,
)

WORKER = "agent"


def declaration(**overrides: object) -> WorkerDeclaration:
    fields: dict[str, object] = {
        "worker_class": WORKER,
        "concurrency_limit": 2,
        "resource_profile": PROFILE,
        "required_trust_tier": "TRUST-0",
        "required_isolation_properties": (),
        "heartbeat_interval": dt.timedelta(seconds=30),
    }
    fields.update(overrides)
    return WorkerDeclaration(**fields)  # type: ignore[arg-type]


class TestCapabilityCondition:
    """Condition (a): resolves other than NOT_CONFIGURED."""

    def test_the_real_graph_is_not_configured_before_activation(self) -> None:
        result = CapabilityAdmission(real_graph()).evaluate(CAPABILITY_ID)
        assert result.state is HonestState.NOT_CONFIGURED
        assert result.is_determinate, "NOT_CONFIGURED is a determinate answer"

    def test_production_admission_refuses_because_capability_is_unconfigured(
        self,
    ) -> None:
        """The honest Phase 8 production answer, using the shipping graph."""
        subject = build_service(resolver=real_graph())
        subject._contract.declare(declaration())
        decision = subject.evaluate(request(WORKER))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED
        assert not decision.admitted
        assert "9B" in decision.reason, "the canonical reason must be preserved"

    def test_an_unknown_capability_fails_closed(self) -> None:
        """A typo must not masquerade as a governed pre-activation answer."""
        subject = build_service(resolver=real_graph())
        subject._contract.declare(declaration())
        with pytest.raises(InvalidCapabilityReference):
            subject.evaluate(request(WORKER, capability_id="build.nosuch"))

    def test_the_scheduler_cannot_activate_the_graph(self) -> None:
        graph = real_graph()
        with pytest.raises(PrematureActivation):
            graph.activate()
        assert not graph.is_activated

    def test_the_scheduler_cannot_force_a_configured_verdict(self) -> None:
        """Setting current_phase to the activation phase does not yield a PASS."""
        activated = real_graph(current_phase="9B")
        assert activated.is_activated
        with pytest.raises(PrematureActivation):
            CapabilityAdmission(activated).evaluate(CAPABILITY_ID)

    def test_the_resolver_is_injected_with_no_default(self) -> None:
        with pytest.raises(TypeError):
            CapabilityAdmission()  # type: ignore[call-arg]


class TestCapabilityVerdictIsNotCached:
    """Load-bearing: §1 forbids caching a capability verdict."""

    def test_every_evaluation_re_queries_the_authority(self) -> None:
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(resolver=spy)
        subject._contract.declare(declaration())
        for _ in range(3):
            subject.evaluate(request(WORKER))
        assert spy.calls == [CAPABILITY_ID] * 3, (
            "the authority must be asked once per evaluation; a cached verdict "
            "would show fewer calls"
        )

    def test_a_changed_verdict_is_observed_immediately(self) -> None:
        """A cache would keep answering with the first verdict."""
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(resolver=spy)
        subject._contract.declare(declaration())
        assert subject.evaluate(request(WORKER)).admitted
        spy.state = HonestState.NOT_CONFIGURED
        second = subject.evaluate(request(WORKER))
        assert second.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED

    def test_the_evaluator_stores_no_verdict(self) -> None:
        spy = ResolverSpy()
        subject = CapabilityAdmission(spy)
        subject.evaluate(CAPABILITY_ID)
        held = [
            value for value in vars(subject).values()
            if value.__class__.__name__ == "CapabilityQueryResult"
        ]
        assert not held, f"a capability verdict is being stored: {held}"

    def test_the_capability_evaluator_has_no_cache_attribute(self) -> None:
        subject = CapabilityAdmission(ResolverSpy())
        subject.evaluate(CAPABILITY_ID)
        assert set(vars(subject)) == {"_resolver"}, (
            f"unexpected state on the capability evaluator: {sorted(vars(subject))}"
        )


class TestIsolationCondition:
    """Condition (b): an isolation composition satisfies the declared tier."""

    def test_a_satisfiable_tier_passes(self) -> None:
        subject = IsolationAdmission(IsolationAuthority.load(REPO), probed_backends)
        assessment = subject.evaluate("TRUST-0", ())
        assert assessment.satisfied

    def test_an_unsatisfiable_tier_refuses_and_keeps_the_canonical_reason(
        self,
    ) -> None:
        """TRUST-4 is genuinely unsupported on this host. Not converted to PASS."""
        subject = IsolationAdmission(IsolationAuthority.load(REPO), probed_backends)
        assessment = subject.evaluate("TRUST-4", ())
        assert not assessment.satisfied
        assert assessment.missing_for_tier
        assert "UNSUPPORTED" in assessment.reason

    def test_an_unknown_tier_raises_the_isolation_authoritys_own_type(self) -> None:
        subject = IsolationAdmission(IsolationAuthority.load(REPO), probed_backends)
        with pytest.raises(TrustTierViolation):
            subject.evaluate("TRUST-9", ())

    def test_a_declared_property_no_backend_provides_is_unmet(self) -> None:
        subject = IsolationAdmission(
            IsolationAuthority.load(REPO), unavailable_backends
        )
        assessment = subject.evaluate("TRUST-0", ("FS_CONFINEMENT",))
        assert not assessment.satisfied
        assert assessment.unmet_declared_properties == ("FS_CONFINEMENT",)

    def test_admission_refuses_when_isolation_is_unsatisfied(self) -> None:
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(resolver=spy)
        subject._contract.declare(declaration(required_trust_tier="TRUST-4"))
        decision = subject.evaluate(request(WORKER))
        assert decision.outcome is AdmissionOutcome.ISOLATION_UNSATISFIED

    def test_no_isolation_backend_is_invented(self) -> None:
        """With nothing available, nothing above TRUST-0 becomes satisfiable."""
        authority = IsolationAuthority.load(REPO)
        subject = IsolationAdmission(authority, unavailable_backends)
        for tier in authority.tiers:
            assessment = subject.evaluate(tier, ())
            if authority.required_properties(tier):
                assert not assessment.satisfied, f"{tier} was satisfied by nothing"


class TestResourceCondition:
    """Condition (c): resource budget is available."""

    def test_spare_capacity_and_an_available_profile_pass(self) -> None:
        assessment = ResourceAdmission().evaluate(
            2, PROFILE, ResourceAvailability(in_flight=1, available_profiles=(PROFILE,))
        )
        assert assessment.satisfied

    @pytest.mark.parametrize("in_flight", [2, 3, 99])
    def test_an_exhausted_concurrency_limit_refuses(self, in_flight: int) -> None:
        assessment = ResourceAdmission().evaluate(
            2,
            PROFILE,
            ResourceAvailability(in_flight=in_flight, available_profiles=(PROFILE,)),
        )
        assert not assessment.satisfied
        assert "concurrency limit" in assessment.reason

    def test_an_unavailable_resource_profile_refuses(self) -> None:
        assessment = ResourceAdmission().evaluate(
            2, PROFILE, ResourceAvailability(in_flight=0, available_profiles=("gpu",))
        )
        assert not assessment.satisfied
        assert "resource profile" in assessment.reason

    def test_no_available_profile_at_all_refuses(self) -> None:
        assessment = ResourceAdmission().evaluate(
            2, PROFILE, ResourceAvailability(in_flight=0)
        )
        assert not assessment.satisfied

    @pytest.mark.parametrize("in_flight", [-1, -100])
    def test_an_impossible_snapshot_fails_closed(self, in_flight: int) -> None:
        with pytest.raises(InvalidResourceAvailability):
            ResourceAdmission().evaluate(
                2,
                PROFILE,
                ResourceAvailability(
                    in_flight=in_flight, available_profiles=(PROFILE,)
                ),
            )

    def test_the_decision_is_deterministic_and_consumes_nothing(self) -> None:
        subject = ResourceAdmission()
        snapshot = ResourceAvailability(in_flight=1, available_profiles=(PROFILE,))
        first = subject.evaluate(2, PROFILE, snapshot)
        second = subject.evaluate(2, PROFILE, snapshot)
        assert first == second
        assert snapshot.in_flight == 1, "evaluating consumed capacity"
        assert not vars(subject), "the resource evaluator accumulated state"

    def test_admission_refuses_when_capacity_is_exhausted(self) -> None:
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(resolver=spy)
        subject._contract.declare(declaration(concurrency_limit=1))
        decision = subject.evaluate(request(WORKER, in_flight=1))
        assert decision.outcome is AdmissionOutcome.RESOURCE_UNAVAILABLE


class TestThreeConditionComposition:
    """All three are required; none may be waived by another."""

    def test_all_three_satisfied_admits(self) -> None:
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(resolver=spy)
        subject._contract.declare(declaration())
        decision = subject.evaluate(request(WORKER))
        assert decision.outcome is AdmissionOutcome.ADMITTED
        assert decision.admitted

    def test_each_condition_alone_can_refuse(self) -> None:
        """Break one condition at a time; each must be sufficient to refuse."""
        cases = {
            AdmissionOutcome.CAPABILITY_NOT_CONFIGURED: (
                ResolverSpy(state=HonestState.NOT_CONFIGURED), {}, {}
            ),
            AdmissionOutcome.ISOLATION_UNSATISFIED: (
                ResolverSpy(state=HonestState.PASS),
                {"required_trust_tier": "TRUST-4"},
                {},
            ),
            AdmissionOutcome.RESOURCE_UNAVAILABLE: (
                ResolverSpy(state=HonestState.PASS),
                {"concurrency_limit": 1},
                {"in_flight": 1},
            ),
        }
        for expected, (spy, declared, asked) in cases.items():
            subject = build_service(resolver=spy)
            subject._contract.declare(declaration(**declared))
            assert subject.evaluate(request(WORKER, **asked)).outcome is expected

    def test_an_unconfigured_capability_can_never_be_admitted(self) -> None:
        """Even with isolation and resource perfect, (a) is decisive."""
        subject = build_service(resolver=ResolverSpy(state=HonestState.NOT_CONFIGURED))
        subject._contract.declare(declaration(required_trust_tier="TRUST-0"))
        decision = subject.evaluate(request(WORKER, in_flight=0))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED
        assert not decision.admitted

    def test_the_canonical_predicate_is_not_narrowed_to_pass(self) -> None:
        """§4 says "other than NOT_CONFIGURED", not "PASS"."""
        subject = build_service(resolver=ResolverSpy(state=HonestState.UNSUPPORTED))
        subject._contract.declare(declaration())
        assert subject.evaluate(request(WORKER)).outcome is AdmissionOutcome.ADMITTED

    def test_the_decision_is_deterministic(self) -> None:
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(resolver=spy)
        subject._contract.declare(declaration())
        answers = {subject.evaluate(request(WORKER)).render() for _ in range(5)}
        assert len(answers) == 1

    def test_admission_produces_no_side_effect(self) -> None:
        """Evaluating twice with the same snapshot gives the same answer."""
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(resolver=spy)
        subject._contract.declare(declaration(concurrency_limit=2))
        asked = request(WORKER, in_flight=1)
        assert subject.evaluate(asked).admitted
        assert subject.evaluate(asked).admitted
        assert asked.availability.in_flight == 1


class TestPolicyDenialStaysDistinct:
    """A policy refusal is not an admission outcome."""

    def test_a_denied_evaluation_raises_rather_than_refusing(
        self, tmp_path: object
    ) -> None:
        subject = build_service(
            resolver=ResolverSpy(state=HonestState.PASS),
            pep=denying_pep(tmp_path),  # type: ignore[arg-type]
            root=tmp_path,  # type: ignore[arg-type]
        )
        with pytest.raises(PolicyDenied):
            subject.evaluate(request(WORKER))

    def test_a_denial_is_never_reclassified_as_a_condition_failure(
        self, tmp_path: object
    ) -> None:
        subject = build_service(
            resolver=ResolverSpy(state=HonestState.PASS),
            pep=denying_pep(tmp_path),  # type: ignore[arg-type]
            root=tmp_path,  # type: ignore[arg-type]
        )
        try:
            subject.evaluate(request(WORKER))
        except PolicyDenied as denied:
            for outcome in AdmissionOutcome:
                assert outcome.value not in str(denied)
        else:  # pragma: no cover - the call above must raise
            pytest.fail("a denying PDP did not stop the governed evaluation")

    def test_the_denial_happens_before_any_condition_is_evaluated(
        self, tmp_path: object
    ) -> None:
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(
            resolver=spy,
            pep=denying_pep(tmp_path),  # type: ignore[arg-type]
            root=tmp_path,  # type: ignore[arg-type]
        )
        with pytest.raises(PolicyDenied):
            subject.evaluate(request(WORKER))
        assert spy.calls == [], "the capability authority was asked despite a DENY"

    def test_the_pep_is_injected_with_no_default(self) -> None:
        from arkali.execution.scheduler.admission import AdmissionService

        with pytest.raises(TypeError):
            AdmissionService()  # type: ignore[call-arg]


class TestAdmissionIsNotAllocation:
    """Package 2 decides. It hands nothing out."""

    def test_the_service_exposes_no_allocation_operation(self) -> None:
        from arkali.execution.scheduler.admission import AdmissionService

        forbidden = (
            "allocate", "dispatch", "claim", "lease", "reserve", "assign",
            "spawn", "enqueue", "dequeue", "priority", "fairness", "queue",
        )
        public = [n for n in dir(AdmissionService) if not n.startswith("_")]
        for name in public:
            assert not any(word in name.lower() for word in forbidden), name

    def test_the_decision_carries_no_worker_handle_or_durable_reference(self) -> None:
        """An admission answer is a verdict, not a grant of anything."""
        spy = ResolverSpy(state=HonestState.PASS)
        subject = build_service(resolver=spy)
        subject._contract.declare(declaration())
        decision = subject.evaluate(request(WORKER))
        fields = set(type(decision).model_fields)
        assert fields == {
            "worker_class", "capability_id", "outcome", "reason",
            "authoritative_source",
        }, f"the admission decision grew a field: {sorted(fields)}"
        for absent in ("handle", "token", "job_id", "assignment", "attempt", "lease"):
            assert not any(absent in name for name in fields), absent

    def test_the_graph_is_the_shipping_class(self) -> None:
        """Anti-vacuity: the production path really uses control.capability."""
        assert isinstance(real_graph(), CapabilityGraph)
