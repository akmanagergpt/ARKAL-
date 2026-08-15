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

THIS MODULE HIT THE SAME CEILING, AND THE SAME ANSWER APPLIES A SECOND TIME.
`engineering.repair` was the sixteenth context needing a base from here, so
`ContractViolation` moved to `contract_violation_base.py` and `ArkaliError`
moved to `error_root.py`, and this module imports both back and re-exports
them - unchanged for all fifteen existing importers, for the identical reason
the split above holds. A new consumer of only `ContractViolation` should
import `contract_violation_base` directly, the way a new consumer of only
`ArkaliError` should import `error_root` directly, so this module's own
fan-in stops absorbing every future context.

Rule, unchanged: no error type in this taxonomy may be caught and converted into
a PASS.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation
from arkali.kernel.contracts.error_root import ArkaliError

__all__ = [
    "ArkaliError",
    "AuthoritativeSourceError",
    "ContractViolation",
    "GovernanceStateError",
]


class GovernanceStateError(ArkaliError):
    """Governance state is missing, malformed or self-contradictory.

    Raised rather than repaired: the Phase Gate Checker must fail closed and
    must never silently repair governance data.
    """

    code = "ARK-ERR-0002"


class AuthoritativeSourceError(GovernanceStateError):
    """An authoritative artifact is absent or unparseable."""

    code = "ARK-ERR-0003"
