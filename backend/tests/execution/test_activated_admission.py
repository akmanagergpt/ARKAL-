"""The activated capability observed through the REAL AdmissionService.

Phase 9B Package 2. `CapabilityGraph` unit tests prove what the graph answers;
these prove what `execution.scheduler` does with that answer, through the
shipping `AdmissionService`, `CapabilityAdmission`, `WorkerContract`,
`IsolationAdmission`, `ResourceAdmission` and a real PEP over a real PDP. Only
the node set, the phase and the injected reference authorities are fixtures.

THE SAFETY QUESTION THIS MODULE EXISTS TO ANSWER. Phase 8's accepted predicate
for condition (a) is `state is not NOT_CONFIGURED`, and it is deliberately not
narrowed to `state is PASS`. That predicate is safe only if the activated graph
never produces a NEGATIVE state other than `NOT_CONFIGURED` — a `FAIL` or
`UNSUPPORTED` capability would be read as condition (a) satisfied and would admit
work whose references do not resolve. Package 2 derived the mapping so that this
cannot happen, and the controls below prove it against the real service rather
than asserting it in prose. **No Phase 8 code, predicate or accepted artifact was
changed.**
"""

from __future__ import annotations

import datetime as dt

import pytest

from arkali.control.capability.reference_resolution import ReferenceResolvers
from arkali.execution.scheduler.admission_result import AdmissionOutcome
from arkali.execution.scheduler.capability_admission import resolves
from arkali.execution.scheduler.worker_contract import WorkerDeclaration
from arkali.kernel.contracts.capability_errors import InvalidCapabilityReference
from arkali.kernel.contracts.results import HonestState
from tests.execution.scheduler_admission_harness import (
    CAPABILITY_ID,
    PROFILE,
    activated_graph,
    activated_node,
    binding,
    build_service,
    request,
    resolving_authorities,
)

WORKER = "agent"
#: The only tier this host can satisfy; condition (b) is not what is under test.
SATISFIABLE_TIER = "TRUST-0"


def declaration(**overrides: object) -> WorkerDeclaration:
    fields: dict[str, object] = {
        "worker_class": WORKER,
        "concurrency_limit": 2,
        "resource_profile": PROFILE,
        "required_trust_tier": SATISFIABLE_TIER,
        "required_isolation_properties": (),
        "heartbeat_interval": dt.timedelta(seconds=30),
    }
    fields.update(overrides)
    return WorkerDeclaration(**fields)  # type: ignore[arg-type]


def service(graph: object) -> object:
    built = build_service(resolver=graph)
    built._contract.declare(declaration())  # type: ignore[attr-defined]
    return built


def evaluate(graph: object) -> object:
    return service(graph).evaluate(request(WORKER))  # type: ignore[attr-defined]


class TestAnActivatedCapabilityCanSatisfyConditionA:
    def test_a_fully_resolved_configured_capability_is_admitted(self) -> None:
        """The first time production admission can succeed at all."""
        node = activated_node(tier=SATISFIABLE_TIER)
        references, _ = resolving_authorities(node)
        decision = evaluate(activated_graph(node, references=references))
        assert decision.outcome is AdmissionOutcome.ADMITTED  # type: ignore[attr-defined]
        assert decision.admitted  # type: ignore[attr-defined]

    def test_the_admitted_path_used_the_real_authorities(self) -> None:
        """Every declared authority was asked; nothing was assumed."""
        node = activated_node(tier=SATISFIABLE_TIER)
        references, spies = resolving_authorities(node)
        evaluate(activated_graph(node, references=references))
        assert spies, "no authority declared; this control would be vacuous"
        for name, spy in spies.items():
            assert spy.asked, f"{name} was never asked yet the job was admitted"  # type: ignore[attr-defined]


