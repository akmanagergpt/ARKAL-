"""Orchestrates `CoreUpgrade` transitions that need a real fact no kernel
guard can compute alone: a restorable snapshot before entry (ARK-REQ-0137)
and a scoped HUMAN_GATE_2 grant before promotion (ARK-REQ-0138).

`lifecycle.evolution` has no declared sibling edge to `lifecycle.recovery` in
`AUTHORITY_MAP.yaml` (only the reverse edge - `lifecycle.recovery ->
lifecycle.release` - and `lifecycle.evolution -> lifecycle.release` are
declared), and none to `acceptance.engine` either. Both facts are reached
through a `Protocol`, the same shape `RecoverySupervisor` already uses to
reach `control.policy`/`evidence.audit`, and the identical shape
`migration_safety_types.HumanGateSource` already uses to reach this exact
`GovernanceState.operation_grant` mechanism for `HUMAN_GATE_6`. The
composition root constructs the real adapters; nothing here imports
`lifecycle.recovery.core_snapshot` or `acceptance.engine` directly.
"""

from __future__ import annotations

from typing import Final, Protocol, runtime_checkable

from arkali.lifecycle.evolution import core_upgrade_state_machine as cusm
from arkali.lifecycle.evolution.core_upgrade_state_machine import StateMachineInstance

#: The operation class this context presents to a scoped gate lookup. Not a
#: PDP `operation_classes` entry - `StableRevisionPointer.promote()` is
#: gated by `StableCandidatePath`'s five-stage receipt proof, not by the PDP
#: operation-class vocabulary (`WRITE_STABLE_FILE`/`ROLLBACK_STABLE` are the
#: only Stable-mutation entries there). This is this context's own scoping
#: key for the human-gate grant table, parallel to `APPLY_MIGRATION`'s.
CORE_PROMOTION_OPERATION: Final[str] = "CORE_PROMOTION"
GATE_2: Final[str] = "HUMAN_GATE_2"


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


@runtime_checkable
class HumanGate2Source(Protocol):
    """Scoped human-gate lookup, identical shape to `migration_safety_types.
    HumanGateSource`. `acceptance.engine.GovernanceState` satisfies this
    structurally through its own `operation_grant` method - no second
    grant-scoping mechanism is introduced here."""

    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str,
        revision_identity: str,
    ) -> bool: ...


def authorize_promotion(
    gates: HumanGate2Source, *, candidate_manifest_ref: str, target_revision_id: str,
) -> dict[str, object]:
    """ARK-REQ-0138: the guard context for `AWAITING_GATE_2 -> PROMOTED`.

    `human_gate_2_recorded` is populated only from a real scoped
    `HUMAN_GATE_2` grant for this exact candidate and target revision - never
    a caller-asserted boolean. `candidate_manifest_ref` and
    `target_revision_id` are the caller's mechanically derived facts about
    the exact promotion reviewed (a candidate's content-addressed manifest
    identity, the resolved Stable revision), the same discipline
    `migration_safety_steps.py` uses for `APPLY_MIGRATION`'s backup digest
    and target revision - never labels a caller may assert freely.
    """
    recorded = gates.operation_grant(
        GATE_2, CORE_PROMOTION_OPERATION, candidate_manifest_ref, target_revision_id,
    )
    return {"human_gate_2_recorded": recorded}
