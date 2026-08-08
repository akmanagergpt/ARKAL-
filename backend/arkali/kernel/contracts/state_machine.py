"""Deterministic state-machine primitive (ARK-REQ-0043, ARK-REQ-0044).

Owner: kernel.contracts.

WHY THIS LIVES IN THE KERNEL. The twelve canonical machines are owned by ten
different bounded contexts, three of them in the `control` layer. The authority
map sets `allow_same_layer: false`, so a shared primitive placed in
`control.architecture` could not be imported by `control.registry.project` or
`control.registry.provider`. Only layer rank 0 is reachable from every
authority, so the *primitive* is a kernel contract while every *machine* stays
owned by the context the authority map names.

STRUCTURAL IMPOSSIBILITY (ARK-REQ-0044). An illegal transition is not detected
and reported - it cannot be expressed. There is no public setter for machine
state anywhere in this module: `StateMachineInstance.state` is a read-only
property, and `__setattr__` rejects every external write. The only path from one
state to another is `apply`, which consults the declared relation first and
raises on rejection. Nothing here converts a rejection into a default, a
coercion or a silent no-op.

NO SHADOW MODEL. This module contains no machine, no state and no transition. It
is mechanism only; the twelve definitions live with their authorities and are
reconciled against docs/canonical/STATE_MACHINES.md by
control.architecture.state_machine_spec.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Mapping
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator

from arkali.kernel.contracts.state_machine_errors import (
    ForbiddenTransition,
    GuardRejected,
    IllegalTransition,
    StateMachineDefinitionError,
    StateMutationBypass,
    TerminalStateEscape,
    UnknownState,
)

#: Data a guard may read. Guards are pure predicates over recorded facts.
GuardContext = Mapping[str, Any]
Guard = Callable[[GuardContext], bool]


class TransitionDecision(str, enum.Enum):
    """Deterministic outcome vocabulary. There is no third answer."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class TransitionOutcome(BaseModel):
    """Immutable record of one evaluated transition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: str
    source: str
    target: str
    decision: TransitionDecision
    guard_applied: bool = False


class StateMachineDefinition(BaseModel):
    """One canonical machine: states, relation, forbidden set, terminals.

    Construction is validating. A definition that contradicts itself raises
    rather than being repaired, so a contradictory machine cannot exist at all.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine: str
    authority: str
    states: tuple[str, ...]
    transitions: tuple[tuple[str, str], ...]
    forbidden: tuple[tuple[str, str], ...] = ()
    terminal: tuple[str, ...] = ()
    authoritative_source: str

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if not self.states:
            raise StateMachineDefinitionError(
                f"{self.machine}: declares no states", source=self.authoritative_source
            )
        if len(set(self.states)) != len(self.states):
            raise StateMachineDefinitionError(
                f"{self.machine}: duplicate state identifier",
                source=self.authoritative_source,
            )
        known = set(self.states)
        for label, pairs in (("transition", self.transitions),
                             ("forbidden", self.forbidden)):
            for src, dst in pairs:
                if src not in known or dst not in known:
                    raise StateMachineDefinitionError(
                        f"{self.machine}: {label} {src}->{dst} names an undeclared state",
                        source=self.authoritative_source,
                    )
        unknown_terminal = sorted(set(self.terminal) - known)
        if unknown_terminal:
            raise StateMachineDefinitionError(
                f"{self.machine}: undeclared terminal states {unknown_terminal}",
                source=self.authoritative_source,
            )
        contradiction = sorted(set(self.forbidden) & set(self.transitions))
        if contradiction:
            raise StateMachineDefinitionError(
                f"{self.machine}: {contradiction} is both legal and forbidden",
                source=self.authoritative_source,
            )
        escaping = sorted(
            f"{src}->{dst}" for src, dst in self.transitions if src in self.terminal
        )
        if escaping:
            raise StateMachineDefinitionError(
                f"{self.machine}: terminal state has outgoing transitions {escaping}",
                source=self.authoritative_source,
            )
        return self

    @property
    def transition_set(self) -> frozenset[tuple[str, str]]:
        return frozenset(self.transitions)

    @property
    def forbidden_set(self) -> frozenset[tuple[str, str]]:
        return frozenset(self.forbidden)


