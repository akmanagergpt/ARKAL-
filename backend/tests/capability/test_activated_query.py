"""The activated deterministic capability query (Phase 9B, Package 2).

`MS §Capability Graph` requires ARKALI to answer "Can I perform this?"
deterministically from the graph, and `EXECUTION_AND_CAPABILITY.md` §1 says how:
resolve every `*_ref` at query time against its owning authority.

THE MAPPING UNDER TEST, AND WHERE IT COMES FROM. §4 admits when "its capability
resolves other than `NOT_CONFIGURED`", pairing *resolving* with *not being*
`NOT_CONFIGURED`; `docs/contracts/worker.md` §7 glosses the accepted Phase 8
outcome identically. So a capability that did not resolve is `NOT_CONFIGURED`,
and the affirmative answer is `PASS`. These controls assert that mapping and
assert that no other state is ever produced — in particular never `FAIL`, which
the canonical set assigns to no capability query and which the accepted Phase 8
predicate would read as success.

Nothing here writes a field name, an authority or a target kind: every subject is
derived from the canonical `capability_node:` block.
"""

from __future__ import annotations

import pathlib
from typing import get_origin

import pytest

from arkali.control.capability.capability_graph import CapabilityGraph
from arkali.control.capability.capability_node import (
    CapabilityNode,
    ConfiguredState,
)
from arkali.control.capability.reference_authority import CapabilityReferenceAuthority
from arkali.control.capability.reference_resolution import ReferenceResolvers
from arkali.kernel.contracts.capability_errors import InvalidCapabilityReference
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]

#: The requirement whose Phase column governs when activation happens.
ACTIVATION_REQUIREMENT = "ARK-REQ-0048"


@pytest.fixture(scope="module")
def binding() -> CapabilityReferenceAuthority:
    return CapabilityReferenceAuthority.load(REPO)


@pytest.fixture(scope="module")
def activation_phase() -> str:
    from arkali.control.specification.register_parser import RequirementRegister

    phase = RequirementRegister.load(REPO).get(ACTIVATION_REQUIREMENT).owning_phase
    assert phase, "activation phase could not be derived from the register"
    return phase


class Authority:
    """A composition-root resolver that records and can change its answer."""

    def __init__(self, answer: bool = True) -> None:
        self.answer = answer
        self.asked: list[str] = []

    def resolves(self, reference: str) -> bool:
        self.asked.append(reference)
        return self.answer


def node(
    binding: CapabilityReferenceAuthority,
    capability_id: str = "build.compile",
    *,
    configured: bool = True,
    **overrides: object,
) -> CapabilityNode:
    """A node holding one reference in every externally-owned field."""
    fields: dict[str, object] = {
        "id": capability_id,
        "version": 1,
        "isolation_tier": "TRUST-2",
        "configured_state": (
            ConfiguredState.CONFIGURED if configured else ConfiguredState.UNCONFIGURED
        ),
    }
    for declared in binding.external():
        annotation = CapabilityNode.model_fields[declared.field].annotation
        reference = f"{declared.target_kind}.{capability_id}"
        fields[declared.field] = (
            (reference,) if get_origin(annotation) is tuple else reference
        )
    fields.update(overrides)
    return CapabilityNode(**fields)  # type: ignore[arg-type]


def authorities(
    binding: CapabilityReferenceAuthority, answer: bool = True
) -> tuple[ReferenceResolvers, dict[str, Authority]]:
    spies = {name: Authority(answer) for name in binding.authorities()}
    return ReferenceResolvers(binding, spies), spies


def graph(
    binding: CapabilityReferenceAuthority,
    activation_phase: str,
    *nodes: CapabilityNode,
    references: object = None,
    current_phase: str | None = None,
) -> CapabilityGraph:
    return CapabilityGraph(
        nodes or (node(binding),),
        activation_phase=activation_phase,
        current_phase=current_phase or activation_phase,
        references=references,  # type: ignore[arg-type]
    )


