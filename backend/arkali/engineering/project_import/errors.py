"""Typed C-29 import/rescue contract failures owned by ``engineering.import``.

Imports `ContractViolation` from `contract_violation_base`, not `error_base`:
`error_base.py` sits at fan-in 13 of 15, and `contract_violation_base.py` is
the absorber module ADR-0008 created for exactly this situation — every later
context needing only the contract-violation base imports it directly, the
same choice `engineering.knowledge`'s and `engineering.repair`'s own
`errors.py` recorded first.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class UnverifiedStaticInspectionError(ContractViolation):
    """A tier was assigned, or execution was approved, without a completed,
    genuinely-executed static inspection report (ARK-REQ-0115, ARK-REQ-0161).
    """

    code = "ARK-ERR-0143"


class TierReassignmentError(ContractViolation):
    """An attempt was made to assign a TRUST tier through a path other than
    the fixed, non-parameterised authority — the structural enforcement of
    "cannot be reassigned by an implementing actor" (ARK-REQ-0161, §12)."""

    code = "ARK-ERR-0144"


class RescueBoundaryViolationError(ContractViolation):
    """A rescue operation attempted to write to the preserved original
    source, escape the allocated working copy, or proceed while the tier's
    required isolation properties are unsatisfiable (ARK-REQ-0348 conditions
    3, 6, 7)."""

    code = "ARK-ERR-0145"


class UnknownRescueMode(ContractViolation):
    """A caller named a rescue mode the canonical document does not declare
    (ARK-REQ-0162)."""

    code = "ARK-ERR-0146"
