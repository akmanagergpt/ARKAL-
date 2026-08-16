"""Typed C-37-consuming factory failures owned by ``engineering.factory``.

Imports `ContractViolation` from `contract_violation_base`, matching the
`control.specification`/`engineering.repair` precedent: `error_base.py` is
fan-in constrained and `contract_violation_base.py` exists to absorb a
further importer needing only the contract-violation base.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class RoutingDecisionIncomplete(ContractViolation):
    """`select_execution_tier` produced no verdict; TIER_ORDER was mutated."""

    code = "ARK-ERR-0114"


class UnresolvedBlueprintError(ContractViolation):
    """Generation was requested from a blueprint with unresolved questions."""

    code = "ARK-ERR-0115"
