"""ERR-002: Plugin Lifecycle `REMOVED` is terminal (closes F-0018).

Human ruling. §6's `any→QUARANTINED` previously admitted `REMOVED→QUARANTINED`,
leaving the machine with no terminal state. The ruling narrows `any` to the
non-removed states; §6 now reads `any pre-REMOVED→QUARANTINED` with an explicit
`Forbidden: REMOVED→any`.

These controls are permanent. They assert both halves of the ruling: that the
legal quarantine paths survived the narrowing, and that no path out of `REMOVED`
exists. A control proving only the second half would pass equally well if the
narrowing had deleted every quarantine transition.
"""

from __future__ import annotations

import pathlib

import pytest
from arkali.control.architecture.state_machine_spec import StateMachineInventory
from arkali.engineering.plugin.plugin_lifecycle_state_machine import build
from arkali.kernel.contracts.state_machine_errors import (
    ForbiddenTransition,
    StateMachineError,
    StateMutationBypass,
    TerminalStateEscape,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
MACHINE = "PluginLifecycle"
REMOVED = "REMOVED"
QUARANTINED = "QUARANTINED"

#: The states the ruling keeps able to reach QUARANTINED.
QUARANTINABLE = (
    "DISCOVERED",
    "MANIFEST_VALIDATED",
    "PERMISSIONS_DECLARED",
    "APPROVED",
    "ENABLED",
    "DISABLED",
)


@pytest.fixture(scope="module")
def spec():
    return StateMachineInventory.load(REPO).get(MACHINE)


class TestLegalQuarantinePathsSurvive:
    """The narrowing must not have removed the transitions it was not about."""

    @pytest.mark.parametrize("source", QUARANTINABLE)
    def test_non_terminal_state_may_still_be_quarantined(self, source: str) -> None:
        outcome = build().evaluate(source, QUARANTINED)
        assert outcome.target == QUARANTINED

    @pytest.mark.parametrize("source", QUARANTINABLE)
    def test_canonical_document_still_declares_the_transition(
        self, source: str, spec
    ) -> None:
        assert (source, QUARANTINED) in spec.transition_set

    def test_quarantine_exits_are_unchanged(self) -> None:
        machine = build()
        assert machine.evaluate(QUARANTINED, "DISABLED").target == "DISABLED"
        assert machine.evaluate(QUARANTINED, REMOVED).target == REMOVED

    def test_the_quarantinable_set_is_exactly_the_non_removed_non_quarantined(
        self, spec
    ) -> None:
        """Derived from the document, so the list above cannot silently rot."""
        declared = {src for src, dst in spec.transitions if dst == QUARANTINED}
        assert declared == set(QUARANTINABLE)


class TestRemovedIsTerminal:
    def test_removed_to_quarantined_is_rejected(self) -> None:
        with pytest.raises(StateMachineError) as caught:
            build().evaluate(REMOVED, QUARANTINED)
        assert isinstance(caught.value, (TerminalStateEscape, ForbiddenTransition))

    @pytest.mark.parametrize(
        "target",
        [
            "DISCOVERED",
            "MANIFEST_VALIDATED",
            "PERMISSIONS_DECLARED",
            "APPROVED",
            "ENABLED",
            "DISABLED",
            "QUARANTINED",
            "REMOVED",
        ],
    )
    def test_removed_to_any_state_is_rejected(self, target: str) -> None:
        with pytest.raises(StateMachineError):
            build().evaluate(REMOVED, target)

    def test_removed_has_no_outgoing_transition_at_all(self) -> None:
        definition = build().definition
        assert [t for t in definition.transitions if t[0] == REMOVED] == []

    def test_removed_is_declared_terminal(self) -> None:
        assert REMOVED in build().definition.terminal
        assert build().start(REMOVED).is_terminal

    def test_canonical_document_agrees(self, spec) -> None:
        assert spec.terminal_states == (REMOVED,)
        assert (REMOVED, QUARANTINED) not in spec.transition_set
        assert (REMOVED, QUARANTINED) in spec.forbidden_set

    def test_an_instance_in_removed_cannot_be_moved(self) -> None:
        instance = build().start(REMOVED)
        with pytest.raises(TerminalStateEscape):
            instance.apply(QUARANTINED)
        assert instance.state == REMOVED

    def test_removed_cannot_be_escaped_by_direct_mutation(self) -> None:
        """Reinstallation by mutating the removed instance must be impossible."""
        instance = build().start(REMOVED)
        with pytest.raises(StateMutationBypass):
            instance._state = "ENABLED"
        with pytest.raises((AttributeError, StateMutationBypass)):
            instance.state = "ENABLED"  # type: ignore[misc]
        assert instance.state == REMOVED


class TestReintroductionUsesANewLifecycle:
    def test_a_new_revision_starts_its_own_instance(self) -> None:
        """The ruling's positive half: reintroduction is a new lifecycle."""
        machine = build()
        removed = machine.start(REMOVED)
        reintroduced = machine.start("DISCOVERED")

        assert reintroduced.state == "DISCOVERED"
        assert removed.state == REMOVED
        assert reintroduced is not removed

    def test_the_new_instance_runs_the_full_lifecycle_independently(self) -> None:
        machine = build()
        removed = machine.start(REMOVED)
        fresh = machine.start("DISCOVERED")

        fresh.apply("MANIFEST_VALIDATED")
        fresh.apply("PERMISSIONS_DECLARED")
        assert fresh.state == "PERMISSIONS_DECLARED"

        # The removed instance is untouched by the new one's progress.
        assert removed.state == REMOVED
        assert removed.is_terminal

    def test_a_new_instance_may_itself_reach_removed_and_stop(self) -> None:
        machine = build()
        fresh = machine.start("DISCOVERED")
        fresh.apply(QUARANTINED)
        fresh.apply(REMOVED)
        assert fresh.is_terminal
        with pytest.raises(TerminalStateEscape):
            fresh.apply(QUARANTINED)
