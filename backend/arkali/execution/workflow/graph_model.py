"""C-20 canonical workflow graph document — the sole canonical authority.

Owner: `execution.workflow`. Contract: C-20 (`CONTRACT_INVENTORY.md` row 46).

THE GRAPH IS THE AUTHORITY, NOT A DERIVED STORE. Unlike `engineering.codeintel`'s
`CodeGraph` (C-24, a rebuildable projection that always refuses to answer an
authoritative question), a `WorkflowGraphDocument` IS the thing MS §Visual
Workflow Studio calls "the sole canonical authority": "UI rendering and backend
execution are two views of the same graph revision." There is no
`resolve_authority` refusal here, because refusing that question is exactly what
this module must not do.

WHY THE FULL DOCUMENT PARTICIPATES IN THE CONTENT HASH, NOT A SEMANTIC SUBSET.
ADR-0004 requires a derived/compiled representation to be "hash-bound to,
and invalidated by any change to" the canonical revision. Hashing the complete
persisted content - including layout/display fields - satisfies "any change"
trivially and without inventing a semantic/presentation split that no canonical
source states. A derived execution plan (`execution_plan.py`, Package 3) is free
to *use* only the execution-relevant fields; it must still be *bound to* this
same full-content hash, which is a strictly stronger, never weaker, invalidation
guarantee.

DETERMINISM BY NORMALISATION. Nodes and edges are stored in frozensets and
always rendered sorted, so insertion order and duplicate insertion cannot reach
the hash - the same technique C-24's `CodeGraph` uses, reused as a design idiom
only; this module does not import that context (forbidden higher-layer edge,
`AUTHORITY_MAP.yaml` `allow_higher_layer: false`).

GRAPH VALIDITY IS THE MINIMUM THE EXECUTOR NEEDS, NOT A WORKFLOW-DESIGN OPINION.
Every rule enforced here exists because its violation would make "the executor
consumes the canonical graph revision" (ARK-REQ-0328) either undefined (a
dangling edge, a duplicate id) or vacuous (an unreachable node can never receive
execution evidence, ARK-REQ-0329). Cycles are NOT forbidden: `LOOP` and `RETRY`
are canonical control constructs that require a back-edge to mean anything.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.execution.workflow.errors import (
    ConstructKindMismatch,
    DanglingEdgeReference,
    DuplicateEdgeIdentity,
    DuplicateNodeIdentity,
    EmptyGraph,
    InvalidSemverTransition,
    NonDeterministicGraphRebuild,
    NoTriggerNode,
    UnreachableNode,
)
from arkali.execution.workflow.graph_vocabulary import (
    LOGIC_KIND,
    TRIGGER_KIND,
    GraphVocabulary,
)
from arkali.kernel.contracts.content_address import address_of

C20_SOURCE: Final[str] = (
    "MS §Visual Workflow Studio + VDC §Workflow identity + ADR-0004 "
    "+ CONTRACT_INVENTORY.md row 46 (C-20)"
)

Declared = Annotated[str, Field(min_length=1)]


def _json_of(value: Any) -> str:
    """Deterministic rendering of free-form node parameters."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class WorkflowNode(BaseModel):
    """One node. `kind` and `construct` are validated against the canonical
    vocabulary only when the node is placed into a `WorkflowGraphDocument`; this
    type itself carries no vocabulary reference, so it stays a plain value
    object.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    node_id: Declared
    kind: Declared
    #: Set only on a `logic`-kind node; the one construct it implements. Named
    #: `control_construct`, not `construct`, so it does not shadow
    #: `pydantic.BaseModel.construct`.
    control_construct: str | None = None
    label: Declared = "untitled"
    #: Free-form, node-kind-specific configuration. Never interpreted here.
    parameters: dict[str, Any] = Field(default_factory=dict)
    #: Display-only layout. Participates in the content hash (see module
    #: docstring) but never in execution semantics.
    position_x: float = 0.0
    position_y: float = 0.0

    def rendering(self) -> tuple[str, ...]:
        return (
            self.node_id,
            self.kind,
            self.control_construct or "",
            self.label,
            _json_of(self.parameters),
            repr(self.position_x),
            repr(self.position_y),
        )

    def __hash__(self) -> int:
        """Identity for set membership is the normalised rendering, not
        Pydantic's default field-tuple hash - which cannot hash `parameters`,
        a plain `dict`, at all.
        """
        return hash(self.rendering())


class WorkflowEdge(BaseModel):
    """One directed edge between two node ids."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    edge_id: Declared
    source_node_id: Declared
    target_node_id: Declared
    #: A branch label for a `logic` source node (e.g. an IF's "true"/"false" or
    #: a SWITCH case). `None` for an unconditional edge.
    condition: str | None = None

    def rendering(self) -> tuple[str, str, str, str]:
        return (
            self.edge_id,
            self.source_node_id,
            self.target_node_id,
            self.condition or "",
        )


