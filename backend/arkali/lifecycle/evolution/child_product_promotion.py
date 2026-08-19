"""C-36 child-product promotion: a real, scoped `HUMAN_GATE_3` grant, then a
real atomic version-lineage advance - the last step of the canonical child
path (working copy -> candidate -> tests/acceptance -> `HUMAN_GATE_3` ->
promotion), never a shortcut around it (ARK-REQ-0132, ARK-REQ-0358, ADR-0010).

Owner: `lifecycle.evolution`.

NOT ARKALI'S OWN STABLE CORE PROMOTION. This module imports nothing from
`lifecycle.release` and calls no `StableRevisionPointer` method - a child
product's promotion mutates only its own `ChildProductVersionLineage`
(`child_product_version.py`), never ARKALI's own Stable Core pointer.
Reusing that pointer for a child product would conflate two distinct
concerns (`ARK-REQ-0358`'s "full core not copied as runtime" reasoning
extends to ARKALI's own bookkeeping, not just the child's deployed
runtime) under one authority; this module is a second, child-scoped
authority for a second, child-scoped subject, not a second *general*
release authority - `lifecycle.evolution` still owns nothing about
ARKALI's own Stable Core.

THE SAME SCOPED-GRANT MECHANISM AS `HUMAN_GATE_2`, REUSED UNMODIFIED.
`_ChildProductGateSource` is the identical shape `core_upgrade_orchestrator.
HumanGate2Source` and `migration_safety_types.HumanGateSource` already use
to reach `acceptance.engine.GovernanceState.operation_grant` - satisfied
structurally by the real `GovernanceState`, no second parser, no second
PDP/PEP, no second authorization table. `PROMOTE_CHILD_PRODUCT` is this
context's own scoping key for the `RUNTIME_OPERATION`-scope grant table,
parallel to `CORE_PROMOTION`'s, not a new PDP `operation_classes` entry.

ADR-0010: FAIL CLOSED, NO EXEMPTION PATH. Every promotion requires the
grant; there is no parameter, flag, or code path that treats any candidate
as exempt from `HUMAN_GATE_3`.

IDENTITY IS DERIVED, NEVER CALLER-ASSERTED (ARK-REQ-0132's anti-replay
half). `child_promotion_target_identity`/`child_promotion_revision_identity`
are content-addressed over the real product identity, the real candidate
content, and the real current version - never a free string a caller
could invent. A grant recorded for one product/candidate/current-version
triple cannot satisfy a lookup for a different product, a different
candidate, a different target version, or the *same* candidate once the
current version has moved on (the exact confused-deputy/replay/stale-hash
shape `test_core_promotion_gate_scope.py` already proved for
`HUMAN_GATE_2`, proved again here for `HUMAN_GATE_3`).

ORDER MATTERS, MIRRORING `core_promotion.promote_core_upgrade` EXACTLY.
Candidate validity, then acceptance evidence, then the grant, are all
checked - and can all raise - before `lineage.append` is ever called.
`append` itself is a pure, immutable operation (`child_product_version.
ChildProductVersionLineage`) that returns a *new* lineage rather than
mutating the caller's; a refusal at any earlier step therefore leaves the
existing lineage byte-identical, never a half-promoted or orphaned state.

ONLY THIS MODULE MAY ADVANCE A LINEAGE WITH NEW CONTENT. Mirrors Phase 23's
own `core_promotion.py` AST proof: `test_child_product_no_direct_promotion.
py` proves no `lifecycle.evolution` module but this one and
`child_product_version.py` itself (whose `rollback_to` legitimately calls
its own `append`) ever calls `ChildProductVersionLineage.append`.
"""

from __future__ import annotations

from typing import Final, Protocol, runtime_checkable

from arkali.lifecycle.evolution.child_product_identity import ChildProductIdentity
from arkali.lifecycle.evolution.child_product_version import (
    ChildProductVersion,
    ChildProductVersionLineage,
)
from arkali.lifecycle.evolution.content_identity import address_of, is_address
from arkali.lifecycle.evolution.errors import (
    ChildProductAcceptanceRequiredError,
    ChildProductCandidateInvalidError,
    ChildProductPromotionNotAuthorizedError,
)

#: This context's own scoping key for the `RUNTIME_OPERATION`-scope grant
#: table - parallel to `core_upgrade_orchestrator.CORE_PROMOTION_OPERATION`,
#: not a new PDP `operation_classes` entry.
PROMOTE_CHILD_PRODUCT_OPERATION: Final[str] = "PROMOTE_CHILD_PRODUCT"
GATE_3: Final[str] = "HUMAN_GATE_3"
#: The one declared value a genesis (first) version's "current" reference
#: takes before any version exists - never `None` reaching the content
#: address, which would be indistinguishable from a real digest's absence.
_GENESIS_MARKER: Final[str] = "GENESIS"


@runtime_checkable
class _ChildProductGateSource(Protocol):
    """Scoped human-gate lookup, identical shape to `core_upgrade_
    orchestrator.HumanGate2Source` and `migration_safety_types.
    HumanGateSource`. `acceptance.engine.GovernanceState` satisfies this
    structurally through its own `operation_grant` method - no second
    grant-scoping mechanism is introduced here."""

    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str,
        revision_identity: str,
    ) -> bool: ...


