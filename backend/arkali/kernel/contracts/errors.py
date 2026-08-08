"""C-01 canonical error taxonomy.

Owner: kernel.contracts. Every governance failure raised by ARKALI derives from
`ArkaliError` and carries a stable machine-readable code, so failures can be
asserted against rather than matched by message text.

Rule: no error type in this taxonomy may be caught and converted into a PASS.
"""

from __future__ import annotations


class ArkaliError(Exception):
    """Base of the canonical error taxonomy."""

    code: str = "ARK-ERR-0000"

    def __init__(self, message: str, *, source: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.source = source

    def __str__(self) -> str:
        base = f"[{self.code}] {self.message}"
        return f"{base} (source: {self.source})" if self.source else base


class ContractViolation(ArkaliError):
    """A value does not satisfy its declared contract."""

    code = "ARK-ERR-0001"


class GovernanceStateError(ArkaliError):
    """Governance state is missing, malformed or self-contradictory.

    Raised rather than repaired: the Phase Gate Checker must fail closed and
    must never silently repair governance data.
    """

    code = "ARK-ERR-0002"


class AuthoritativeSourceError(GovernanceStateError):
    """An authoritative artifact is absent or unparseable."""

    code = "ARK-ERR-0003"


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