class WorkflowGraphDocument:
    """The canonical graph for one workflow. Build with `build`, never `__init__`
    directly, so validity is proven once at construction and never re-checked by
    convention.
    """

    def __init__(
        self,
        workflow_id: str,
        nodes: tuple[WorkflowNode, ...],
        edges: tuple[WorkflowEdge, ...],
    ) -> None:
        self.workflow_id = workflow_id
        self._nodes = nodes
        self._edges = edges

    @classmethod
    def build(
        cls,
        vocabulary: GraphVocabulary,
        workflow_id: str,
        *,
        nodes: Iterable[WorkflowNode] = (),
        edges: Iterable[WorkflowEdge] = (),
    ) -> WorkflowGraphDocument:
        """Declared content is kept as-given, not deduplicated by set
        membership: two nodes that differ only by id, or two exact-duplicate
        declarations of the same id, must both reach `_validate_node_ids`
        rather than silently collapsing to one through `frozenset` equality.
        """
        document = cls(workflow_id, tuple(nodes), tuple(edges))
        document._validate(vocabulary)
        return document

    # -- reads -----------------------------------------------------------

    def nodes(self) -> tuple[WorkflowNode, ...]:
        """Every node, in normalised order. Never insertion order."""
        return tuple(sorted(self._nodes, key=lambda n: n.rendering()))

    def edges(self) -> tuple[WorkflowEdge, ...]:
        """Every edge, in normalised order. Never insertion order."""
        return tuple(sorted(self._edges, key=lambda e: e.rendering()))

    def node(self, node_id: str) -> WorkflowNode | None:
        for candidate in self._nodes:
            if candidate.node_id == node_id:
                return candidate
        return None

    def trigger_node_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(n.node_id for n in self._nodes if n.kind == TRIGGER_KIND)
        )

    def outgoing(self, node_id: str) -> tuple[WorkflowEdge, ...]:
        return tuple(
            sorted(
                (e for e in self._edges if e.source_node_id == node_id),
                key=lambda e: e.rendering(),
            )
        )

    @property
    def content_hash(self) -> str:
        """The canonical content address of exactly this graph's declared
        content - nodes, edges, and workflow id. Order-independent by
        construction (see module docstring).
        """
        payload = _json_of(
            {
                "workflow_id": self.workflow_id,
                "nodes": [list(n.rendering()) for n in self.nodes()],
                "edges": [list(e.rendering()) for e in self.edges()],
            }
        )
        return address_of(payload.encode("utf-8"))

    def assert_rebuild_matches(self, rebuilt: WorkflowGraphDocument) -> None:
        """Anti-vacuity for `content_hash`: identical declared content must
        produce an identical hash regardless of assembly order.
        """
        if rebuilt.workflow_id != self.workflow_id:
            raise NonDeterministicGraphRebuild(
                f"rebuild produced workflow_id {rebuilt.workflow_id!r}, not "
                f"{self.workflow_id!r}",
                source=C20_SOURCE,
            )
        if rebuilt.content_hash != self.content_hash:
            raise NonDeterministicGraphRebuild(
                f"rebuild address {rebuilt.content_hash} does not match "
                f"{self.content_hash} for identical declared content",
                source=C20_SOURCE,
            )

    def __len__(self) -> int:
        return len(self._nodes)

    # -- validity ----------------------------------------------------------

    def _validate(self, vocabulary: GraphVocabulary) -> None:
        if not self._nodes:
            raise EmptyGraph("a canonical workflow graph declares no nodes", source=C20_SOURCE)
        self._validate_node_ids()
        self._validate_edge_ids()
        self._validate_kinds_and_constructs(vocabulary)
        self._validate_edge_references()
        self._validate_trigger_and_reachability()

    def _validate_node_ids(self) -> None:
        seen: set[str] = set()
        for node in self._nodes:
            if node.node_id in seen:
                raise DuplicateNodeIdentity(
                    f"node id {node.node_id!r} is declared more than once",
                    source=C20_SOURCE,
                )
            seen.add(node.node_id)

    def _validate_edge_ids(self) -> None:
        seen: set[str] = set()
        for edge in self._edges:
            if edge.edge_id in seen:
                raise DuplicateEdgeIdentity(
                    f"edge id {edge.edge_id!r} is declared more than once",
                    source=C20_SOURCE,
                )
            seen.add(edge.edge_id)

    def _validate_kinds_and_constructs(self, vocabulary: GraphVocabulary) -> None:
        for node in self._nodes:
            vocabulary.require_node_kind(node.kind)
            if node.control_construct is not None:
                vocabulary.require_control_construct(node.control_construct)
            is_logic = node.kind == LOGIC_KIND
            has_construct = node.control_construct is not None
            if is_logic != has_construct:
                raise ConstructKindMismatch(
                    f"node {node.node_id!r} (kind={node.kind!r}, "
                    f"control_construct={node.control_construct!r}): a "
                    f"{LOGIC_KIND!r} node must declare exactly one control "
                    f"construct, and only a {LOGIC_KIND!r} node may declare one",
                    source=C20_SOURCE,
                )

    def _validate_edge_references(self) -> None:
        node_ids = {n.node_id for n in self._nodes}
        for edge in self._edges:
            if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
                raise DanglingEdgeReference(
                    f"edge {edge.edge_id!r} references a node id this graph "
                    f"does not declare (source={edge.source_node_id!r}, "
                    f"target={edge.target_node_id!r})",
                    source=C20_SOURCE,
                )

    def _validate_trigger_and_reachability(self) -> None:
        triggers = self.trigger_node_ids()
        if not triggers:
            raise NoTriggerNode(
                "a canonical workflow graph declares no trigger node, so it "
                "has no entry point",
                source=C20_SOURCE,
            )
        reachable: set[str] = set(triggers)
        frontier = list(triggers)
        while frontier:
            current = frontier.pop()
            for edge in self.outgoing(current):
                if edge.target_node_id not in reachable:
                    reachable.add(edge.target_node_id)
                    frontier.append(edge.target_node_id)
        unreachable = sorted(n.node_id for n in self._nodes if n.node_id not in reachable)
        if unreachable:
            raise UnreachableNode(
                f"node(s) {unreachable} are not reachable from any trigger "
                "node; a node that can never execute cannot be part of a "
                "canonical executable graph",
                source=C20_SOURCE,
            )


