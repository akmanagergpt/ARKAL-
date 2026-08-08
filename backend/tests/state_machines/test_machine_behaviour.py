"""Behavioural verification of the twelve machines (ARK-REQ-0043, ARK-REQ-0044).

File presence and table definitions are not verification. Every assertion here
executes a real transition against a real machine and checks the outcome, and
every negative assertion checks the *reason* the transition was refused, so a
control cannot pass because something unrelated happened to raise.
"""

from __future__ import annotations

import itertools
import pathlib

import pytest
from arkali.kernel.contracts.state_machine_errors import (
    ForbiddenTransition,
    GuardRejected,
    IllegalTransition,
    StateMachineError,
    StateMutationBypass,
    TerminalStateEscape,
    UnknownState,
)
from arkali.kernel.contracts.state_machine import TransitionDecision

from tests.state_machines.registry import MACHINE_MODULES, all_machines

REPO = pathlib.Path(__file__).resolve().parents[3]
NAMES = sorted(MACHINE_MODULES)

#: Contexts sufficient to satisfy every guard, per machine and transition.
SATISFYING_CONTEXT: dict[tuple[str, str, str], dict[str, object]] = {
    ("Candidate", "ACCEPTED", "PROMOTED"): {"evidence_set": ("EV-0001",)},
    ("WorkflowExecution", "WAITING_APPROVAL", "RUNNING"): {
        "human_approval_recorded": True
    },
    ("Release", "SIGNED_READY", "RELEASED"): {
        "human_gate_7_recorded": True,
        "evidence_complete": True,
    },
    ("BackupRestore", "BACKUP_RUNNING", "BACKUP_VERIFIED"): {"restore_proven": True},
    ("CoreUpgrade", "SNAPSHOT_TAKEN", "CANDIDATE_BUILT"): {
        "recovery_supervisor_verified": True
    },
    ("CoreUpgrade", "AWAITING_GATE_2", "PROMOTED"): {"human_gate_2_recorded": True},
    ("CoreUpgrade", "PROMOTED", "ROLLED_BACK"): {"invoker": "lifecycle.recovery"},
    ("EvolutionCampaign", "DECLARED", "RUNNING"): {
        "objective": "reduce p95 latency",
        "baseline_metrics": {"p95_ms": 400},
        "budgets": ("time", "cost", "tokens", "attempts", "risk", "scope"),
    },
    ("HardeningRound", "DECLARED", "RUNNING"): {"budgets_declared": True},
    ("ImportProject", "STATICALLY_INSPECTED", "TIER_ASSIGNED"): {
        "tier_assigned_by": "control.isolation"
    },
    ("ImportProject", "TIER_ASSIGNED", "APPROVED_FOR_EXECUTION"): {
        "static_inspection_complete": True
    },
}


def _context(machine: str, source: str, target: str) -> dict[str, object]:
    """A context sufficient to satisfy any guard on this transition."""
    if machine == "PluginLifecycle" and (source, target) == (
        "PERMISSIONS_DECLARED",
        "APPROVED",
    ):
        return {
            "canonical_operation_classes": _operation_classes(),
            "declared_permissions": ("READ_FILE",),
        }
    return dict(SATISFYING_CONTEXT.get((machine, source, target), {}))


