"""C-14 artifact error types.

Owner: `evidence.artifact`.

WHY THESE ARE NOT IN `kernel.contracts.errors`. The same reason the C-12 registry
taxonomy is not: `arkali.kernel.contracts.errors` is already at the edge of its
fan-in budget, and ADR-0008 makes decomposition the answer to a budget rather
than an exception. The shared base stays in the kernel; the concrete types live
with the context that raises them. Phase 4's security taxonomy took the same
route.

Each failure mode is a distinct type so a negative control can assert the
*reason* something was refused. A control asserting only that an exception was
raised would pass for an unrelated reason - the F-0017 defect.

Codes are allocated from 0050 upward. Deliberately not from the low range: the
0010-0013 block is already carried by two different modules, so a new type there
would be a third meaning for a code a client is supposed to branch on.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import ContractViolation


class InvalidArtifactIdentity(ContractViolation):
    """A content address is malformed, or an identity was supplied by a caller."""

    code = "ARK-ERR-0050"


class UnknownArtifact(ContractViolation):
    """A provenance record or parent edge names an artifact that is not registered."""

    code = "ARK-ERR-0051"


class ArtifactImmutabilityViolation(ContractViolation):
    """An attempt to modify a persisted artifact or provenance record."""

    code = "ARK-ERR-0052"


class ArtifactContentMismatch(ContractViolation):
    """Stored bytes no longer hash to the address they are filed under.

    Never repaired automatically. A mismatch means either the bytes or the record
    is wrong, and silently rewriting one to agree with the other would destroy
    the only evidence that they ever disagreed.
    """

    code = "ARK-ERR-0053"
