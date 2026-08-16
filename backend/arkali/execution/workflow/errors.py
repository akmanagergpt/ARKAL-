"""C-20 canonical workflow graph error types (ARK-REQ-0062 … 0065, 0328 … 0332).

Owner: `execution.workflow`.

WHY THESE ARE NOT IN `kernel.contracts.errors`. Same reason `execution.scheduler`
and `execution.durable` keep their own: `errors.py` sits at its fan-in budget
(15) and ADR-0008 makes decomposition the answer to a budget rather than an
exception. The abstract base layer is imported from
`kernel.contracts.error_base`, which already carries `execution.scheduler`,
`execution.durable` and eleven other contexts at fan-in 12 of 15 - this context
is the thirteenth, still inside the budget.

Each failure mode is a distinct type so a negative control can assert the
*reason* something was refused, not merely that something was raised (the
F-0017 defect, applied here).

Codes are allocated from 0116 upward; 0115 is the highest code allocated
elsewhere in the repository as of Phase 17.
"""

from __future__ import annotations

from arkali.kernel.contracts.error_base import (
    AuthoritativeSourceError,
    ContractViolation,
)


class CanonicalWorkflowSourceError(AuthoritativeSourceError):
    """The canonical VDC §Workflow identity section is absent or unparseable.

    Distinct from every declaration failure below: this says the *authority*
    could not be read, not that a graph declared something wrong.
    """

    code = "ARK-ERR-0116"


class UnknownNodeKind(ContractViolation):
    """A node declares a kind the canonical VDC list does not define."""

    code = "ARK-ERR-0117"


class UnknownControlConstruct(ContractViolation):
    """A node declares a control construct the canonical VDC list does not
    define."""

    code = "ARK-ERR-0118"


class ConstructKindMismatch(ContractViolation):
    """A construct is declared on a non-`logic` node, or a `logic` node
    declares none.

    A control construct is a `logic`-kind concept (MS §Workflow Studio: IF,
    ELSE, SWITCH, LOOP, PARALLEL, MERGE, WAIT, RETRY, ERROR HANDLER and HUMAN
    APPROVAL are how a `logic` node governs flow). Allowing a `trigger` or
    `data` node to also carry a construct would make two fields answer the same
    question, and a `logic` node without one would be an unrunnable branch.
    """

    code = "ARK-ERR-0119"


class DuplicateNodeIdentity(ContractViolation):
    """Two nodes in one graph declare the same node id."""

    code = "ARK-ERR-0120"


class DuplicateEdgeIdentity(ContractViolation):
    """Two edges in one graph declare the same edge id."""

    code = "ARK-ERR-0121"


class DanglingEdgeReference(ContractViolation):
    """An edge names a source or target node id that the graph does not
    declare.

    Refused rather than dropped: the executor consumes exactly the declared
    graph (ARK-REQ-0328), so a silently-dropped edge would make the executed
    graph differ from the persisted one.
    """

    code = "ARK-ERR-0122"


class UnreachableNode(ContractViolation):
    """A node is not reachable, by edges, from any `trigger` node.

    A node that can never be entered can never produce execution evidence, so
    admitting it into a canonical, executable graph would make ARK-REQ-0329
    unsatisfiable for that node by construction.
    """

    code = "ARK-ERR-0123"


class NoTriggerNode(ContractViolation):
    """A graph declares no `trigger`-kind node, so it has no entry point."""

    code = "ARK-ERR-0124"


class EmptyGraph(ContractViolation):
    """A graph declares no nodes at all."""

    code = "ARK-ERR-0125"


class InvalidSemverTransition(ContractViolation):
    """A declared semver bump does not follow from the prior revision's semver.

    MAJOR/MINOR/PATCH is author-declared per revision (C-20 is `STRICT`
    compatibility - "no breaking change without MAJOR"), but the arithmetic
    itself - which single field increments and that the lower fields reset -
    is never taken on the author's word.
    """

    code = "ARK-ERR-0126"


class StaleDerivedRepresentation(ContractViolation):
    """A derived/compiled representation's bound hash does not match the
    current canonical revision (ADR-0004).

    This is the structural refusal ARK-REQ-0065 and ARK-REQ-0332 require: a
    stale-hash derived representation is never executed, not merely warned
    about.
    """

    code = "ARK-ERR-0127"


class NonDeterministicGraphRebuild(ContractViolation):
    """Rebuilding a graph's content address from its own declared content
    produced a different address than the one it was constructed with."""

    code = "ARK-ERR-0128"


class UnknownWorkflow(ContractViolation):
    """No workflow is registered under a given workflow id."""

    code = "ARK-ERR-0129"


class UnknownWorkflowRevision(ContractViolation):
    """No revision is registered under a given (workflow id, revision
    number)."""

    code = "ARK-ERR-0130"


class ImmutableRevisionViolation(ContractViolation):
    """A persisted revision was updated or deleted.

    A restart, an executor and a reader all trust that a revision, once
    persisted, reads back identically forever - the C-20 "revision-hashed"
    half of its declared versioning is meaningless otherwise.
    """

    code = "ARK-ERR-0131"


class RevisionIntegrityViolation(ContractViolation):
    """A persisted revision's stored content hash does not match the hash
    recomputed from its stored declared content.

    Never trusted on read: `WorkflowGraphStore` recomputes the hash from the
    stored nodes/edges every time and refuses a mismatch, rather than reading
    the stored hash column as if it were self-certifying.
    """

    code = "ARK-ERR-0132"
