"""Typed refusals owned by `engineering.product_change` (D-030).

Derives from `kernel.contracts.error_root.ArkaliError` directly, never
`kernel.contracts.contract_violation_base.ContractViolation` -- that module
is already at its fan-in ceiling (15 of 15, confirmed at ruling time);
`error_root` has real headroom and is `ArkaliError` itself, the same
`DOMAIN_ERROR_BASE` `surfaces.command.error_mapping` already requires every
mapped domain error to derive from, so nothing about HTTP-refusal mapping
is lost by skipping the intermediate class.
"""

from __future__ import annotations

from arkali.kernel.contracts.error_root import ArkaliError


class ProductChangeError(ArkaliError):
    """Base for every refusal this context raises."""

    code = "ARK-ERR-0160"


class NoBaseRevisionError(ProductChangeError):
    """A project has no revision to base a change on."""

    code = "ARK-ERR-0161"


class RevisionSourceUnavailableError(ProductChangeError):
    """A revision's immutable source cannot be materialized from its own
    recorded provenance -- never fabricated."""

    code = "ARK-ERR-0162"


class InspectionFailedError(ProductChangeError):
    """Real source inspection could not complete."""

    code = "ARK-ERR-0163"


class ModelPlanInvalidError(ProductChangeError):
    """The provider's own response could not be parsed as a real,
    schema-valid `ChangePlan` -- never silently coerced."""

    code = "ARK-ERR-0164"


class ChangesetValidationError(ProductChangeError):
    """A changeset operation names a forbidden path, a missing
    precondition, or a collision with another operation in the same
    changeset -- refused before any write."""

    code = "ARK-ERR-0165"


class VerificationFailedError(ProductChangeError):
    """A real, applied changeset failed real automated verification."""

    code = "ARK-ERR-0166"


class PromotionNotAuthorizedError(ProductChangeError):
    """`MANAGED_PRODUCT_REVISION_PROMOTION` was requested and no real
    scoped grant exists for this exact (project, base revision, proposal)
    triple."""

    code = "ARK-ERR-0167"


class StaleBaseRevisionError(ProductChangeError):
    """The project's canonical current revision moved on since this
    modification's own base was captured -- refused rather than silently
    rebased."""

    code = "ARK-ERR-0168"


class NoActiveModificationError(ProductChangeError):
    """An operation needs a real, currently active modification execution
    and none exists for this project."""

    code = "ARK-ERR-0169"
