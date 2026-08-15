"""Typed C-26 repair-contract failures owned by ``engineering.repair``.

Imports `ContractViolation` from `contract_violation_base`, not `error_base`:
`error_base.py` was already at `max_fan_in_per_module` (15) and this was the
sixteenth context needing only the contract-violation base, which is exactly
what `contract_violation_base.py` exists to absorb.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class InvalidRepairFingerprintError(ContractViolation):
    """A repair attempt cannot be identified canonically."""

    code = "ARK-ERR-0109"


class RepairBudgetExceededError(ContractViolation):
    """A repair attempt would exceed one or more declared dimensions."""

    code = "ARK-ERR-0110"


class RepeatedFailedStrategyError(ContractViolation):
    """The same strategy was already attempted for this failure and cause."""

    code = "ARK-ERR-0111"
