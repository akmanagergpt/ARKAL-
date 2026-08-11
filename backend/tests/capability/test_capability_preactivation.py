"""Pre-activation behaviour of the Capability Graph (ARK-REQ-0049, ADR-0003).

The activation phase is not written in this test either. It is derived from the
requirement register, where ARK-REQ-0048 ("Schema at Phase 3, activation at Phase
9B") carries it in the Phase column. If governance ever moves activation, this
test moves with it instead of asserting a stale constant.
"""

from __future__ import annotations

import pathlib

import pytest

from arkali.control.capability.capability_graph import CapabilityGraph
from arkali.control.capability.capability_node import CapabilityNode, ConfiguredState
from arkali.control.specification.register_parser import RequirementRegister
from arkali.kernel.contracts.capability_errors import (
    InvalidCapabilityReference,
    PrematureActivation,
)
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]

#: The requirement whose Phase column governs when activation happens.
ACTIVATION_REQUIREMENT = "ARK-REQ-0048"
#: The requirement whose Phase column governs when the schema is delivered.
SCHEMA_REQUIREMENT = "ARK-REQ-0045"


@pytest.fixture(scope="module")
def register() -> RequirementRegister:
    return RequirementRegister.load(REPO)


@pytest.fixture(scope="module")
def activation_phase(register: RequirementRegister) -> str:
    phase = register.get(ACTIVATION_REQUIREMENT).owning_phase
    assert phase, "activation phase could not be derived from the register"
    return phase


@pytest.fixture(scope="module")
def schema_phase(register: RequirementRegister) -> str:
    phase = register.get(SCHEMA_REQUIREMENT).owning_phase
    assert phase, "schema phase could not be derived from the register"
    return phase


def node(**overrides: object) -> CapabilityNode:
    base: dict[str, object] = {
        "id": "build.compile",
        "version": 1,
        "isolation_tier": "TRUST-2",
    }
    base.update(overrides)
    return CapabilityNode(**base)  # type: ignore[arg-type]


def graph(activation: str, current: str) -> CapabilityGraph:
    return CapabilityGraph(
        [node()], activation_phase=activation, current_phase=current
    )


class TestGovernanceDerivation:
    def test_schema_and_activation_are_different_phases(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        """ADR-0003's whole point. If these ever match, the split has collapsed."""
        assert schema_phase != activation_phase

    def test_activation_is_not_the_current_phase(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        assert activation_phase != schema_phase


class TestPreActivationQueries:
    def test_query_returns_not_configured(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        result = graph(activation_phase, schema_phase).can_perform("build.compile")
        assert result.state is HonestState.NOT_CONFIGURED

    def test_not_configured_is_a_determinate_answer(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        """ARK-REQ-0046's determinism is satisfied by NOT_CONFIGURED, not bypassed."""
        result = graph(activation_phase, schema_phase).can_perform("build.compile")
        assert result.is_determinate

    def test_answer_is_identical_on_repeat(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        subject = graph(activation_phase, schema_phase)
        answers = {
            subject.can_perform("build.compile").model_dump_json() for _ in range(5)
        }
        assert len(answers) == 1

    def test_configured_state_does_not_leak_into_the_answer(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        """A node marked CONFIGURED must still answer NOT_CONFIGURED pre-activation.

        This is the exact shape of the defect ADR-0003 prevents: treating a
        node's own declared state as evidence that its referenced authorities
        exist.
        """
        subject = CapabilityGraph(
            [node(configured_state=ConfiguredState.CONFIGURED)],
            activation_phase=activation_phase,
            current_phase=schema_phase,
        )
        assert subject.can_perform("build.compile").state is HonestState.NOT_CONFIGURED

    def test_unknown_capability_raises_rather_than_answering(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        """A typo must not be answered with a governed pre-activation verdict."""
        with pytest.raises(InvalidCapabilityReference):
            graph(activation_phase, schema_phase).can_perform("no.such.capability")

    def test_graph_reports_itself_inactive(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        assert graph(activation_phase, schema_phase).is_activated is False


class TestPrematureActivationIsRejected:
    def test_explicit_activation_is_refused(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        with pytest.raises(PrematureActivation):
            graph(activation_phase, schema_phase).activate()

    @pytest.mark.parametrize("pretended", ["4", "5", "9", "23"])
    def test_activation_refused_from_any_earlier_phase(
        self, pretended: str, activation_phase: str
    ) -> None:
        if pretended == activation_phase:
            pytest.skip("that phase is the activation phase")
        with pytest.raises(PrematureActivation):
            graph(activation_phase, pretended).activate()

    def test_reaching_the_activation_phase_alone_invents_no_verdict(
        self, activation_phase: str
    ) -> None:
        """REPLACES the Phase 3 tripwire, with a strictly stronger obligation.

        Until Phase 9B Package 2 this asserted that `can_perform` RAISED
        `PrematureActivation` at the activation phase, because Phase 3 refused to
        implement a forward phase. Package 2 is that phase, so the refusal is
        gone — but the obligation it protected is not, and it is now larger: the
        answer must be DERIVED FROM LIVE AUTHORITIES, never invented.

        A graph standing at its activation phase with no reference authority
        composed has nothing to derive from. It must therefore answer
        `NOT_CONFIGURED` — the same determinate answer, for the same canonical
        reason ADR-0003 gives before activation: no referenced authority can
        answer. It must never answer affirmatively. See
        `tests/capability/test_activated_query.py` for the full derivation
        controls, and `tests/execution/test_activated_admission.py` for the same
        obligation proven through the real `AdmissionService`.
        """
        result = graph(activation_phase, activation_phase).can_perform(
            "build.compile"
        )
        assert result.state is HonestState.NOT_CONFIGURED
        assert result.is_determinate
        assert result.state is not HonestState.PASS

    def test_activation_state_is_derived_not_settable(
        self, schema_phase: str, activation_phase: str
    ) -> None:
        subject = graph(activation_phase, schema_phase)
        with pytest.raises(AttributeError):
            subject.is_activated = True  # type: ignore[misc]
