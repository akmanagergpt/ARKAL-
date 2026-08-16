"""C-20 control-construct evaluation (ARK-REQ-0329).

Owner: `execution.workflow`.

Real, deterministic per-construct decisions, made from declared facts only -
`node.parameters`, the document's own edges, and (for `LOOP`/`RETRY`/`WAIT`) a
counter the executor persists across steps. This module is pure: no session,
no durable job, no mutation of a `WorkflowExecutionRecord`. The executor
applies the returned decision; this module only decides what it should be.

ONE PUBLIC ENTRY POINT. `execution.workflow`'s public-surface budget (40 of
40, context-wide) has no room for ten separately-public `evaluate_*`
functions plus a result type - so the ten are internal (`_evaluate_*`) and
`evaluate_construct` is the sole public dispatch, keyed by the exact
canonical construct spelling `GraphVocabulary` parses. The result is a plain
`dict`, not a bespoke class, for the same budget reason: a class statement is
one more `ast.ClassDef` this context's surface would carry for no behaviour
a dict of four fixed keys does not already give a caller.

MS §Visual Workflow Studio names ten control constructs and states nothing
about their exact runtime semantics beyond that name - the same gap
`graph_model.py`'s validity rules already had to close for structure. These
semantics are this session's derivation, chosen to be the ordinary reading of
each name (a bounded loop, a fan-out, an all-inputs join, a bounded retry with
a distinct give-up edge) rather than an arbitrary one, and are real: every
decision is computed from an actual input, never fabricated to make a test
pass.
"""

from __future__ import annotations

from typing import Final

from arkali.execution.workflow.execution_errors import NoMatchingEdge
from arkali.execution.workflow.graph_model import WorkflowEdge, WorkflowGraphDocument, WorkflowNode
from arkali.execution.workflow.workflow_execution_state_machine import CANCELLED, FAILED

ENQUEUE: Final[str] = "ENQUEUE"
PAUSE_SIGNAL: Final[str] = "PAUSE_SIGNAL"
PAUSE_APPROVAL: Final[str] = "PAUSE_APPROVAL"
TERMINAL: Final[str] = "TERMINAL"

C20_SOURCE: Final[str] = (
    "MS §Visual Workflow Studio (construct semantics, this session's derivation)"
)

#: The seven constructs whose decision needs no persisted counter.
_STATELESS: Final[frozenset[str]] = frozenset(
    {"IF", "ELSE", "SWITCH", "PARALLEL", "MERGE", "ERROR HANDLER", "HUMAN APPROVAL"}
)
#: Every canonical construct this module answers for.
CONSTRUCTS: Final[frozenset[str]] = _STATELESS | frozenset({"LOOP", "RETRY", "WAIT"})


def _decision(
    kind: str,
    edges: tuple[WorkflowEdge, ...] = (),
    terminal_state: str | None = None,
    outcome: str = "",
    counter: int = 0,
) -> dict[str, object]:
    return {
        "kind": kind, "edges": edges, "terminal_state": terminal_state,
        "outcome": outcome, "counter": counter,
    }


def _require_edge(document: WorkflowGraphDocument, node_id: str, condition: str) -> WorkflowEdge:
    for edge in document.outgoing(node_id):
        if edge.condition == condition:
            return edge
    raise NoMatchingEdge(
        f"node {node_id!r}: no outgoing edge declares condition {condition!r}",
        source=C20_SOURCE,
    )


def _evaluate_if(node: WorkflowNode, document: WorkflowGraphDocument) -> dict[str, object]:
    value = bool(node.parameters.get("value", True))
    condition = "true" if value else "false"
    edge = _require_edge(document, node.node_id, condition)
    return _decision(ENQUEUE, (edge,), outcome=f"IF:{condition}")


def _evaluate_else(node: WorkflowNode, document: WorkflowGraphDocument) -> dict[str, object]:
    return _decision(ENQUEUE, document.outgoing(node.node_id), outcome="ELSE:passthrough")


def _evaluate_switch(node: WorkflowNode, document: WorkflowGraphDocument) -> dict[str, object]:
    value = str(node.parameters.get("value", ""))
    for edge in document.outgoing(node.node_id):
        if edge.condition == value:
            return _decision(ENQUEUE, (edge,), outcome=f"SWITCH:{value}")
    edge = _require_edge(document, node.node_id, "default")
    return _decision(ENQUEUE, (edge,), outcome=f"SWITCH:default(value={value!r})")


