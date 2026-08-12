"""C-24 code graph / Digital Twin failure taxonomy (Phase 11).

Owner: `engineering.codeintel`.

WHY THESE ARE NOT IN `kernel.contracts`. Same reason as the C-11, C-12, C-14,
C-15, C-19, C-21 and C-22 taxonomies before them: `kernel.contracts.errors` is
at its `max_fan_in_per_module` ceiling of 15 and the context's public surface has
no room, which Phase 10 established by MEASUREMENT when the architecture gate
refused a taxonomy placed there at 42 of 40. ADR-0008 makes decomposition the
answer to a budget rather than an exception. The abstract base comes from
`kernel.contracts.error_base`, so this context adds no edge to `errors.py`.

Each failure mode is a distinct type so a negative control can assert the
*reason* something was refused. A control asserting only that an exception was
raised would pass for an unrelated reason - the F-0017 defect.

NO ERROR HERE MAY BE CAUGHT AND CONVERTED INTO A PASS. In particular
`NonDeterministicRebuild` must never be downgraded to "the graph changed
because the source changed": `CONTRACT_INVENTORY.md` row 24 names rebuild
determinism as C-24's verification, so a rebuild that differs from an identical
input is a contract violation and not a fact about the repository.

Codes are allocated from 0097 upward; 0095-0096 belong to `control.policy`.
"""

from __future__ import annotations

from arkali.kernel.contracts.error_base import ContractViolation


class CodeIntelligenceError(ContractViolation):
    """Base of the code-graph / Digital Twin failure taxonomy."""

    code = "ARK-ERR-0097"


class UnknownGraphKind(CodeIntelligenceError):
    """A graph kind the canonical architecture does not declare."""

    code = "ARK-ERR-0098"


class UnknownTwinView(CodeIntelligenceError):
    """A Digital Twin view the canonical architecture does not declare."""

    code = "ARK-ERR-0099"


class IncompleteDigitalTwin(CodeIntelligenceError):
    """The twin does not compose every view the canonical architecture names."""

    code = "ARK-ERR-0100"


class DerivedStoreTreatedAsAuthority(CodeIntelligenceError):
    """Something asked the twin to be the source of truth for an owned concern.

    `ARCHITECTURE.md` §11: the twin "is a **derived** store - never an authority
    - and is rebuildable from source plus the owning authorities." Answering as
    an authority would make it a second store of somebody else's concern.
    """

    code = "ARK-ERR-0101"


class NonDeterministicRebuild(CodeIntelligenceError):
    """Rebuilding from identical input produced a different graph."""

    code = "ARK-ERR-0102"
