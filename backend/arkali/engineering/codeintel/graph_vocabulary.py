"""The canonical graph set and Digital Twin views, parsed from ARCHITECTURE.md.

Owner: engineering.codeintel. Concern: `code_graphs_and_digital_twin`.

WHAT THIS EXISTS TO PREVENT. `ARK-REQ-0066` requires Code Intelligence to
maintain "the specified graph set" and `ARK-REQ-0067` requires the Digital Twin
to compose "the nine specified views". Both requirements are phrased as
references to a specification rather than as lists, so the lists belong in the
specification and nowhere else. Writing either into a Python tuple would put a
governed value in a second place - defect class F-0013 - and the canonical
architecture could gain, lose or rename a graph while this module kept enforcing
yesterday's set and reporting PASS.

`ARCHITECTURE.md` §11 declares both in one paragraph:

    `engineering.codeintel` maintains symbol, import, dependency, route, model
    and frontend-contract graphs for Python (native AST) and other languages
    (Tree-sitter adapters). The Digital Twin composes: specification view,
    architecture view, code graph, data graph, runtime graph, deployment graph,
    test view, version view, failure view. It is a **derived** store - never an
    authority - and is rebuildable from source plus the owning authorities.

THE NUMBER NINE IS NEVER ASSERTED HERE. `ARK-REQ-0067` says "the nine specified
views", but the nine lives in the register's requirement text, not in this
module: whatever §11 declares is what the twin must compose. A control proves the
count follows the document by parsing declarations of several sizes, so a
canonical set that adds a tenth view moves this vocabulary instead of expiring
it. The register and the architecture agreeing on nine is a fact this module
lets a caller CHECK, not one it hard-codes.

FAILS CLOSED, AND ANTI-VACUITY IS EXPLICIT. An absent section, a paragraph with
no graph clause, a paragraph with no view clause, or either list carrying fewer
than two entries is refused. A vocabulary with nothing in it would make "the
specified graph set" unfalsifiable - every store would satisfy it by having no
kind that could be wrong (F-0016, F-0017).

THIS MODULE DESCRIBES; IT DOES NOT BUILD. Constructing a graph is a later
package's, and nothing here reads source code, walks an AST or touches a
repository other than the canonical document it parses.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.engineering.codeintel.errors import UnknownGraphKind, UnknownTwinView
from arkali.kernel.contracts.error_base import AuthoritativeSourceError

ARCHITECTURE_RELPATH: Final[str] = "docs/canonical/ARCHITECTURE.md"

#: The section that declares both vocabularies. Bounded by the next heading so a
#: sentence in a later section cannot be read as part of this declaration.
_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^##\s*\d+\.\s*Code Intelligence\s*/\s*Digital Twin architecture\s*$"
    r"(?P<body>.*?)(?=^##\s|\Z)",
    re.M | re.S,
)

#: `maintains <list> graphs for` - the graph set.
_GRAPH_CLAUSE: Final[re.Pattern[str]] = re.compile(
    r"maintains\s+(?P<list>.+?)\s+graphs\s+for", re.I | re.S
)

#: `The Digital Twin composes: <list>.` - the view set.
_VIEW_CLAUSE: Final[re.Pattern[str]] = re.compile(
    r"Digital Twin composes:\s*(?P<list>.+?)\.", re.I | re.S
)

_MINIMUM_ENTRIES: Final[int] = 2


def _split(enumeration: str) -> tuple[str, ...]:
    """`a, b, c and d` -> the four names, in declaration order."""
    parts = [
        piece.strip().strip("`*")
        for chunk in enumeration.split(",")
        for piece in re.split(r"\band\b", chunk)
    ]
    return tuple(part for part in parts if part)


def slug(name: str) -> str:
    """The identifier a name maps onto. Mechanical, not chosen.

    The trailing noun the document uses for presentation (`view`, `graph`) is
    not part of the identity: §11 writes `test view` and `code graph` in the same
    list, and treating those suffixes as meaningful would make the vocabulary
    depend on prose style rather than on what is declared.
    """
    words = [part for part in re.split(r"\W+", name.lower()) if part]
    while len(words) > 1 and words[-1] in {"view", "graph", "graphs", "views"}:
        words.pop()
    return "_".join(words)


def _clause(body: str, pattern: re.Pattern[str], what: str, source: str) -> tuple[str, ...]:
    found = pattern.search(body)
    if found is None:
        raise AuthoritativeSourceError(
            f"the Code Intelligence section declares no {what}; refusing to "
            "invent it",
            source=source,
        )
    entries = _split(found.group("list"))
    if len(entries) < _MINIMUM_ENTRIES:
        raise AuthoritativeSourceError(
            f"the canonical {what} carries {len(entries)} entr(y/ies); a "
            "specified set with nothing to exclude would pass vacuously",
            source=source,
        )
    return entries


class GraphVocabulary:
    """The canonical graph set and Digital Twin view set. Construct with `load`."""

    def __init__(
        self, graphs: tuple[str, ...], views: tuple[str, ...], source: str
    ) -> None:
        self._graphs = graphs
        self._views = views
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> GraphVocabulary:
        path = repo_root / ARCHITECTURE_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError(
                "canonical architecture document not found", source=str(path)
            )
        section = _SECTION.search(path.read_text(encoding="utf-8"))
        if section is None:
            raise AuthoritativeSourceError(
                "no Code Intelligence / Digital Twin architecture section; "
                "refusing to invent the graph set or the view set",
                source=str(path),
            )
        body = section.group("body")
        return cls(
            _clause(body, _GRAPH_CLAUSE, "graph set", str(path)),
            _clause(body, _VIEW_CLAUSE, "Digital Twin view set", str(path)),
            str(path),
        )

    def graphs(self) -> tuple[str, ...]:
        """Every graph kind, in the order the document declares them."""
        return self._graphs

    def views(self) -> tuple[str, ...]:
        """Every Digital Twin view, in the order the document declares them."""
        return self._views

    def graph_ids(self) -> tuple[str, ...]:
        return tuple(slug(name) for name in self._graphs)

    def view_ids(self) -> tuple[str, ...]:
        return tuple(slug(name) for name in self._views)

    def require_graph(self, kind: str) -> str:
        """The canonical identifier for a graph kind, or a refusal."""
        identifier = slug(kind)
        if identifier not in self.graph_ids():
            raise UnknownGraphKind(
                f"{kind!r} is not a canonical graph kind; "
                f"{self.source} specifies {list(self._graphs)}",
                source=self.source,
            )
        return identifier

    def require_view(self, view: str) -> str:
        """The canonical identifier for a twin view, or a refusal."""
        identifier = slug(view)
        if identifier not in self.view_ids():
            raise UnknownTwinView(
                f"{view!r} is not a canonical Digital Twin view; "
                f"{self.source} specifies {list(self._views)}",
                source=self.source,
            )
        return identifier
