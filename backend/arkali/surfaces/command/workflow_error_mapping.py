"""C-20 workflow error to HTTP-status mapping.

Owner: `surfaces.command`. Phase 17 Package 6.

MATCHED BY CLASS NAME, NOT `isinstance` - AND THAT IS DELIBERATE, NOT A
SHORTCUT. `error_mapping.py`'s other two tables `isinstance`-check a real
imported type. Doing the same here would import
`execution.workflow.errors`/`execution_errors`, which - composed with
`workflow.py`'s Protocol-typed collaborators avoiding exactly this - would
still leave a `surfaces.command → execution.workflow` edge that extends the
already-four-hop `execution.workflow → execution.durable → control.policy →
kernel.contracts` chain to five and breaches `max_orchestration_depth`.
Every workflow error type here is a leaf `ContractViolation` with no further
subclass this surface would need to also catch, so exact class-name matching
loses nothing `isinstance` would have given it - the same trade-off
`workflow.py`'s `Protocol` collaborators already make.

NOTHING IS SWALLOWED AND NOTHING IS DEFAULTED. Only the refusals this surface
genuinely has an opinion about appear. An unmapped workflow error propagates,
so an unforeseen failure surfaces as a server error rather than being
reported as a client mistake.
"""

from __future__ import annotations

from typing import Final

#: Ordered most-specific first, matching the sibling tables' discipline.
#:
#: Graph-validity refusals (`EmptyGraph`, `NoTriggerNode`, `UnreachableNode`,
#: duplicate/dangling/mismatch, `NoMatchingEdge`) are 400: the caller
#: submitted a graph the canonical rules refuse, and the shape is theirs to
#: fix. `Unknown*` lookups are 404. `AutomatedActorCannotApprove` is 403,
#: matching `PolicyDenied` in the sibling table - a refusal by policy is
#: never a client formatting problem. `RevisionIntegrityViolation`,
#: `NoPendingApproval` and `ApprovalNotEnforced` are 409: each names a real
#: conflict between the request and the execution's or revision's current
#: state, not malformed input.
WORKFLOW_STATUS_BY_ERROR_NAME: Final[tuple[tuple[str, int], ...]] = (
    ("AutomatedActorCannotApprove", 403),
    ("UnknownWorkflowExecution", 404),
    ("UnknownWorkflow", 404),
    ("UnknownWorkflowRevision", 404),
    ("NoPendingApproval", 409),
    ("ApprovalNotEnforced", 409),
    ("RevisionIntegrityViolation", 409),
    ("EmptyGraph", 400),
    ("NoTriggerNode", 400),
    ("UnreachableNode", 400),
    ("DuplicateNodeIdentity", 400),
    ("DuplicateEdgeIdentity", 400),
    ("DanglingEdgeReference", 400),
    ("ConstructKindMismatch", 400),
    ("UnknownNodeKind", 400),
    ("UnknownControlConstruct", 400),
    ("NoMatchingEdge", 400),
)


def status_for_workflow_error(error: Exception) -> int | None:
    """The HTTP status for a workflow domain error, matched by exact class
    name - or None if it is not one of the names above."""
    name = type(error).__name__
    for error_name, status in WORKFLOW_STATUS_BY_ERROR_NAME:
        if name == error_name:
            return status
    return None


def workflow_error_names() -> tuple[str, ...]:
    """Every workflow error class name this surface maps. Read by the
    coverage control."""
    return tuple(name for name, _ in WORKFLOW_STATUS_BY_ERROR_NAME)
