"""C-01 canonical error taxonomy.

Owner: kernel.contracts. Every governance failure raised by ARKALI derives from
`ArkaliError` and carries a stable machine-readable code, so failures can be
asserted against rather than matched by message text.

Rule: no error type in this taxonomy may be caught and converted into a PASS.

THE ABSTRACT BASE LAYER MOVED TO `error_base` (Phase 8 Package 1). `ArkaliError`,
`ContractViolation`, `GovernanceStateError` and `AuthoritativeSourceError` are
defined there and re-exported here, so every existing importer is unchanged. The
reason is the same one recorded at the foot of this module: this is the taxonomy
every context must reach, so it accumulates inbound edges until it hits
`max_fan_in_per_module`, and ADR-0008 answers a budget with decomposition. A
context declaring its own error types now imports `error_base` and adds no edge
here.
"""

from __future__ import annotations

from arkali.kernel.contracts.error_base import (
    ArkaliError,
    AuthoritativeSourceError,
    ContractViolation,
    GovernanceStateError,
)

__all__ = [
    "ArkaliError",
    "ArchitectureBudgetError",
    "AuthoritativeSourceError",
    "AuthorityConflictError",
    "ContractViolation",
    "DependencyDirectionError",
    "GovernanceStateError",
    "HumanGateRequired",
    "PhaseProgressionDenied",
    "ProtectedCoreViolation",
]


class AuthorityConflictError(GovernanceStateError):
    """A concern resolves to more than one canonical owner."""

    code = "ARK-ERR-0004"


class DependencyDirectionError(ContractViolation):
    """A dependency points at an equal or higher layer without a declared edge."""

    code = "ARK-ERR-0005"


class ArchitectureBudgetError(ContractViolation):
    """A numeric architecture budget is exceeded without an approved exception."""

    code = "ARK-ERR-0006"


class ProtectedCoreViolation(GovernanceStateError):
    """A Protected Core boundary was crossed without the required gate."""

    code = "ARK-ERR-0007"


class PhaseProgressionDenied(GovernanceStateError):
    """Progression to the requested phase is not legal."""

    code = "ARK-ERR-0008"


class HumanGateRequired(PhaseProgressionDenied):
    """A human gate is required and no acceptance record exists."""

    code = "ARK-ERR-0009"


# Phase 3 extends this taxonomy in sibling modules rather than here, because
# `max_public_symbols_per_module` is 20 and the combined taxonomy exceeds it.
# Decomposition is the intended response to a budget (ADR-0008); a GATE 8
# exception is not, and would in any case have to be authored by someone other
# than the implementing actor. See `state_machine_errors` and
# `capability_errors`, both owned by kernel.contracts.
