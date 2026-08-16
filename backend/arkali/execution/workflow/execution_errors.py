"""C-20 executor error types (ARK-REQ-0328 … 0330, 0332).

Owner: `execution.workflow`.

SEPARATE FROM `errors.py` BY DECOMPOSITION, NOT BY ACCIDENT. `errors.py`
(Package 1/2's graph-identity and persistence errors) already carries 17 of
the 20 `max_public_symbols_per_module` budget. ADR-0008 makes decomposition
the answer to a budget rather than an exception, and the seam here is real:
`errors.py` is about what a *declared graph* may say; this module is about
what a *running execution* may do. Every type here is still a
`ContractViolation`.

IMPORTS `contract_violation_base` DIRECTLY, NOT `error_base`. `errors.py`
already added the context's one `error_base` edge (fan-in 13 of 15) for
`AuthoritativeSourceError`, which nothing here needs. A context needing only
`ContractViolation` imports `contract_violation_base` directly (fan-in 8),
per the budget-facts guidance carried in this session's handoff.

Codes continue from 0134, the next free code after `errors.py`'s 0133 (owned
by `control.policy`'s `AutomatedActorCannotApprove`, Package 4) and this
context's own 0132.
"""

from __future__ import annotations

from arkali.kernel.contracts.contract_violation_base import ContractViolation


class UnknownWorkflowExecution(ContractViolation):
    """No execution is registered under a given execution id."""

    code = "ARK-ERR-0134"


class ExecutionNotRunning(ContractViolation):
    """An operation that requires `RUNNING` was attempted against an
    execution in a different lifecycle state.

    The canonical `WorkflowExecution` machine (Phase 3) is the sole
    transition authority; this is the executor's own precondition check
    before it ever asks the machine to evaluate a move.
    """

    code = "ARK-ERR-0135"


class NoPendingApproval(ContractViolation):
    """An approval was submitted for an execution that is not
    `WAITING_APPROVAL`, or for a node other than the one it is waiting on."""

    code = "ARK-ERR-0136"


class ApprovalNotEnforced(ContractViolation):
    """A submitted approval did not satisfy
    `control.policy.WorkflowApprovalGate.is_enforced_approval`.

    Refused rather than silently ignored: a caller must learn *that* its
    approval did not count, not have the execution stay quietly stuck.
    """

    code = "ARK-ERR-0137"


class UnknownPlanNode(ContractViolation):
    """The execution frontier names a node id the compiled plan does not
    contain.

    Structurally should be unreachable - `WorkflowGraphDocument` validity
    already refuses a dangling edge - so this is a defence against a
    corrupted or hand-edited persisted frontier, not an expected path.
    """

    code = "ARK-ERR-0138"


class NoMatchingEdge(ContractViolation):
    """A control construct evaluated a real decision but found no declared
    outgoing edge whose `condition` matches it.

    A graph-authoring defect, not a runtime data problem: `IF`/`SWITCH`/
    `LOOP`/`RETRY` each require the branch they select to exist as a real
    edge, and refuse rather than silently falling through.
    """

    code = "ARK-ERR-0139"
