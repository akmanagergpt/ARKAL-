"""Typed C-30 plugin-manifest contract failures owned by `engineering.plugin`.

Imports `ContractViolation` from `contract_violation_base`, not `error_base`
(fan-in 14 of 15) - the ADR-0008 absorber module every later context needing
only the contract-violation base already imports, the same choice
`engineering.import`'s own `errors.py` recorded first.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class PluginManifestVersionError(ContractViolation):
    """A plugin manifest declared a version string that is not valid semver
    2.0.0 (ARK-REQ-0164; `CONTRACT_INVENTORY.md` row C-30: versioning is
    semver)."""

    code = "ARK-ERR-0147"