class TestTheAffirmativeAnswerIsEarned:
    def test_a_fully_resolved_configured_capability_passes(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, _ = authorities(binding)
        result = graph(
            binding, activation_phase, references=composed
        ).can_perform("build.compile")
        assert result.state is HonestState.PASS
        assert result.is_determinate

    def test_pass_requires_every_authority_to_have_been_asked(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        """An affirmative answer no authority contributed to would be invented."""
        composed, spies = authorities(binding)
        assert (
            graph(binding, activation_phase, references=composed)
            .can_perform("build.compile")
            .state
            is HonestState.PASS
        )
        assert spies, "no authority is declared; this control would be vacuous"
        for name, spy in spies.items():
            assert spy.asked, f"{name} was never asked yet the answer was PASS"

    def test_the_answer_names_the_activated_canonical_source(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, _ = authorities(binding)
        result = graph(
            binding, activation_phase, references=composed
        ).can_perform("build.compile")
        assert "EXECUTION_AND_CAPABILITY" in result.authoritative_source


class TestEveryNegativeIsNotConfigured:
    """The derived mapping. Never FAIL, never UNSUPPORTED, never PASS."""

    def _negatives(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> list[tuple[str, HonestState]]:
        refusing, _ = authorities(binding, answer=False)
        found: list[tuple[str, HonestState]] = []
        found.append((
            "no authority composed",
            graph(binding, activation_phase).can_perform("build.compile").state,
        ))
        found.append((
            "empty resolver set",
            graph(
                binding, activation_phase, references=ReferenceResolvers(binding, {})
            ).can_perform("build.compile").state,
        ))
        found.append((
            "refusing authority",
            graph(binding, activation_phase, references=refusing)
            .can_perform("build.compile").state,
        ))
        resolving, _ = authorities(binding)
        found.append((
            "unconfigured node",
            graph(
                binding,
                activation_phase,
                node(binding, configured=False),
                references=resolving,
            ).can_perform("build.compile").state,
        ))
        return found

    def test_every_refusal_is_not_configured(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        cases = self._negatives(binding, activation_phase)
        assert cases, "no negative case was built; this control would be vacuous"
        for label, state in cases:
            assert state is HonestState.NOT_CONFIGURED, f"{label} produced {state}"

    def test_no_refusal_is_ever_fail(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        """`FAIL` is assigned to no capability query by the canonical set.

        It is also unsafe: the accepted Phase 8 predicate is
        `state is not NOT_CONFIGURED`, so a `FAIL` capability would be read as
        condition (a) SATISFIED and would admit work whose references do not
        resolve.
        """
        for label, state in self._negatives(binding, activation_phase):
            assert state is not HonestState.FAIL, f"{label} produced FAIL"
            assert state is not HonestState.UNSUPPORTED, f"{label} produced UNSUPPORTED"
            assert state is not HonestState.PASS, f"{label} produced PASS"

    def test_a_per_reference_fail_does_not_surface_as_a_graph_level_fail(
        self, binding: CapabilityReferenceAuthority
    ) -> None:
        """Package 1's internal outcome is not the graph-level answer."""
        refusing, _ = authorities(binding, answer=False)
        resolutions = refusing.resolve(node(binding))
        assert resolutions and all(r.state is HonestState.FAIL for r in resolutions)

    def test_an_unconfigured_node_is_refused_even_when_all_refs_resolve(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, _ = authorities(binding)
        result = graph(
            binding,
            activation_phase,
            node(binding, configured=False),
            references=composed,
        ).can_perform("build.compile")
        assert result.state is HonestState.NOT_CONFIGURED
        assert ConfiguredState.UNCONFIGURED.value in result.reason


class TestPrerequisitesAreTransitiveAndGraphOwned:
    def _pair(
        self, binding: CapabilityReferenceAuthority, *, base_configured: bool
    ) -> tuple[CapabilityNode, CapabilityNode]:
        base = node(binding, "build.base", configured=base_configured)
        top = node(binding, "build.compile", prerequisites=("build.base",))
        return base, top

    def test_a_capability_whose_prerequisite_resolved_passes(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        base, top = self._pair(binding, base_configured=True)
        composed, _ = authorities(binding)
        subject = graph(binding, activation_phase, base, top, references=composed)
        assert subject.can_perform("build.compile").state is HonestState.PASS

    def test_an_unresolved_prerequisite_refuses_the_dependent_capability(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        base, top = self._pair(binding, base_configured=False)
        composed, _ = authorities(binding)
        subject = graph(binding, activation_phase, base, top, references=composed)
        assert subject.can_perform("build.base").state is HonestState.NOT_CONFIGURED
        result = subject.can_perform("build.compile")
        assert result.state is HonestState.NOT_CONFIGURED
        assert "build.base" in result.reason

    def test_a_prerequisite_cycle_fails_closed_rather_than_answering(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        """A malformed graph is not an unconfigured capability."""
        first = node(binding, "build.first", prerequisites=("build.second",))
        second = node(binding, "build.second", prerequisites=("build.first",))
        composed, _ = authorities(binding)
        subject = graph(binding, activation_phase, first, second, references=composed)
        with pytest.raises(InvalidCapabilityReference):
            subject.can_perform("build.first")

    def test_a_fallback_never_rescues_an_unresolved_capability(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        """Fallback SELECTION has no canonical semantics here, so it decides nothing."""
        healthy = node(binding, "build.spare")
        broken = node(
            binding, "build.compile", configured=False, fallback_refs=("build.spare",)
        )
        composed, _ = authorities(binding)
        subject = graph(binding, activation_phase, healthy, broken, references=composed)
        assert subject.can_perform("build.spare").state is HonestState.PASS
        assert (
            subject.can_perform("build.compile").state is HonestState.NOT_CONFIGURED
        )


class TestFieldsWithNoCanonicalSemanticsAreNotEvaluated:
    """Nothing is invented for a field no authority defines a rule for."""

    @pytest.mark.parametrize(
        "overrides",
        [
            {"runtime_requirements": {"min_memory_mb": 512}},
            {"runtime_requirements": {}},
            {"platform_support": ("windows",)},
            {"platform_support": ()},
            {"isolation_tier": "TRUST-4"},
            {"isolation_tier": "TRUST-0"},
        ],
    )
    def test_the_answer_is_unaffected(
        self,
        binding: CapabilityReferenceAuthority,
        activation_phase: str,
        overrides: dict[str, object],
    ) -> None:
        composed, _ = authorities(binding)
        subject = graph(
            binding, activation_phase, node(binding, **overrides), references=composed
        )
        assert subject.can_perform("build.compile").state is HonestState.PASS


class TestDeterminismWithoutCaching:
    def test_identical_inputs_produce_an_identical_result(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, _ = authorities(binding)
        subject = graph(binding, activation_phase, references=composed)
        rendered = {
            subject.can_perform("build.compile").model_dump_json() for _ in range(5)
        }
        assert len(rendered) == 1, "state, reason or source varied between calls"

    def test_the_reason_follows_the_canonical_schema_order(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        """Two references broken at once: the FIRST declared field is reported."""
        refusing, _ = authorities(binding, answer=False)
        result = graph(
            binding, activation_phase, references=refusing
        ).can_perform("build.compile")
        first = binding.external()[0].field
        assert result.reason.startswith(first), result.reason

    def test_every_query_re_asks_every_authority(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, spies = authorities(binding)
        subject = graph(binding, activation_phase, references=composed)
        for _ in range(3):
            subject.can_perform("build.compile")
        for name, spy in spies.items():
            assert len(spy.asked) == 3, f"{name} was asked {len(spy.asked)} times"

    def test_a_changed_authority_answer_changes_the_next_query(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, spies = authorities(binding)
        subject = graph(binding, activation_phase, references=composed)
        assert subject.can_perform("build.compile").state is HonestState.PASS
        for spy in spies.values():
            spy.answer = False
        assert (
            subject.can_perform("build.compile").state is HonestState.NOT_CONFIGURED
        )
        for spy in spies.values():
            spy.answer = True
        assert subject.can_perform("build.compile").state is HonestState.PASS

    def test_the_graph_stores_no_verdict(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, _ = authorities(binding)
        subject = graph(binding, activation_phase, references=composed)
        subject.can_perform("build.compile")
        assert set(vars(subject)) == {
            "_nodes",
            "activation_phase",
            "current_phase",
            "_references",
        }


class TestFailClosedAndPreActivation:
    def test_an_unknown_capability_still_raises(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, _ = authorities(binding)
        with pytest.raises(InvalidCapabilityReference):
            graph(binding, activation_phase, references=composed).can_perform(
                "no.such.capability"
            )

    def test_pre_activation_is_unchanged_even_when_fully_composed(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        """ADR-0003's split survives Package 2."""
        composed, spies = authorities(binding)
        subject = graph(
            binding, activation_phase, references=composed, current_phase="8"
        )
        result = subject.can_perform("build.compile")
        assert result.state is HonestState.NOT_CONFIGURED
        assert not any(spy.asked for spy in spies.values()), (
            "an authority was consulted before activation"
        )

    def test_activation_is_still_a_derived_phase_fact(
        self, binding: CapabilityReferenceAuthority, activation_phase: str
    ) -> None:
        composed, _ = authorities(binding)
        subject = graph(binding, activation_phase, references=composed)
        assert subject.is_activated
        with pytest.raises(AttributeError):
            subject.is_activated = True  # type: ignore[misc]
