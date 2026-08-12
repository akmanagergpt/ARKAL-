"""Build the symbol, import and dependency graphs from Python source.

Owner: engineering.codeintel. Concern: `code_graphs_and_digital_twin`.

WHAT THIS BUILDS, AND WHAT IT HONESTLY DOES NOT. `ARCHITECTURE.md` §11 specifies
six graph kinds and names Python native AST as the mechanism for this language.
This module builds the three that are derivable from Python source ALONE -
symbol, import and dependency - and builds no others. The remaining three are
not stubbed, not defaulted and not returned empty: `builds()` reports exactly
which kinds it produces, and asking for one it does not build is a refusal rather
than an empty graph, because an empty graph is indistinguishable from "nothing
found" and would report coverage this module does not have.

  - `route` and `model` require framework semantics (FastAPI decorators,
    SQLAlchemy mappings) rather than syntax, and `frontend-contract` requires
    TypeScript, which §11 assigns to a Tree-sitter adapter this build does not
    have. Reporting them as built-and-empty would be the fabricated-coverage
    failure the Master Specification forbids.

DETERMINISM IS THE POINT, NOT A SIDE EFFECT. `CONTRACT_INVENTORY.md` row 24
names rebuild determinism as C-24's verification, so this builder walks files in
sorted order and emits into a set that `CodeGraph` renders sorted. Nothing here
depends on filesystem iteration order, on `os.walk` ordering, or on the order a
caller passes paths - two builds over the same files address identically.

SYNTAX ONLY, AND SOURCES ALWAYS RECORDED. Every node and edge carries the file
it was observed in, because a derived store must be able to point back at the
authority rather than ask to be believed. Nothing here executes, imports or
resolves the code it reads: an unimportable or half-written module is parsed as
text and contributes what it syntactically declares, which is what makes the
graph rebuildable from source without side effects.
"""

from __future__ import annotations

import ast
import pathlib
from typing import Final

from arkali.engineering.codeintel.code_graph import CodeGraph, GraphEdge, GraphNode
from arkali.engineering.codeintel.errors import UnknownGraphKind
from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary

#: The graph kinds Python source alone determines. Derived from what this
#: module can honestly observe, and every entry is resolved through the
#: canonical vocabulary before use, so a name that stops being specified fails
#: here rather than silently building an unspecified graph.
_BUILDABLE: Final[tuple[str, ...]] = ("symbol", "import", "dependency")


class PythonGraphBuilder:
    """Builds the Python-derivable graphs of the canonical set."""

    def __init__(self, vocabulary: GraphVocabulary, root: pathlib.Path) -> None:
        self._vocabulary = vocabulary
        self._root = root
        #: Resolved through the vocabulary at construction, so an unspecified
        #: kind is refused before any file is read.
        self._buildable = tuple(
            vocabulary.require_graph(kind) for kind in _BUILDABLE
        )

    def builds(self) -> tuple[str, ...]:
        """Exactly the kinds this builder produces. Never the whole set."""
        return self._buildable

    def unbuilt(self) -> tuple[str, ...]:
        """Specified kinds this builder does NOT produce, stated honestly."""
        return tuple(
            kind for kind in self._vocabulary.graph_ids()
            if kind not in self._buildable
        )

    def _files(self) -> tuple[pathlib.Path, ...]:
        """Every Python file under the root, in sorted order.

        Sorted because rebuild determinism must not depend on how the
        filesystem happens to enumerate a directory.
        """
        return tuple(sorted(self._root.rglob("*.py")))

    def _relative(self, path: pathlib.Path) -> str:
        return path.relative_to(self._root).as_posix()

    def build(self, kind: str) -> CodeGraph:
        """Build one graph, or refuse if this builder does not produce it."""
        identifier = self._vocabulary.require_graph(kind)
        if identifier not in self._buildable:
            raise UnknownGraphKind(
                f"{kind!r} is specified by the canonical architecture but this "
                f"builder does not produce it; it builds {list(self._buildable)} "
                "from Python source alone. An empty graph would be "
                "indistinguishable from 'nothing found' and would report "
                "coverage this builder does not have",
                source=self._vocabulary.source,
            )
        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []
        for path in self._files():
            where = self._relative(path)
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if identifier == "symbol":
                nodes.extend(self._symbols(tree, where))
            elif identifier == "import":
                found = self._imports(tree, where)
                nodes.append(GraphNode(identifier=where, source=where))
                edges.extend(found)
            else:
                edges.extend(self._dependencies(tree, where))
                nodes.append(GraphNode(identifier=where, source=where))
        return CodeGraph.build(
            self._vocabulary, identifier, nodes=nodes, edges=edges
        )

    @staticmethod
    def _symbols(tree: ast.Module, where: str) -> list[GraphNode]:
        """Every top-level class and function this file declares."""
        found: list[GraphNode] = []
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                found.append(GraphNode(identifier=f"{where}::{node.name}", source=where))
        return found

    @staticmethod
    def _imported_names(tree: ast.Module) -> list[str]:
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
        return names

    @classmethod
    def _imports(cls, tree: ast.Module, where: str) -> list[GraphEdge]:
        """One edge per imported module name, as written."""
        return [
            GraphEdge(origin=where, target=name, source=where)
            for name in cls._imported_names(tree)
        ]

    @classmethod
    def _dependencies(cls, tree: ast.Module, where: str) -> list[GraphEdge]:
        """One edge per distinct top-level package this file depends on.

        The dependency graph is coarser than the import graph on purpose: it
        answers "what does this file rely on" rather than "what did it write",
        so `a.b.c` and `a.b.d` collapse to `a`. They are separate canonical
        kinds and are built separately rather than one being derived from the
        other at query time.
        """
        return [
            GraphEdge(origin=where, target=name.split(".")[0], source=where)
            for name in cls._imported_names(tree)
        ]
