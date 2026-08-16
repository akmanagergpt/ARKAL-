"""Typed C-28 knowledge-contract failures owned by ``engineering.knowledge``.

Imports `ContractViolation` from `contract_violation_base`, not `error_base`:
`error_base.py` sits at fan-in 13 of 15 (Phase 17's own last redirect), and
`contract_violation_base.py` is the absorber module ADR-0008 created for
exactly this situation — every later context needing only the contract-
violation base imports it directly, the same choice `engineering.repair`'s
`errors.py` recorded first.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class UnbackedKnowledgeClaimError(ContractViolation):
    """A knowledge claim or verified-outcome record was attempted with an
    evidence reference that is not a real, canonically-addressed pointer
    (ARK-REQ-0126, ARK-REQ-0394)."""

    code = "ARK-ERR-0140"


class IllegalValidityTransitionError(ContractViolation):
    """A knowledge record attempted a validity-state transition the derived
    lifecycle in `docs/contracts/knowledge.md` does not permit
    (ARK-REQ-0127)."""

    code = "ARK-ERR-0141"


class IncompleteComponentMetadataError(ContractViolation):
    """A reusable component descriptor is missing a canonically required
    test, security or compatibility declaration (ARK-REQ-0128)."""

    code = "ARK-ERR-0142"
