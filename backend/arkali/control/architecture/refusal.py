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
"""

from __future__ import annotations

from arkali.kernel.contracts.errors import AuthoritativeSourceError


def refuse(message: str, source: str) -> AuthoritativeSourceError:
    """Build the canonical refusal. Callers raise it; nothing here swallows one."""
    return AuthoritativeSourceError(message, source=source)