def _operation_classes() -> tuple[str, ...]:
    """The fourteen classes, read from the authority map — never hard-coded."""
    import yaml

    raw = yaml.safe_load(
        (REPO / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
    )
    classes = tuple(raw["operation_classes"])
    assert classes, "authority map declares no operation classes"
    return classes


class TestEveryLegalTransition:
    @pytest.mark.parametrize("name", NAMES)
    def test_every_declared_transition_is_accepted(self, name: str) -> None:
        machine = all_machines()[name]
        declared = machine.definition.transitions
        assert declared, f"{name}: no transitions to exercise"
        for source, target in declared:
            outcome = machine.evaluate(source, target, _context(name, source, target))
            assert outcome.decision is TransitionDecision.ACCEPTED
            assert (outcome.source, outcome.target) == (source, target)
            assert outcome.machine == name

    @pytest.mark.parametrize("name", NAMES)
    def test_instance_reaches_the_target_state(self, name: str) -> None:
        machine = all_machines()[name]
        for source, target in machine.definition.transitions:
            instance = machine.start(source)
            assert instance.state == source
            instance.apply(target, _context(name, source, target))
            assert instance.state == target


class TestEveryForbiddenTransition:
    @pytest.mark.parametrize("name", NAMES)
    def test_explicitly_forbidden_pairs_are_refused(self, name: str) -> None:
        machine = all_machines()[name]
        forbidden = machine.definition.forbidden
        if not forbidden:
            pytest.skip(f"{name} declares no explicit forbidden pairs")
        for source, target in forbidden:
            with pytest.raises(IllegalTransition) as caught:
                machine.evaluate(source, target)
            # A terminal source is refused earlier, and that subtype is also an
            # IllegalTransition - both are correct refusals of the same pair.
            assert isinstance(
                caught.value, (ForbiddenTransition, TerminalStateEscape)
            ), f"{name}: {source}->{target} refused for an unrelated reason"

    @pytest.mark.parametrize("name", NAMES)
    def test_every_undeclared_pair_is_refused(self, name: str) -> None:
        """The complement of the relation must be unreachable, not merely unused."""
        machine = all_machines()[name]
        states = machine.definition.states
        legal = machine.definition.transition_set
        checked = 0
        for source, target in itertools.product(states, repeat=2):
            if (source, target) in legal:
                continue
            with pytest.raises(StateMachineError):
                machine.evaluate(source, target, _context(name, source, target))
            checked += 1
        assert checked > 0, f"{name}: no undeclared pair existed to reject"

    def test_candidate_cannot_skip_verification(self) -> None:
        """The sharpest canonical prohibition, asserted by name."""
        machine = all_machines()["Candidate"]
        for source in ("CREATED", "VERIFYING"):
            with pytest.raises(ForbiddenTransition):
                machine.evaluate(source, "PROMOTED", {"evidence_set": ("EV-0001",)})


class TestTerminalStates:
    @pytest.mark.parametrize("name", NAMES)
    def test_no_escape_from_a_terminal_state(self, name: str) -> None:
        machine = all_machines()[name]
        terminal = machine.definition.terminal
        if not terminal:
            pytest.skip(f"{name} declares no terminal state")
        for state in terminal:
            for target in machine.definition.states:
                with pytest.raises(TerminalStateEscape):
                    machine.evaluate(state, target)

    @pytest.mark.parametrize("name", NAMES)
    def test_instance_reports_terminality(self, name: str) -> None:
        machine = all_machines()[name]
        if not machine.definition.terminal:
            pytest.skip(f"{name} declares no terminal state")
        for state in machine.definition.terminal:
            assert machine.start(state).is_terminal

    def test_evolution_campaign_cannot_restart_for_a_better_verdict(self) -> None:
        """§10: all four exits terminal; no restart to obtain a different exit."""
        machine = all_machines()["EvolutionCampaign"]
        for exit_state in ("ESCALATED", "BLOCKED"):
            with pytest.raises(TerminalStateEscape):
                machine.evaluate(exit_state, "RUNNING")


def _all_guarded() -> list[tuple[str, str, str]]:
    """Every guarded transition, derived from the machines themselves.

    Deriving this rather than listing it by hand means a guard added later is
    automatically covered; a hand-written list would silently stop being
    exhaustive, which is the F-0016 defect class.
    """
    found = [
        (name, source, target)
        for name, machine in all_machines().items()
        for source, target in machine.guarded_transitions
    ]
    assert found, "no guarded transition exists to exercise"
    return sorted(found)


GUARDED = _all_guarded()


class TestGuards:
    def test_every_guard_has_a_satisfying_context_defined(self) -> None:
        """A guard with no known satisfying context could not be positively tested."""
        for name, source, target in GUARDED:
            assert _context(name, source, target), (
                f"{name}: {source}->{target} is guarded but no satisfying "
                "context is defined, so the positive case would be untested"
            )

    @pytest.mark.parametrize("name,source,target", GUARDED)
    def test_guard_rejects_an_empty_context(
        self, name: str, source: str, target: str
    ) -> None:
        machine = all_machines()[name]
        with pytest.raises(GuardRejected):
            machine.evaluate(source, target, {})

    @pytest.mark.parametrize("name,source,target", GUARDED)
    def test_guard_accepts_a_satisfying_context(
        self, name: str, source: str, target: str
    ) -> None:
        machine = all_machines()[name]
        outcome = machine.evaluate(source, target, _context(name, source, target))
        assert outcome.guard_applied is True

    def test_core_candidate_promotion_additionally_requires_gate_2(self) -> None:
        machine = all_machines()["Candidate"]
        core = {"evidence_set": ("EV-0001",), "is_core_candidate": True}
        with pytest.raises(GuardRejected):
            machine.evaluate("ACCEPTED", "PROMOTED", core)
        machine.evaluate("ACCEPTED", "PROMOTED", core | {"human_gate_2_recorded": True})

    def test_workflow_approval_cannot_be_self_declared(self) -> None:
        machine = all_machines()["WorkflowExecution"]
        for context in ({"human_approval_recorded": False}, {"agent_approved": True}):
            with pytest.raises(GuardRejected):
                machine.evaluate("WAITING_APPROVAL", "RUNNING", context)

    def test_rollback_is_refused_to_any_invoker_but_recovery(self) -> None:
        machine = all_machines()["CoreUpgrade"]
        for invoker in ("lifecycle.evolution", "ai_agent", "lifecycle.release"):
            with pytest.raises(GuardRejected):
                machine.evaluate("PROMOTED", "ROLLED_BACK", {"invoker": invoker})

    def test_plugin_permission_vocabulary_absence_fails_closed(self) -> None:
        machine = all_machines()["PluginLifecycle"]
        with pytest.raises(GuardRejected):
            machine.evaluate(
                "PERMISSIONS_DECLARED",
                "APPROVED",
                {"canonical_operation_classes": (), "declared_permissions": ()},
            )

    def test_plugin_unmappable_permission_blocks(self) -> None:
        machine = all_machines()["PluginLifecycle"]
        with pytest.raises(GuardRejected):
            machine.evaluate(
                "PERMISSIONS_DECLARED",
                "APPROVED",
                {
                    "canonical_operation_classes": _operation_classes(),
                    "declared_permissions": ("INVENT_A_PERMISSION",),
                },
            )


class TestMalformedAndUnknownInput:
    @pytest.mark.parametrize("name", NAMES)
    def test_unknown_source_state(self, name: str) -> None:
        machine = all_machines()[name]
        with pytest.raises(UnknownState):
            machine.evaluate("NO_SUCH_STATE", machine.definition.states[0])

    @pytest.mark.parametrize("name", NAMES)
    def test_unknown_target_state(self, name: str) -> None:
        machine = all_machines()[name]
        with pytest.raises(UnknownState):
            machine.evaluate(machine.definition.states[0], "NO_SUCH_STATE")

    @pytest.mark.parametrize("name", NAMES)
    @pytest.mark.parametrize("malformed", ["", "   ", None, 7, ["ACTIVE"]])
    def test_malformed_state_input(self, name: str, malformed: object) -> None:
        machine = all_machines()[name]
        with pytest.raises(UnknownState):
            machine.evaluate(malformed, machine.definition.states[0])  # type: ignore[arg-type]

    @pytest.mark.parametrize("name", NAMES)
    def test_start_rejects_an_unknown_initial_state(self, name: str) -> None:
        with pytest.raises(UnknownState):
            all_machines()[name].start("NO_SUCH_STATE")


class TestNoMutationBypass:
    @pytest.mark.parametrize("name", NAMES)
    def test_public_state_has_no_setter(self, name: str) -> None:
        machine = all_machines()[name]
        instance = machine.start(machine.definition.states[0])
        with pytest.raises((AttributeError, StateMutationBypass)):
            instance.state = machine.definition.states[-1]  # type: ignore[misc]

    @pytest.mark.parametrize("name", NAMES)
    def test_private_attribute_assignment_is_refused(self, name: str) -> None:
        machine = all_machines()[name]
        instance = machine.start(machine.definition.states[0])
        with pytest.raises(StateMutationBypass):
            instance._state = machine.definition.states[-1]

    @pytest.mark.parametrize("name", NAMES)
    def test_state_survives_a_refused_transition(self, name: str) -> None:
        machine = all_machines()[name]
        start = machine.definition.states[0]
        instance = machine.start(start)
        with pytest.raises(StateMachineError):
            instance.apply("NO_SUCH_STATE")
        assert instance.state == start


class TestDeterminism:
    @pytest.mark.parametrize("name", NAMES)
    def test_repeated_evaluation_is_identical(self, name: str) -> None:
        machine = all_machines()[name]
        for source, target in machine.definition.transitions:
            context = _context(name, source, target)
            results = [machine.evaluate(source, target, context) for _ in range(5)]
            assert len({r.model_dump_json() for r in results}) == 1

    @pytest.mark.parametrize("name", NAMES)
    def test_rejection_is_repeatable(self, name: str) -> None:
        machine = all_machines()[name]
        for _ in range(3):
            with pytest.raises(UnknownState):
                machine.evaluate("NO_SUCH_STATE", machine.definition.states[0])
