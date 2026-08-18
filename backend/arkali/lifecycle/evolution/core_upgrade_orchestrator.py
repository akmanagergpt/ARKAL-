"""Begins a `CoreUpgrade` instance only after a real restorable snapshot
exists (ARK-REQ-0137).

`lifecycle.evolution` has no declared sibling edge to `lifecycle.recovery` in
`AUTHORITY_MAP.yaml` (only the reverse edge - `lifecycle.recovery ->
lifecycle.release` - and `lifecycle.evolution -> lifecycle.release` are
declared). This module reaches `lifecycle.recovery`'s real snapshot proof
through a `Protocol`, the same shape `RecoverySupervisor` already uses to
reach `control.policy`/`evidence.audit`: the composition root constructs the
real adapter over `lifecycle.recovery.core_snapshot.take_core_snapshot`;
nothing here imports that module.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from arkali.lifecycle.evolution import core_upgrade_state_machine as cusm
from arkali.lifecycle.evolution.core_upgrade_state_machine import StateMachineInstance


@runtime_checkable
class RestorableSnapshotProof(Protocol):
    """Structural view of `lifecycle.recovery.core_snapshot.take_core_snapshot`,
    reduced to the one fact this module needs."""

    def take_snapshot(self, *, candidate_id: str) -> str:
        """Take and prove a restorable snapshot; return the snapshotted
        revision id. Raises rather than returning a false success if no
        Stable revision exists or the snapshot does not prove restorable."""
        ...


def _initial_state() -> str:
    """The one declared `CoreUpgrade` state with no incoming transition -
    derived from the machine, never hard-coded (mirrors
    `backup_service._initial_state`)."""
    definition = cusm.build().definition
    return next(
        state for state in definition.states
        if all(target != state for _, target in definition.transitions)
    )


def begin_core_upgrade(
    snapshot: RestorableSnapshotProof, *, candidate_id: str,
) -> tuple[StateMachineInstance, str]:
    """The production entry point for starting a `CoreUpgrade` instance.

    ARK-REQ-0137: a restorable snapshot is taken and proved *before* the
    instance exists at all - `StateMachine.start` carries no guard of its
    own, so this function is what makes "no snapshot, no instance" true.
    """
    revision_id = snapshot.take_snapshot(candidate_id=candidate_id)
    instance = cusm.build().start(_initial_state())
    return instance, revision_id
