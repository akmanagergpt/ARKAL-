"""C-12 registry error types.

Owner: `control.registry.project`.

WHY THESE ARE NOT IN `kernel.contracts.errors`. Adding two more importers of the
kernel taxonomy pushed `arkali.kernel.contracts.errors` to fan-in 16 against a
budget of 15. The budget was pointing at something real: every context reaching
directly into one error module turns the kernel into a hub. ADR-0008 makes
decomposition the response to a budget, not an exception, and the security
taxonomy took the same route at Phase 4 - the shared base stays in the kernel
and the concrete types live with the context that raises them.

Exactly one module in this context imports the kernel taxonomy, and it is this
one.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import ContractViolation


class InvalidProjectIdentity(ContractViolation):
    """A project or revision identity is empty or malformed."""

    code = "ARK-ERR-0010"


class UnknownProject(ContractViolation):
    """A revision or transition names a project that does not exist."""

    code = "ARK-ERR-0011"


class DuplicateIdentity(ContractViolation):
    """A project or revision identity is already registered."""

    code = "ARK-ERR-0012"


class ImmutableRevisionViolation(ContractViolation):
    """An attempt to modify a persisted revision record."""

    code = "ARK-ERR-0013"
