"""C-36 child-product rollback: returns a child product's current version to
an already-recorded, already-approved one - never new content, never a
different product, never ARKALI's own Stable Core (ARK-REQ-0132,
ARK-REQ-0358).

Owner: `lifecycle.evolution`.

A SEPARATE AUTHORITY FROM PROMOTION (ADR-0009's own precedent, reapplied).
"If one component both promotes and rolls back, a failed promotion could
approve its own recovery" - the reason `lifecycle.release` (promote) and
`lifecycle.recovery` (rollback) are two authorities, one direction of
trust. This module is the child-product-scoped mirror of that split:
`child_product_promotion.py` never calls `restore_to`
(`test_child_product_no_direct_promotion.py` already proves this by AST),
and this module never calls `.append` with `is_rollback=False` - it can
only ever reach the rollback path.

WHY ROLLBACK NEEDS NO FRESH `HUMAN_GATE_3`, AND WHAT ENFORCES THAT HONESTLY.
Promotion introduces genuinely new, unreviewed content, which is exactly
why ADR-0010 makes it fail-closed on human approval. Rollback introduces
nothing new: `ChildProductVersionLineage.restore_to` only ever restores a
`content_ref` that is already present in this lineage's own durable
history (`find` refuses any target that is not), which is content a
`HUMAN_GATE_3` grant already approved once, at the promotion that first
introduced it. This is the identical reasoning `RecoverySupervisor`
(Phase 22B) already established for ARKALI's own Stable Core: its rollback
requires no fresh human approval either, only proof the target was
"previously verified" - here that proof is the lineage's own history,
not a caller's claim, structurally, not by convention.

NOT `RecoverySupervisor`, AND NO NEW PDP/PEP ENTRY. This module imports
nothing from `lifecycle.release` or `lifecycle.recovery` - it never
reaches ARKALI's own Stable Core pointer or the Recovery Supervisor's
`ROLLBACK_STABLE` grant, and introduces no second rollback mechanism for
ARKALI's own core. A child product's rollback is scoped entirely to its
own `ChildProductVersionLineage`, passed in by the caller; there is no
global registry here through which one product's rollback could reach a
different product's lineage.
"""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.lifecycle.evolution.child_product_identity import ChildProductIdentity
from arkali.lifecycle.evolution.child_product_version import ChildProductVersionLineage
from arkali.lifecycle.evolution.content_identity import address_of
from arkali.lifecycle.evolution.errors import ChildProductRollbackRequestInvalidError

Declared = Annotated[str, Field(min_length=1)]
#: The one production module allowed to call `restore_to` other than
#: `child_product_version.py`'s own internal use from within that method.
_ROLLBACK_CAMPAIGN_PREFIX: Final[str] = "rollback"


class ChildProductRollbackReceipt(BaseModel):
    """C-36 evidence: what one rollback proved. Built only from what
    actually happened - mirrors `RecoverySupervisor.RollbackRecord`'s own
    "built from what actually happened" discipline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    product_ref: Declared
    from_version_ref: str | None
    to_version_ref: Declared
    restored_content_ref: Declared
    reason: Declared

    def rendering(self) -> bytes:
        return self.model_dump_json(by_alias=True).encode("utf-8")

    @property
    def receipt_ref(self) -> str:
        return address_of(self.rendering())


def rollback_child_product(
    lineage: ChildProductVersionLineage,
    identity: ChildProductIdentity,
    *,
    target_version_ref: str,
    reason: str,
) -> tuple[ChildProductVersionLineage, ChildProductRollbackReceipt]:
    """The only production path that rolls a child product's current
    version back to an already-recorded one. Raises before anything is
    returned if `identity`/`lineage` do not name the same product (a
    caller cannot roll back product B by passing product A's identity
    alongside product B's lineage), if no real reason is given, or if the
    target is not genuinely part of this lineage's own history
    (`ChildProductVersionLineage.find`'s existing refusal). Produces no
    new content: the restored content is always copied from the target's
    own already-recorded entry.
    """
    if lineage.product_ref != identity.product_ref:
        raise ChildProductRollbackRequestInvalidError(
            f"identity {identity.product_id!r} (product_ref="
            f"{identity.product_ref!r}) does not match the lineage it was "
            f"given (product_ref={lineage.product_ref!r})"
        )
    if not reason.strip():
        raise ChildProductRollbackRequestInvalidError(
            "a rollback must state a real reason"
        )
    from_ref = lineage.current.version_ref if lineage.current else None
    campaign_id = f"{_ROLLBACK_CAMPAIGN_PREFIX}:{identity.product_ref}:{from_ref or 'GENESIS'}"
    rolled_back = lineage.restore_to(target_version_ref, campaign_id=campaign_id)
    current = rolled_back.current
    assert current is not None  # restore_to always appends
    receipt = ChildProductRollbackReceipt(
        product_ref=identity.product_ref,
        from_version_ref=from_ref,
        to_version_ref=current.version_ref,
        restored_content_ref=current.content_ref,
        reason=reason,
    )
    return rolled_back, receipt
