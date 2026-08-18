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
