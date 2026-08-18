"""Composed `CoreUpgrade` promotion: a real HUMAN_GATE_2 grant, then a real
Stable promotion - the last step of "self-evolution pipeline followed"
(ARK-REQ-0134).

`lifecycle.evolution -> lifecycle.release` is a declared sibling edge
("promotion handoff" in `AUTHORITY_MAP.yaml`), so this module imports
`StableCandidatePath`/`StableRevisionPointer` directly - unlike Package 3's
`lifecycle.recovery` edge and Package 4's `acceptance.engine` edge, neither
of which is declared, this one is.

TWO INDEPENDENT REFUSALS, NEITHER BYPASSABLE BY THE OTHER. The `CoreUpgrade`
transition itself refuses without a real scoped `HUMAN_GATE_2` grant
(`GuardRejected`, ARK-REQ-0138); `StableRevisionPointer.promote` - reused
completely unmodified, the only `promote()` in this codebase - refuses
without a genuine five-stage promotion receipt. This module performs no
Stable mutation of its own; it only sequences two already-independent
authorities' own refusals.
"""

from __future__ import annotations

from typing import Final

from arkali.lifecycle.evolution.core_upgrade_orchestrator import (
    HumanGate2Source,
    authorize_promotion,
)
from arkali.lifecycle.evolution.core_upgrade_state_machine import StateMachineInstance
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import (
    StableRevisionPointer,
    StableRevisionRecord,
)

PROMOTED_STATE: Final[str] = "PROMOTED"


class CorePromotionRequest:
    """Every fact one promotion needs, bundled by the caller - the same
    reason `MigrationSafetyRequest` bundles facts for the Apply step
    (`ARCHITECTURE.md` section 8's parameter budget)."""

    def __init__(
        self,
        *,
        instance: StateMachineInstance,
        gates: HumanGate2Source,
        path: StableCandidatePath,
        pointer: StableRevisionPointer,
        receipt: StageReceipt,
        revision_id: str,
        candidate_manifest_ref: str,
    ) -> None:
        self.instance = instance
        self.gates = gates
        self.path = path
        self.pointer = pointer
        self.receipt = receipt
        self.revision_id = revision_id
        self.candidate_manifest_ref = candidate_manifest_ref


def promote_core_upgrade(request: CorePromotionRequest) -> StableRevisionRecord:
    """The only production path from `AWAITING_GATE_2` to a real Stable
    promotion. Raises (never mutates anything) if either refusal fires.

    Order matters: the receipt is validated into its final promotion stage
    *before* the `CoreUpgrade` instance transitions, so a stale or
    incomplete receipt cannot leave the instance claiming `PROMOTED` while
    Stable was never actually written - the state machine would otherwise
    have no way to know the pointer write that follows can still fail.
    """
    promotion_receipt = request.path.promotion_receipt(request.receipt)
    request.instance.apply(
        PROMOTED_STATE,
        authorize_promotion(
            request.gates, candidate_manifest_ref=request.candidate_manifest_ref,
            target_revision_id=request.revision_id,
        ),
    )
    return request.pointer.promote(
        promotion_receipt, revision_id=request.revision_id,
        candidate_id=promotion_receipt.candidate_id,
    )
