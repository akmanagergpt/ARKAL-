"""Deterministic domain-error to HTTP-status mapping.

Owner: `surfaces.command`.

WHY THIS IS A SEPARATE MODULE. `app.py` already touches three bounded contexts
- `control.registry.project`, `control.policy` and `kernel.persistence` - which
is exactly `max_contexts_touched_by_module`. Importing the state-machine error
taxonomy there as well would make four. The budget is pointing at real coupling:
a surface module that reaches into every context is the central object the
constitution forbids. ADR-0008 makes decomposition the answer.

NOTHING IS SWALLOWED. Every mapped error becomes a refusal with the domain
error's own code and message. There is no branch that turns a refused operation
into a success, and an unmapped error is deliberately NOT given a default status
- it propagates, so an unforeseen failure surfaces as a server error rather than
being quietly reported as a client mistake.

NO LEAKAGE. Only `code` and `message` cross the boundary. `ArkaliError.__str__`
appends its `source`, which can name a canonical document; that rendering is
never used here.
"""

from __future__ import annotations

from typing import Final

from arkali.control.policy.policy_errors import PolicyDenied
from arkali.control.registry.project.errors import (
    DuplicateIdentity,
    ImmutableRevisionViolation,
    InvalidProjectIdentity,
    UnknownProject,
)
from arkali.kernel.contracts.errors import ArkaliError
from arkali.kernel.contracts.state_machine_errors import (
    ForbiddenTransition,
    IllegalTransition,
    TerminalStateEscape,
    UnknownState,
)
from arkali.surfaces.command.job_error_mapping import DURABLE_STATUS_BY_ERROR
from arkali.surfaces.command.workflow_error_mapping import status_for_workflow_error

#: The one base every mapped refusal derives from, re-exported so the
#: application can register a handler for it WITHOUT importing
#: `kernel.contracts` itself: `app.py` sits at `max_contexts_touched_by_module`
#: and this module already counts that context. A control asserts every mapped
#: type really is a subclass, so the handler cannot be registered on a base that
#: misses one.
DOMAIN_ERROR_BASE: Final[type[Exception]] = ArkaliError

#: Ordered most-specific first: `isinstance` is checked in this order, and
#: several of these share a base class.
#:
#: The durable half is COMPOSED from a same-context sibling rather than
#: written here, because this module already touches three bounded contexts
#: and that is the whole budget. The workflow half is matched by class NAME
#: instead of `isinstance` (`workflow_error_mapping.status_for_workflow_error`)
#: for a stronger reason than the budget: composing `execution.workflow` here
#: would extend an already-four-hop chain to five and breach
#: `max_orchestration_depth`, so `status_for` below checks this table first
#: and falls back to the name-matched one. Both tables are disjoint - no
#: durable or workflow error is a project error or a state-machine error - so
#: appending cannot shadow an entry above. `PolicyDenied` stays first
#: regardless, since a refusal by policy is never a client formatting
#: problem.
STATUS_BY_ERROR: Final[tuple[tuple[type[Exception], int], ...]] = (
    # A refusal by policy is never a client formatting problem.
    (PolicyDenied, 403),
    (UnknownProject, 404),
    (DuplicateIdentity, 409),
    (ImmutableRevisionViolation, 409),
    (InvalidProjectIdentity, 400),
    # The target state does not exist in the canonical machine at all.
    (UnknownState, 422),
    # The target exists but the move is not permitted from the current state.
    (TerminalStateEscape, 409),
    (ForbiddenTransition, 409),
    (IllegalTransition, 409),
) + DURABLE_STATUS_BY_ERROR


def status_for(error: Exception) -> int | None:
    """The HTTP status for a domain error, or None if it is not mapped.

    None means "this surface has no opinion", and the caller must let the error
    propagate rather than inventing a status for it.
    """
    for error_type, status in STATUS_BY_ERROR:
        if isinstance(error, error_type):
            return status
    return status_for_workflow_error(error)


def code_of(error: Exception) -> str:
    """The canonical error code, so clients branch on a stable value."""
    return str(getattr(error, "code", type(error).__name__))


def message_of(error: Exception) -> str:
    """The domain message only - never the rendered exception with its source."""
    return str(getattr(error, "message", str(error)))


def mapped_error_types() -> tuple[type[Exception], ...]:
    """Every error type this surface maps. Read by the coverage control."""
    return tuple(error_type for error_type, _ in STATUS_BY_ERROR)