class SemverBump:
    """The three declared bump kinds. Not an enum: `execution.workflow` keeps
    no vocabulary of its own beyond these three universally-defined words.
    """

    MAJOR: Final[str] = "MAJOR"
    MINOR: Final[str] = "MINOR"
    PATCH: Final[str] = "PATCH"
    ALL: Final[frozenset[str]] = frozenset({MAJOR, MINOR, PATCH})


_SEMVER: Final[re.Pattern[str]] = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def bump_semver(previous: str | None, bump: str) -> str:
    """The next semver, given the author-declared bump kind.

    `previous is None` is the first revision, always "1.0.0" regardless of the
    declared bump - there is no prior version for MINOR or PATCH to be relative
    to. The arithmetic for every later revision is never taken on the caller's
    word: MAJOR resets minor and patch to zero, MINOR resets patch to zero, and
    an unparseable `previous` is refused rather than restarted from 0.0.0
    silently, since C-20 is `STRICT` compatibility.
    """
    if bump not in SemverBump.ALL:
        raise InvalidSemverTransition(
            f"unknown semver bump {bump!r}; declared bumps are "
            f"{sorted(SemverBump.ALL)}",
            source=C20_SOURCE,
        )
    if previous is None:
        return "1.0.0"
    match = _SEMVER.match(previous)
    if match is None:
        raise InvalidSemverTransition(
            f"previous semver {previous!r} is not MAJOR.MINOR.PATCH",
            source=C20_SOURCE,
        )
    major, minor, patch = (int(part) for part in match.groups())
    if bump == SemverBump.MAJOR:
        return f"{major + 1}.0.0"
    if bump == SemverBump.MINOR:
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"