class ChildProductAcceptanceRecord:
    """Real evidence that a specific candidate was verified before
    promotion - never a boolean a caller could assert for free (the same
    "evidence is execution, not a boolean" discipline
    `acceptance.verification_profile` already established). Bound to the
    exact `candidate_ref` it verifies; a record for one candidate cannot
    authorize promoting a different one."""

    __slots__ = ("candidate_ref", "command", "exit_code")

    def __init__(self, *, candidate_ref: str, command: str, exit_code: int) -> None:
        if not is_address(candidate_ref):
            raise ChildProductCandidateInvalidError(
                f"acceptance record candidate_ref {candidate_ref!r} is not a "
                "canonical content address"
            )
        if not command.strip():
            raise ChildProductCandidateInvalidError(
                "acceptance record must name the real command that ran"
            )
        self.candidate_ref = candidate_ref
        self.command = command
        self.exit_code = exit_code

    @property
    def passed(self) -> bool:
        return self.exit_code == 0


def child_promotion_target_identity(
    identity: ChildProductIdentity, candidate_ref: str,
) -> str:
    """Content-addressed identity of (product, candidate) - the exact
    subject a `HUMAN_GATE_3` grant must name to promote this candidate for
    this product. A different product or a different candidate yields a
    wholly different identity; nothing here is a caller-chosen label."""
    payload = f"{identity.product_ref}:{candidate_ref}".encode()
    return address_of(payload)


def child_promotion_revision_identity(
    current_version_ref: str | None, candidate_ref: str,
) -> str:
    """Content-addressed identity of the exact promotion transition - which
    version is current right now, becoming which candidate. A grant for one
    (current, candidate) pair does not cover the same candidate once a
    different promotion has already moved the current version on (the
    stale-hash/replay refusal), nor a different candidate for the same
    current version."""
    payload = f"{current_version_ref or _GENESIS_MARKER}:{candidate_ref}".encode()
    return address_of(payload)


def authorize_child_product_promotion(
    gates: _ChildProductGateSource,
    identity: ChildProductIdentity,
    lineage: ChildProductVersionLineage,
    *,
    candidate_ref: str,
) -> dict[str, object]:
    """ARK-REQ-0132: the guard context for a child-product promotion.
    `human_gate_3_recorded` is populated only from a real scoped
    `HUMAN_GATE_3` grant for this exact candidate and current version -
    never a caller-asserted boolean."""
    current_ref = lineage.current.version_ref if lineage.current else None
    recorded = gates.operation_grant(
        GATE_3,
        PROMOTE_CHILD_PRODUCT_OPERATION,
        child_promotion_target_identity(identity, candidate_ref),
        child_promotion_revision_identity(current_ref, candidate_ref),
    )
    return {"human_gate_3_recorded": recorded}


def promote_child_product(
    gates: _ChildProductGateSource,
    identity: ChildProductIdentity,
    lineage: ChildProductVersionLineage,
    *,
    candidate_ref: str,
    campaign_id: str,
    acceptance: ChildProductAcceptanceRecord,
) -> ChildProductVersionLineage:
    """The only production path from a verified candidate to a new current
    child-product version. Raises (never mutates anything) if the
    candidate is malformed, the acceptance record does not match, the
    product is not SDK-eligible, or no scoped `HUMAN_GATE_3` grant exists -
    every check runs, and can refuse, before `lineage.append` is reached.
    """
    if not is_address(candidate_ref):
        raise ChildProductCandidateInvalidError(
            f"candidate_ref {candidate_ref!r} is not a canonical content address"
        )
    if not identity.uses_evolution_sdk:
        raise ChildProductCandidateInvalidError(
            f"child product {identity.product_id!r} is mode "
            f"{identity.mode.value!r}; only AI_NATIVE_SELF_EVOLVING products "
            "may be promoted through the Product Evolution SDK"
        )
    if acceptance.candidate_ref != candidate_ref:
        raise ChildProductAcceptanceRequiredError(
            f"acceptance record names candidate {acceptance.candidate_ref!r}, "
            f"not the candidate being promoted {candidate_ref!r}"
        )
    if not acceptance.passed:
        raise ChildProductAcceptanceRequiredError(
            f"candidate {candidate_ref!r} acceptance ({acceptance.command!r}) "
            f"exited {acceptance.exit_code}, not 0"
        )
    context = authorize_child_product_promotion(
        gates, identity, lineage, candidate_ref=candidate_ref,
    )
    if not context["human_gate_3_recorded"]:
        raise ChildProductPromotionNotAuthorizedError(
            f"HUMAN_GATE_3 required and not recorded for product "
            f"{identity.product_id!r} candidate {candidate_ref!r}"
        )
    current_ref = lineage.current.version_ref if lineage.current else None
    new_version = ChildProductVersion(
        sequence=len(lineage.versions) + 1,
        content_ref=candidate_ref,
        campaign_id=campaign_id,
        parent_ref=current_ref,
        is_rollback=False,
    )
    return lineage.append(new_version)
