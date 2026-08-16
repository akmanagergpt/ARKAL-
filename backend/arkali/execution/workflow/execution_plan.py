"""C-20 derived, compiled execution plan (ADR-0004).

Owner: `execution.workflow`.

ADR-0004: "Derived compiled or cached representations are permitted only when
deterministically derived from [the canonical revision], hash-bound to it, and
invalidated by any change to it. A derived representation whose bound hash
differs from the current canonical revision is never executed." This module is
that permission, exercised exactly once: `CompiledExecutionPlan` is the
executor's dispatch-ready view of a `WorkflowGraphDocument` - node and edge
lookups precomputed instead of re-scanned per step - and nothing more.

WHY THE FULL CONTENT HASH, NOT A NARROWER "EXECUTION-RELEVANT" ONE. Binding to
`WorkflowGraphDocument.content_hash` (which covers layout too, per that
module's own docstring) is a strictly STRONGER invalidation guarantee than a
hash over only execution-relevant fields would be: "any change... invalidates"
is satisfied by construction, never by an enumerated subset of fields that a
future node type could fall outside of.

DETERMINISTIC BY CONSTRUCTION, NOT BY CONVENTION. `derive` reads
`document.nodes()`/`document.edges()`, both already normalised (sorted,
insertion-order-independent) by `WorkflowGraphDocument`. Deriving twice from an
identically-content document - built in any assembly order - produces two
plans with identical `bound_revision_hash` and identical lookup tables.

THE PLAN IS NEVER AN AUTHORITY. It is a read-only projection with no method
that could grant it one: no publish, no validity override, no independent
identity. `execution.workflow`'s sole authority is `WorkflowGraphStore`
(Package 2); this module answers only "what does this canonical revision say",
precomputed for repeated lookups.
"""

from __future__ import annotations

from typing import Final

from arkali.execution.workflow.errors import StaleDerivedRepresentation
from arkali.execution.workflow.graph_model import WorkflowEdge, WorkflowGraphDocument, WorkflowNode

C20_SOURCE: Final[str] = "ADR-0004 + CONTRACT_INVENTORY.md row 46 (C-20)"


class CompiledExecutionPlan:
    """A dispatch-ready, hash-bound view of one canonical graph revision.

    Build with `derive`, never `__init__` directly - the same discipline
    `WorkflowGraphDocument.build` uses, so a plan can never exist bound to a
    hash nobody actually computed from its own content.
    """

    def __init__(
        self,
        workflow_id: str,
        bound_revision_hash: str,
        nodes_by_id: dict[str, WorkflowNode],
        outgoing_by_id: dict[str, tuple[WorkflowEdge, ...]],
        trigger_ids: tuple[str, ...],
    ) -> None:
        self.workflow_id = workflow_id
        self.bound_revision_hash = bound_revision_hash
        self._nodes_by_id = nodes_by_id
        self._outgoing_by_id = outgoing_by_id
        self.trigger_ids = trigger_ids

    @classmethod
    def derive(cls, document: WorkflowGraphDocument) -> CompiledExecutionPlan:
        """Deterministically derive a plan from exactly this document's
        declared content, bound to its `content_hash`.
        """
        nodes_by_id = {n.node_id: n for n in document.nodes()}
        outgoing_by_id = {
            node_id: document.outgoing(node_id) for node_id in nodes_by_id
        }
        return cls(
            document.workflow_id,
            document.content_hash,
            nodes_by_id,
            outgoing_by_id,
            document.trigger_node_ids(),
        )

    # -- reads -----------------------------------------------------------

    def node(self, node_id: str) -> WorkflowNode | None:
        return self._nodes_by_id.get(node_id)

    def outgoing(self, node_id: str) -> tuple[WorkflowEdge, ...]:
        return self._outgoing_by_id.get(node_id, ())

    def node_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._nodes_by_id))

    # -- staleness (ADR-0004) ------------------------------------------------

    def is_stale(self, current_revision_hash: str) -> bool:
        """Whether this plan's bound hash no longer matches the canonical
        revision it claims to be derived from."""
        return self.bound_revision_hash != current_revision_hash

    def require_fresh(self, current_revision_hash: str) -> None:
        """ADR-0004's hard rule, as a refusal a caller cannot skip.

        A stale-hash derived representation is never executed - not warned
        about, not executed-with-a-note. There is no branch here that
        proceeds after a mismatch.
        """
        if self.is_stale(current_revision_hash):
            raise StaleDerivedRepresentation(
                f"compiled execution plan for workflow {self.workflow_id!r} is "
                f"bound to revision hash {self.bound_revision_hash}, which does "
                f"not match the current canonical revision hash "
                f"{current_revision_hash}; a stale-hash derived representation "
                "is never executed",
                source=C20_SOURCE,
            )