class TestEveryCapabilityRefusalStopsAdmission:
    def test_a_missing_resolver_does_not_admit(self) -> None:
        node = activated_node(tier=SATISFIABLE_TIER)
        empty = ReferenceResolvers(binding(), {})
        decision = evaluate(activated_graph(node, references=empty))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED  # type: ignore[attr-defined]

    def test_no_composed_authority_at_all_does_not_admit(self) -> None:
        node = activated_node(tier=SATISFIABLE_TIER)
        decision = evaluate(activated_graph(node, references=None))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED  # type: ignore[attr-defined]

    def test_an_unresolved_reference_does_not_admit(self) -> None:
        """The authority is composed and answers no."""
        node = activated_node(tier=SATISFIABLE_TIER)
        references, spies = resolving_authorities(node)
        for spy in spies.values():
            spy.known = set()  # type: ignore[attr-defined]
        decision = evaluate(activated_graph(node, references=references))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED  # type: ignore[attr-defined]

    def test_an_unknown_reference_does_not_admit(self) -> None:
        """A node naming an identifier no authority declares."""
        node = activated_node(tier=SATISFIABLE_TIER)
        other = activated_node("build.other", tier=SATISFIABLE_TIER)
        references, _ = resolving_authorities(other)
        decision = evaluate(activated_graph(node, references=references))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED  # type: ignore[attr-defined]

    def test_an_unconfigured_node_does_not_admit(self) -> None:
        node = activated_node(tier=SATISFIABLE_TIER, configured=False)
        references, _ = resolving_authorities(node)
        decision = evaluate(activated_graph(node, references=references))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED  # type: ignore[attr-defined]

    def test_an_unresolved_prerequisite_does_not_admit(self) -> None:
        base = activated_node("build.base", tier=SATISFIABLE_TIER, configured=False)
        top = activated_node(
            CAPABILITY_ID, tier=SATISFIABLE_TIER, prerequisites=("build.base",)
        )
        references, _ = resolving_authorities(base, top)
        decision = evaluate(activated_graph(base, top, references=references))
        assert decision.outcome is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED  # type: ignore[attr-defined]

    def test_an_unknown_capability_still_fails_closed(self) -> None:
        node = activated_node("build.other", tier=SATISFIABLE_TIER)
        references, _ = resolving_authorities(node)
        with pytest.raises(InvalidCapabilityReference):
            evaluate(activated_graph(node, references=references))


class TestNoNegativeGraphOutcomeCanBecomeAdmitted:
    """The load-bearing reconciliation with Phase 8's unchanged predicate."""

    def _states(self) -> set[HonestState]:
        """Every state the activated graph actually produces, collected live."""
        node = activated_node(tier=SATISFIABLE_TIER)
        references, spies = resolving_authorities(node)
        found = {activated_graph(node, references=references).can_perform(
            CAPABILITY_ID
        ).state}
        for spy in spies.values():
            spy.known = set()  # type: ignore[attr-defined]
        found.add(
            activated_graph(node, references=references).can_perform(
                CAPABILITY_ID
            ).state
        )
        found.add(
            activated_graph(
                activated_node(tier=SATISFIABLE_TIER, configured=False),
                references=references,
            ).can_perform(CAPABILITY_ID).state
        )
        found.add(
            activated_graph(node, references=None).can_perform(CAPABILITY_ID).state
        )
        found.add(
            activated_graph(node, references=references, current_phase="8")
            .can_perform(CAPABILITY_ID).state
        )
        return found

    def test_the_graph_produces_only_pass_and_not_configured(self) -> None:
        assert self._states() == {HonestState.PASS, HonestState.NOT_CONFIGURED}

    def test_exactly_the_affirmative_state_satisfies_the_canonical_predicate(
        self,
    ) -> None:
        """§4's predicate is unchanged; the mapping is what makes it safe.

        `resolves` is Phase 8's accepted implementation of "resolves other than
        `NOT_CONFIGURED`". Applied to every state the activated graph can
        produce, exactly the affirmative one satisfies condition (a).
        """
        from arkali.control.capability.capability_graph import CapabilityQueryResult

        satisfying = {
            state
            for state in self._states()
            if resolves(
                CapabilityQueryResult(
                    capability_id=CAPABILITY_ID, state=state, reason="probe"
                )
            )
        }
        assert satisfying == {HonestState.PASS}

    def test_a_state_the_graph_never_produces_would_have_been_admitted(self) -> None:
        """Why the mapping had to be derived rather than chosen.

        This documents the hazard executably: had a refusal been mapped to
        `FAIL`, the unchanged canonical predicate would have read it as condition
        (a) SATISFIED. The graph produces no such state, which is the whole point.
        """
        from arkali.control.capability.capability_graph import CapabilityQueryResult

        hazardous = CapabilityQueryResult(
            capability_id=CAPABILITY_ID, state=HonestState.FAIL, reason="hypothetical"
        )
        assert resolves(hazardous), "the predicate would admit a FAIL capability"
        assert HonestState.FAIL not in self._states()