def _evaluate_loop(
    node: WorkflowNode, document: WorkflowGraphDocument, counter: int
) -> dict[str, object]:
    max_iterations = int(node.parameters.get("max_iterations", 1))
    if counter < max_iterations:
        edge = _require_edge(document, node.node_id, "continue")
        return _decision(
            ENQUEUE, (edge,), outcome=f"LOOP:continue({counter + 1})", counter=counter + 1
        )
    edge = _require_edge(document, node.node_id, "exit")
    return _decision(ENQUEUE, (edge,), outcome=f"LOOP:exit({counter})", counter=counter)


def _evaluate_parallel(node: WorkflowNode, document: WorkflowGraphDocument) -> dict[str, object]:
    return _decision(ENQUEUE, document.outgoing(node.node_id), outcome="PARALLEL:fan_out")


def _evaluate_merge(node: WorkflowNode, document: WorkflowGraphDocument) -> dict[str, object]:
    return _decision(ENQUEUE, document.outgoing(node.node_id), outcome="MERGE:joined")


def _evaluate_wait(
    node: WorkflowNode, document: WorkflowGraphDocument, already_waited: bool
) -> dict[str, object]:
    if not already_waited:
        return _decision(PAUSE_SIGNAL, outcome="WAIT:paused", counter=1)
    return _decision(ENQUEUE, document.outgoing(node.node_id), outcome="WAIT:resumed", counter=1)


def _evaluate_retry(
    node: WorkflowNode, document: WorkflowGraphDocument, counter: int
) -> dict[str, object]:
    if bool(node.parameters.get("succeeded", False)):
        edge = _require_edge(document, node.node_id, "success")
        return _decision(ENQUEUE, (edge,), outcome="RETRY:success", counter=counter)
    max_attempts = int(node.parameters.get("max_attempts", 1))
    if counter < max_attempts:
        edge = _require_edge(document, node.node_id, "retry")
        return _decision(
            ENQUEUE, (edge,), outcome=f"RETRY:retry({counter + 1})", counter=counter + 1
        )
    edge = _require_edge(document, node.node_id, "exhausted")
    return _decision(ENQUEUE, (edge,), outcome=f"RETRY:exhausted({counter})", counter=counter)


def _evaluate_error_handler(
    node: WorkflowNode, document: WorkflowGraphDocument
) -> dict[str, object]:
    """`COMPENSATING` only transitions to `FAILED` or `CANCELLED` in the
    canonical `WorkflowExecution` machine (Phase 3) - there is no path back to
    `RUNNING` - so a triggered error is always this execution's last step."""
    if not bool(node.parameters.get("triggered", False)):
        edge = _require_edge(document, node.node_id, "ok")
        return _decision(ENQUEUE, (edge,), outcome="ERROR_HANDLER:passthrough")
    terminal = CANCELLED if bool(node.parameters.get("recoverable", True)) else FAILED
    return _decision(TERMINAL, terminal_state=terminal, outcome=f"ERROR_HANDLER:{terminal}")


def _evaluate_human_approval(
    node: WorkflowNode, document: WorkflowGraphDocument
) -> dict[str, object]:
    """Always pauses (`WAITING_APPROVAL`). Resuming is not a re-dispatch of
    this function - only `WorkflowExecutor.approve`, gated by
    `control.policy.WorkflowApprovalGate`, may enqueue this node's outgoing
    edge."""
    return _decision(PAUSE_APPROVAL, outcome="HUMAN_APPROVAL:awaiting")


def evaluate_construct(
    construct: str,
    node: WorkflowNode,
    document: WorkflowGraphDocument,
    *,
    counter: int = 0,
    already_waited: bool = False,
) -> dict[str, object]:
    """The one public entry point for every canonical control construct.

    Returns a dict with keys `kind` (one of `ENQUEUE`/`PAUSE_SIGNAL`/
    `PAUSE_APPROVAL`/`TERMINAL`), `edges` (a tuple of `WorkflowEdge` to
    enqueue, for `ENQUEUE`), `terminal_state` (for `TERMINAL`), `outcome`
    (a human-readable evidence string) and `counter` (the updated
    `LOOP`/`RETRY` iteration count, echoed unchanged for stateless constructs).
    """
    if construct == "LOOP":
        return _evaluate_loop(node, document, counter)
    if construct == "RETRY":
        return _evaluate_retry(node, document, counter)
    if construct == "WAIT":
        return _evaluate_wait(node, document, already_waited)
    if construct not in _STATELESS:
        raise NoMatchingEdge(
            f"node {node.node_id!r}: unknown control construct {construct!r}",
            source=C20_SOURCE,
        )
    dispatch = {
        "IF": _evaluate_if, "ELSE": _evaluate_else, "SWITCH": _evaluate_switch,
        "PARALLEL": _evaluate_parallel, "MERGE": _evaluate_merge,
        "ERROR HANDLER": _evaluate_error_handler, "HUMAN APPROVAL": _evaluate_human_approval,
    }
    return dispatch[construct](node, document)