class StateMachine:
    """Stateless evaluator. The sole authority on whether a transition is legal."""

    def __init__(
        self,
        definition: StateMachineDefinition,
        guards: Mapping[tuple[str, str], Guard] | None = None,
    ) -> None:
        self.definition = definition
        declared = definition.transition_set
        unknown = sorted(pair for pair in (guards or {}) if pair not in declared)
        if unknown:
            raise StateMachineDefinitionError(
                f"{definition.machine}: guard declared for non-existent transition "
                f"{unknown}",
                source=definition.authoritative_source,
            )
        self._guards: dict[tuple[str, str], Guard] = dict(guards or {})

    @property
    def machine(self) -> str:
        return self.definition.machine

    @property
    def guarded_transitions(self) -> tuple[tuple[str, str], ...]:
        """Transitions carrying a guard. Lets a test prove every guard is exercised."""
        return tuple(sorted(self._guards))

    def is_legal(self, source: str, target: str) -> bool:
        """Pure relation membership. Guards are not consulted."""
        return (source, target) in self.definition.transition_set

    def evaluate(
        self, source: str, target: str, context: GuardContext | None = None
    ) -> TransitionOutcome:
        """Decide one transition. Raises on every rejection; never returns REJECTED.

        Order is deliberate: malformed input, then unknown states, then terminal
        escape, then explicit prohibition, then relation membership, then guard.
        A caller can therefore assert the precise reason.
        """
        self._require_known(source, "source")
        self._require_known(target, "target")
        definition = self.definition
        if source in definition.terminal:
            raise TerminalStateEscape(
                f"{definition.machine}: {source} is terminal; {source}->{target} "
                "cannot occur",
                source=definition.authoritative_source,
            )
        if (source, target) in definition.forbidden_set:
            raise ForbiddenTransition(
                f"{definition.machine}: {source}->{target} is explicitly forbidden",
                source=definition.authoritative_source,
            )
        if (source, target) not in definition.transition_set:
            raise IllegalTransition(
                f"{definition.machine}: {source}->{target} is not a declared transition",
                source=definition.authoritative_source,
            )
        guard = self._guards.get((source, target))
        if guard is not None and not guard(dict(context or {})):
            raise GuardRejected(
                f"{definition.machine}: guard rejected {source}->{target}",
                source=definition.authoritative_source,
            )
        return TransitionOutcome(
            machine=definition.machine,
            source=source,
            target=target,
            decision=TransitionDecision.ACCEPTED,
            guard_applied=guard is not None,
        )

    def _require_known(self, value: str, role: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise UnknownState(
                f"{self.definition.machine}: malformed {role} state {value!r}",
                source=self.definition.authoritative_source,
            )
        if value not in set(self.definition.states):
            raise UnknownState(
                f"{self.definition.machine}: unknown {role} state {value!r}",
                source=self.definition.authoritative_source,
            )

    def start(self, initial: str) -> StateMachineInstance:
        self._require_known(initial, "initial")
        return StateMachineInstance(self, initial)


class StateMachineInstance:
    """A machine bound to a current state.

    There is no setter. `state` is read-only and `__setattr__` refuses every
    external write, including to the private attribute, so the only way to reach
    a new state is `apply`, which validates first.
    """

    __slots__ = ("_machine", "_state", "_sealed")

    #: Annotated for the type checker; assignment goes through object.__setattr__
    #: because this class refuses ordinary attribute writes.
    _machine: StateMachine
    _state: str
    _sealed: bool

    def __init__(self, machine: StateMachine, initial: str) -> None:
        object.__setattr__(self, "_machine", machine)
        object.__setattr__(self, "_state", initial)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: object) -> None:
        raise StateMutationBypass(
            f"{self._machine.machine}: direct assignment to {name!r} is refused; "
            "state changes only through apply()",
            source=self._machine.definition.authoritative_source,
        )

    def __delattr__(self, name: str) -> None:
        raise StateMutationBypass(
            f"{self._machine.machine}: deletion of {name!r} is refused",
            source=self._machine.definition.authoritative_source,
        )

    @property
    def state(self) -> str:
        return self._state

    @property
    def machine(self) -> StateMachine:
        return self._machine

    @property
    def is_terminal(self) -> bool:
        return self._state in self._machine.definition.terminal

    def apply(
        self, target: str, context: GuardContext | None = None
    ) -> TransitionOutcome:
        """Validate then move. Raises without mutating if the transition is rejected."""
        outcome = self._machine.evaluate(self._state, target, context)
        object.__setattr__(self, "_state", target)
        return outcome