class TestTheGraphDoesNotUsurpTheOtherConditions:
    def test_isolation_remains_condition_b_even_when_the_capability_resolves(
        self,
    ) -> None:
        """§4's conjunction, proven: the graph answers PASS and admission refuses.

        `control.isolation` owns tier satisfiability and
        `AUTHORITY_MAP.yaml` gives it `capability_state_when_unsatisfiable`. The
        graph must not answer that question, and admission must still refuse.
        """
        node = activated_node(tier="TRUST-4")
        references, _ = resolving_authorities(node)
        graph = activated_graph(node, references=references)
        assert graph.can_perform(CAPABILITY_ID).state is HonestState.PASS
        built = build_service(resolver=graph)
        built._contract.declare(declaration(required_trust_tier="TRUST-4"))
        decision = built.evaluate(request(WORKER))
        assert decision.outcome is AdmissionOutcome.ISOLATION_UNSATISFIED

    def test_resources_remain_condition_c(self) -> None:
        node = activated_node(tier=SATISFIABLE_TIER)
        references, _ = resolving_authorities(node)
        built = build_service(resolver=activated_graph(node, references=references))
        built._contract.declare(declaration())
        decision = built.evaluate(request(WORKER, in_flight=2))
        assert decision.outcome is AdmissionOutcome.RESOURCE_UNAVAILABLE


class TestAdmissionCachesNothing:
    def test_a_changed_authority_answer_is_observed_on_the_next_evaluation(
        self,
    ) -> None:
        """Through the real service, not through the graph alone."""
        node = activated_node(tier=SATISFIABLE_TIER)
        references, spies = resolving_authorities(node)
        built = service(activated_graph(node, references=references))
        assert built.evaluate(request(WORKER)).outcome is AdmissionOutcome.ADMITTED  # type: ignore[attr-defined]
        for spy in spies.values():
            spy.known = set()  # type: ignore[attr-defined]
        assert (
            built.evaluate(request(WORKER)).outcome  # type: ignore[attr-defined]
            is AdmissionOutcome.CAPABILITY_NOT_CONFIGURED
        )
        for spy in spies.values():
            spy.known = set(spy.asked)  # type: ignore[attr-defined]
        assert built.evaluate(request(WORKER)).outcome is AdmissionOutcome.ADMITTED  # type: ignore[attr-defined]

    def test_every_admission_re_asks_every_authority(self) -> None:
        node = activated_node(tier=SATISFIABLE_TIER)
        references, spies = resolving_authorities(node)
        built = service(activated_graph(node, references=references))
        for _ in range(3):
            built.evaluate(request(WORKER))  # type: ignore[attr-defined]
        for name, spy in spies.items():
            assert len(spy.asked) == 3, f"{name} was asked {len(spy.asked)} times"  # type: ignore[attr-defined]

    def test_the_admission_evaluator_still_holds_no_verdict(self) -> None:
        node = activated_node(tier=SATISFIABLE_TIER)
        references, _ = resolving_authorities(node)
        built = build_service(resolver=activated_graph(node, references=references))
        assert set(vars(built._capability)) == {"_resolver"}
