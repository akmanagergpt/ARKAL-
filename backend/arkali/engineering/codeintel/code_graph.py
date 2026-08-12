"""C-24 code graph — a derived, deterministically rebuildable store (ARK-REQ-0066).

Owner: engineering.codeintel. Concern: `code_graphs_and_digital_twin`.

WHAT `ARK-REQ-0066` ACTUALLY REQUIRES. "Code Intelligence maintains the specified
graph set." The set is specified in `ARCHITECTURE.md` §11 and parsed by
`graph_vocabulary.py`; this module holds the graph itself. A graph kind the
canonical architecture does not specify cannot be added, because
`GraphVocabulary.require_graph` refuses it before a node or edge is ever built.

C-24's DECLARED VERIFICATION IS REBUILD DETERMINISM.
`CONTRACT_INVENTORY.md` row 24 names it in as many words, so it is not a quality
we hope for but the evidence responsibility the contract carries. `address` is
computed over a fully normalised rendering with `kernel.contracts.content_address`
- the same canonical addressing C-14 and C-23 use - so two graphs built from the
same facts address identically no matter what order those facts arrived in, and
any change to any node or edge changes the address. `assert_rebuild_matches`
turns that into a refusal rather than a comparison a caller might skip.

DETERMINISM IS ACHIEVED BY NORMALISATION, NOT BY ASKING CALLERS TO BE TIDY.
Nodes and edges are stored in sets and rendered sorted, so insertion order,
duplicate insertion and dictionary iteration order cannot reach the address. A
graph that depended on any of those would be a graph whose rebuild is a coin
toss, and `ARK-REQ-0066`'s `unit` evidence would be untestable.

THE GRAPH IS A DERIVED STORE AND NEVER AN AUTHORITY. `ARCHITECTURE.md` §11:
it "is a **derived** store - never an authority - and is rebuildable from source
plus the owning authorities." So this module records WHAT IT OBSERVED and the
source it observed it from; it answers no question about whether an observation
is correct, permitted, healthy or current, because those belong to the contexts
that own them. `sources` exists precisely so a reader can go back to the
authority rather than trusting the derived copy.

NOTHING HERE PARSES PYTHON. Building nodes from an AST is the next module's
concern; this one is the store and its determinism contract, so the determinism
evidence does not depend on the correctness of a parser.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.engineering.codeintel.errors import (
    DerivedStoreTreatedAsAuthority,
    NonDeterministicRebuild,
)
from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.kernel.contracts.content_address import address_of

C24_SOURCE: Final[str] = "ARCHITECTURE.md §11 + CONTRACT_INVENTORY.md row 24 (C-24)"

Declared = Annotated[str, Field(min_length=1)]


class GraphNode(BaseModel):
    """One observed entity, and the source it was observed in."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    #: Stable identity within its graph, e.g. a dotted symbol or a module path.
    identifier: Declared
    #: Where this was observed. A derived store must always be able to point
    #: back at the authority rather than ask to be believed.
    source: Declared

    def rendering(self) -> tuple[str, str]:
        return (self.identifier, self.source)


class GraphEdge(BaseModel):
    """One observed relationship between two identifiers."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    origin: Declared
    target: Declared
    source: Declared

    def rendering(self) -> tuple[str, str, str]:
        return (self.origin, self.target, self.source)


class CodeGraph:
    """One graph of the canonical set. Build with `build`."""

    def __init__(
        self,
        kind: str,
        nodes: frozenset[GraphNode],
        edges: frozenset[GraphEdge],
    ) -> None:
        self.kind = kind
        self._nodes = nodes
        self._edges = edges

    @classmethod
    def build(
        cls,
        vocabulary: GraphVocabulary,
        kind: str,
        *,
        nodes: Iterable[GraphNode] = (),
        edges: Iterable[GraphEdge] = (),
    ) -> CodeGraph:
        """Build a graph of a kind the canonical architecture specifies.

        The kind is resolved through the vocabulary, so a graph outside the
        specified set cannot be constructed at all rather than being constructed
        and later audited.
        """
        return cls(vocabulary.require_graph(kind), frozenset(nodes), frozenset(edges))

    def nodes(self) -> tuple[GraphNode, ...]:
        """Every node, in normalised order. Never insertion order."""
        return tuple(sorted(self._nodes, key=lambda n: n.rendering()))

    def edges(self) -> tuple[GraphEdge, ...]:
        """Every edge, in normalised order. Never insertion order."""
        return tuple(sorted(self._edges, key=lambda e: e.rendering()))

    def sources(self) -> tuple[str, ...]:
        """Every distinct source this graph was derived from, sorted.

        The derived store's way of saying "do not believe me, read these".
        """
        return tuple(sorted({n.source for n in self._nodes} | {e.source for e in self._edges}))

    @property
    def address(self) -> str:
        """The canonical content address of exactly these facts.

        Order-independent by construction: the rendering is sorted, so a graph
        assembled in a different order addresses identically. That is what makes
        rebuild determinism testable rather than aspirational.
        """
        payload = json.dumps(
            {
                "kind": self.kind,
                "nodes": [list(n.rendering()) for n in self.nodes()],
                "edges": [list(e.rendering()) for e in self.edges()],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return address_of(payload.encode("utf-8"))

    def assert_rebuild_matches(self, rebuilt: CodeGraph) -> None:
        """C-24's verification, as a refusal rather than a comparison.

        A caller that merely compared addresses could forget to. This raises,
        and the error may never be caught and turned into a PASS: a rebuild that
        differs from an identical input is a contract violation, not a fact
        about the repository.
        """
        if rebuilt.kind != self.kind:
            raise NonDeterministicRebuild(
                f"rebuild produced kind {rebuilt.kind!r}, not {self.kind!r}",
                source=C24_SOURCE,
            )
        if rebuilt.address != self.address:
            raise NonDeterministicRebuild(
                f"{self.kind}: rebuild address {rebuilt.address} does not match "
                f"{self.address}; C-24's declared verification is rebuild "
                "determinism, so identical input must produce an identical graph",
                source=C24_SOURCE,
            )

    def resolve_authority(self, concern: str) -> None:
        """Always refuses. The graph is derived and never an authority.

        There is no branch in which this answers, at any kind, for any concern.
        A derived store that could be asked an authoritative question would
        become a second store of somebody else's concern the first time a caller
        found it convenient - which is exactly what `ARCHITECTURE.md` §11
        forbids and what the `shadow_registry` gate exists to catch.
        """
        raise DerivedStoreTreatedAsAuthority(
            f"the code graph is a derived store and cannot be the authority for "
            f"{concern!r}; it is rebuildable from source plus the owning "
            "authorities, and those authorities are where the answer lives",
            source=C24_SOURCE,
        )

    def __len__(self) -> int:
        return len(self._nodes)
