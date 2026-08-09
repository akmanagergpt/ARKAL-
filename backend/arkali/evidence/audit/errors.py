"""C-15 audit chain error types.

Owner: `evidence.audit` (Protected Core).

Same reasoning as the C-12 and C-14 taxonomies: the shared base stays in the
kernel and the concrete types live with the context that raises them, because
`kernel.contracts.errors` sits at its fan-in budget and ADR-0008 makes
decomposition the answer to a budget rather than an exception. Exactly one
module in this context imports the kernel taxonomy, and it is this one.

Each failure mode is a distinct type so a negative control can assert the
*reason* an append was refused. A control asserting only that something raised
would pass for an unrelated reason - the F-0017 defect.

Codes are allocated from 0060 upward; 0050-0053 belong to `evidence.artifact`.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import ContractViolation


class InvalidEvidenceRecord(ContractViolation):
    """A field is missing, malformed, or an identity was supplied by a caller."""

    code = "ARK-ERR-0060"


class OrphanEvidence(ContractViolation):
    """The record names no requirement the canonical register recognises.

    `VERIFICATION_ARCHITECTURE.md` section 2.2 rule 3: evidence not reachable
    from an ARK-REQ does not count. Counting is Phase 13; refusing to store a
    structurally unreachable record is this phase's share of the rule.
    """

    code = "ARK-ERR-0061"


class UnknownEvidenceRecord(ContractViolation):
    """A supersession or linkage names a record that is not in the chain."""

    code = "ARK-ERR-0062"


class EvidenceImmutabilityViolation(ContractViolation):
    """An attempt to modify or delete a persisted evidence record.

    Correcting an outcome means appending a record that supersedes the old one.
    The old one stays visible; nothing is rewritten.
    """

    code = "ARK-ERR-0063"


class ChainIntegrityViolation(ContractViolation):
    """The stored chain does not recompute to the digests it carries.

    Never repaired automatically. A mismatch means the chain was altered, and
    rewriting it to agree with itself would destroy the only evidence of that.
    """

    code = "ARK-ERR-0064"


class IllegalSupersession(ContractViolation):
    """A record cannot supersede itself, or supersede an already-superseded one."""

    code = "ARK-ERR-0065"
