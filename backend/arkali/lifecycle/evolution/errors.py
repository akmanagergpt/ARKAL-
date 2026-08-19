"""Typed C-33 evolution-campaign contract failures owned by `lifecycle.evolution`.

Imports `ContractViolation` from `contract_violation_base`, matching
`engineering.repair.errors` - the same recurring shape: a context needing only
the contract-violation base, not the full `error_base` taxonomy.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class CampaignBudgetExceededError(ContractViolation):
    """A campaign attempt would exceed one or more of the six declared
    budgets (ARK-REQ-0139/0141)."""

    code = "ARK-ERR-0153"


class CampaignStillRunningError(ContractViolation):
    """A terminal state was requested for a campaign that has neither
    promoted a candidate nor exhausted its budget or no-progress threshold
    (ARK-REQ-0140) - the campaign is still eligible to continue."""

    code = "ARK-ERR-0154"


class ChildProductNotSdkEligibleError(ContractViolation):
    """A `STANDARD`/`AI_ASSISTED` child product cannot declare a Product
    Evolution SDK campaign - MS reserves the SDK for
    `AI_NATIVE_SELF_EVOLVING` products only (ARK-REQ-0131)."""

    code = "ARK-ERR-0157"


class UnknownVersionReferenceError(ContractViolation):
    """A rollback or lookup named a `version_ref` this lineage never
    recorded (ARK-REQ-0132) - a caller's claim that some content was "an
    earlier version" is never trusted without the lineage's own history
    proving it."""

    code = "ARK-ERR-0158"


class VersionLineageOrderError(ContractViolation):
    """A version was appended out of sequence or with a parent reference
    that does not honestly continue this lineage (ARK-REQ-0358) - a gap or
    a rewritten parent is refused, never silently accepted."""

    code = "ARK-ERR-0159"


class ChildProductPromotionNotAuthorizedError(ContractViolation):
    """A child-product promotion was attempted without a recorded, scoped
    `HUMAN_GATE_3` grant naming this exact (product, candidate, current
    version) triple (ADR-0010, ARK-REQ-0132/0358). Refused before anything
    is mutated - never a partial promotion."""

    code = "ARK-ERR-0160"


class ChildProductAcceptanceRequiredError(ContractViolation):
    """A child-product promotion was attempted without a passing
    acceptance record naming the exact candidate being promoted - real
    executed evidence, never a caller-asserted boolean (ARK-REQ-0132)."""

    code = "ARK-ERR-0161"


class ChildProductCandidateInvalidError(ContractViolation):
    """A promotion candidate reference is not a genuine content address,
    or the product is not SDK-eligible - refused before any grant is even
    looked up (ARK-REQ-0131/0132)."""

    code = "ARK-ERR-0162"


class ChildProductRollbackRequestInvalidError(ContractViolation):
    """A rollback request named an identity that does not match the
    lineage it was given, or carried no real reason - refused before
    `ChildProductVersionLineage.restore_to` is ever reached (ARK-REQ-0132,
    ARK-REQ-0358)."""

    code = "ARK-ERR-0163"
