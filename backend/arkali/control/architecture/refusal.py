"""The canonical refusal for `control.architecture`.

Owner: control.architecture (Protected Core).

WHY THIS MODULE EXISTS. Three modules in this context imported
`AuthoritativeSourceError` from `kernel.contracts.errors` purely to raise it,
which is three edges into a module whose fan-in budget is 15 and which Phase 6
pushed past it. ADR-0008 makes decomposition the answer to a budget rather than
an exception, and the budget was pointing at something real: every module
reaching directly into one error module is what turns the kernel into a hub.

`acceptance.engine` already took this shape - `governance_source.refuse` is its
single path - and `control.registry.project` documents the same rule: exactly
one module per context imports the kernel taxonomy.

NOTHING IS WEAKENED. The same exception type is raised, with the same message
and the same source. Only the number of edges changes.

COMPLETED AT PHASE 7 PACKAGE 1. The docstring above named three modules, but
Phase 6 routed only one of them through here and left the other two importing
the kernel directly - which held at a fan-in of exactly 15, with no headroom, so
the next context to declare an error module pushed it to 16 again. It did:
`execution.durable`. The decomposition is now applied to all three, taking the
fan-in to 14, and `refuse_governance_state` is added because `gates/runner.py`
raises the parent type rather than the authoritative-source one.
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import (
    AuthoritativeSourceError,
    GovernanceStateError,
)


def refuse(message: str, source: str = "") -> AuthoritativeSourceError:
    """Build the canonical refusal. Callers raise it; nothing here swallows one.

    `source` defaults to empty because the base error already treats an absent
    source that way, so a call site that has no document to name behaves exactly
    as it did when it constructed the exception itself.
    """
    return AuthoritativeSourceError(message, source=source)


def refuse_governance_state(message: str, source: str = "") -> GovernanceStateError:
    """The parent refusal, for state that is malformed but not a missing source."""
    return GovernanceStateError(message, source=source)
