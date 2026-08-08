"""Negative controls for the state-machine primitive itself.

Every control uses an in-memory fixture machine. No accepted repository state is
read or written here, and no canonical machine is mutated.

A control that merely asserts "something raised" proves nothing (F-0017), so each
asserts the specific error type, and the definition-level controls assert that a
*valid* definition of the same shape is accepted — otherwise a control could pass
because the constructor rejects everything.
"""

from __future__ import annotations

import pytest
from arkali.kernel.contracts.state_machine_errors import (
    ForbiddenTransition,
    GuardRejected,
    IllegalTransition,
    StateMachineDefinitionError,
    StateMutationBypass,
    TerminalStateEscape,
    UnknownState,
)
from arkali.kernel.contracts.state_machine import (
    StateMachine,
    StateMachineDefinition,
    TransitionDecision,
)

SOURCE = "in-memory test fixture"


def fixture_definition(**overrides: object) -> StateMachineDefinition:
    base: dict[str, object] = {
        "machine": "Fixture",
        "authority": "test.fixture",
        "authoritative_source": SOURCE,
        "states": ("A", "B", "C", "END"),
        "transitions": (("A", "B"), ("B", "C"), ("C", "END")),
        "forbidden": (("A", "C"),),
        "terminal": ("END",),
    }
    base.update(overrides)
    return StateMachineDefinition(**base)  # type: ignore[arg-type]


class TestDefinitionFailsClosed:
    def test_the_baseline_fixture_is_valid(self) -> None:
        """Proves the rejections below are specific, not blanket refusal."""
        assert fixture_definition().machine == "Fixture"

    def test_transition_naming_an_undeclared_state_is_rejected(self) -> None:
        with pytest.raises(StateMachineDefinitionError):
            fixture_definition(transitions=(("A", "GHOST"),))

    def test_forbidden_naming_an_undeclared_state_is_rejected(self) -> None:
        with pytest.raises(StateMachineDefinitionError):
            fixture_definition(forbidden=(("GHOST", "A"),))

    def test_a_pair_that_is_both_legal_and_forbidden_is_rejected(self) -> None:
        with pytest.raises(StateMachineDefinitionError):
            fixture_definition(transitions=(("A", "B"),), forbidden=(("A", "B"),))

    def test_terminal_state_with_an_outgoing_transition_is_rejected(self) -> None:
        with pytest.raises(StateMachineDefinitionError):
            fixture_definition(
                transitions=(("A", "B"), ("END", "A")), terminal=("END",)
            )

    def test_undeclared_terminal_state_is_rejected(self) -> None:
        with pytest.raises(StateMachineDefinitionError):
            fixture_definition(terminal=("GHOST",))

    def test_duplicate_state_identifier_is_rejected(self) -> None:
        with pytest.raises(StateMachineDefinitionError):
            fixture_definition(states=("A", "A", "B", "C", "END"))

    def test_empty_state_set_is_rejected(self) -> None:
        with pytest.raises(StateMachineDefinitionError):
            fixture_definition(states=(), transitions=(), forbidden=(), terminal=())

    def test_guard_on_a_non_existent_transition_is_rejected(self) -> None:
        with pytest.raises(StateMachineDefinitionError):
            StateMachine(fixture_definition(), {("A", "END"): lambda _c: True})


class TestTransitionRefusals:
    def test_declared_transition_is_accepted(self) -> None:
        outcome = StateMachine(fixture_definition()).evaluate("A", "B")
        assert outcome.decision is TransitionDecision.ACCEPTED

    def test_explicitly_forbidden_pair_raises_forbidden(self) -> None:
        with pytest.raises(ForbiddenTransition):
            StateMachine(fixture_definition()).evaluate("A", "C")

    def test_undeclared_pair_raises_illegal_but_not_forbidden(self) -> None:
        with pytest.raises(IllegalTransition) as caught:
            StateMachine(fixture_definition()).evaluate("B", "A")
        assert not isinstance(caught.value, ForbiddenTransition)

    def test_terminal_escape_raises_its_own_type(self) -> None:
        with pytest.raises(TerminalStateEscape):
            StateMachine(fixture_definition()).evaluate("END", "A")

    @pytest.mark.parametrize("bad", ["", "  ", "ghost", None, 3, ("A",)])
    def test_malformed_or_unknown_state_raises_unknown_state(self, bad: object) -> None:
        with pytest.raises(UnknownState):
            StateMachine(fixture_definition()).evaluate(bad, "B")  # type: ignore[arg-type]

    def test_guard_rejection_raises_its_own_type(self) -> None:
        machine = StateMachine(
            fixture_definition(), {("A", "B"): lambda ctx: bool(ctx.get("ok"))}
        )
        with pytest.raises(GuardRejected):
            machine.evaluate("A", "B", {})
        assert machine.evaluate("A", "B", {"ok": True}).guard_applied is True


class TestNoMutationBypass:
    def test_there_is_no_public_setter_for_state(self) -> None:
        instance = StateMachine(fixture_definition()).start("A")
        with pytest.raises((AttributeError, StateMutationBypass)):
            instance.state = "END"  # type: ignore[misc]
        assert instance.state == "A"

    def test_private_assignment_is_refused(self) -> None:
        instance = StateMachine(fixture_definition()).start("A")
        with pytest.raises(StateMutationBypass):
            instance._state = "END"
        assert instance.state == "A"

    def test_attribute_deletion_is_refused(self) -> None:
        instance = StateMachine(fixture_definition()).start("A")
        with pytest.raises(StateMutationBypass):
            del instance._state
        assert instance.state == "A"

    def test_new_attributes_cannot_be_attached(self) -> None:
        instance = StateMachine(fixture_definition()).start("A")
        with pytest.raises(StateMutationBypass):
            instance.injected = "END"  # type: ignore[attr-defined]

    def test_refused_apply_leaves_state_untouched(self) -> None:
        instance = StateMachine(fixture_definition()).start("A")
        with pytest.raises(ForbiddenTransition):
            instance.apply("C")
        assert instance.state == "A"


class TestDeterminism:
    def test_same_inputs_give_byte_identical_outcomes(self) -> None:
        machine = StateMachine(fixture_definition())
        rendered = {machine.evaluate("A", "B").model_dump_json() for _ in range(10)}
        assert len(rendered) == 1

    def test_outcome_is_immutable(self) -> None:
        outcome = StateMachine(fixture_definition()).evaluate("A", "B")
        with pytest.raises(Exception):
            outcome.target = "C"  # type: ignore[misc]
