"""C-01 canonical error taxonomy — the abstract base layer.

Owner: kernel.contracts.

WHY THIS MODULE EXISTS. `errors.py` reached `max_fan_in_per_module` (15). Every
bounded context that raises a governance failure needs a base from this taxonomy,
so the module every context must import is the one that accumulates edges, and
the count only ever grows: `execution.scheduler` was the sixteenth. ADR-0008
makes decomposition the answer to a budget rather than an exception, and
`errors.py` already carries the instruction in its own closing comment - Phase 3
split `state_machine_errors` and `capability_errors` out of it for exactly this
reason.

THE SEAM IS REAL, NOT ARITHMETIC. What lives here is the part of the taxonomy
that other contexts *derive from*: the root, the contract-violation base, and the
two governance-state bases a parser raises. What stays in `errors.py` is the part
other contexts *catch* - concrete failures owned by the architecture and phase
machinery. A context declaring its own error types needs the first group and not
the second, which is why the edge count divides cleanly along this line instead
of being balanced to fit.

NOTHING MOVED FOR CALLERS. `errors.py` re-exports all four names, so every
existing importer is unchanged and no call site was touched to make room. A
re-export adds no public surface: the budget counts top-level definitions, not
imported names.

Rule, unchanged: no error type in this taxonomy may be caught and converted into
a PASS.
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
