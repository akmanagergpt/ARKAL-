"""Static inspection of an imported project (ARK-REQ-0115, ARK-REQ-0161).

Owner: engineering.import.

NO EXECUTION, STRUCTURALLY. This module contains no `import`, `importlib`,
`exec`, `eval`, `__import__`, `subprocess` or `compile(..., mode="exec")`
of anything under the inspected root. Every byte read from the target
project is either hashed (`Path.read_bytes`) or parsed as syntax
(`ast.parse`, via the reused `PythonGraphBuilder`) — never run. `ast.parse`
does not execute module-level statements; a file whose only defect is a
runtime side effect at import time contributes only what it syntactically
declares, exactly the same property `PythonGraphBuilder`'s own docstring
already establishes for `engineering.codeintel`'s own source tree, now
exercised against an arbitrary, untrusted one.

NO PARALLEL AST PARSER. `PythonGraphBuilder` (Phase 11, C-24) already builds
symbol/import/dependency graphs from Python source alone, accepts an
arbitrary filesystem root as a plain constructor argument, and is proven
never to import or execute what it reads. Re-implementing that here would be
exactly the duplicated-authority defect this build's governance repeatedly
refuses (`docs/build/BUILD_STATE.md` "NO PARALLEL ARCHITECTURE"); this module
composes it via the declared `engineering.import -> engineering.codeintel`
sibling edge instead.

DETERMINISTIC SOURCE ADDRESSING. `source_address` is a content address over
the sorted `(relative_posix_path, sha256(bytes))` listing of every file under
the root — the same normalised-rendering-then-hash idiom `CodeGraph.address`
uses for graph facts, applied here to raw file content so two inspections of
byte-identical trees address identically regardless of filesystem
enumeration order.
"""

from __future__ import annotations

import json
import pathlib

from arkali.engineering.codeintel.graph_vocabulary import GraphVocabulary
from arkali.engineering.codeintel.python_builder import PythonGraphBuilder
from arkali.engineering.project_import.contracts import StaticInspectionReport
from arkali.engineering.project_import.errors import UnverifiedStaticInspectionError
from arkali.kernel.contracts.content_address import address_of, digest_of


class StaticInspector:
    """Statically inspects an arbitrary project directory. Never executes it."""

    def __init__(self, graph_vocabulary: GraphVocabulary) -> None:
        self._vocabulary = graph_vocabulary

    def inspect(self, root: pathlib.Path) -> StaticInspectionReport:
        if not root.is_dir():
            raise UnverifiedStaticInspectionError(
                f"import root {root} is not an existing directory; static "
                "inspection cannot proceed against a project that is not "
                "present"
            )
        files = sorted(
            path for path in root.rglob("*") if path.is_file()
        )
        listing = sorted(
            (path.relative_to(root).as_posix(), digest_of(path.read_bytes()))
            for path in files
        )
        source_address = address_of(
            json.dumps(listing, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        )
        builder = PythonGraphBuilder(self._vocabulary, root)
        graph_addresses = tuple(
            sorted((kind, builder.build(kind).address) for kind in builder.builds())
        )
        return StaticInspectionReport(
            source_address=source_address,
            graph_kinds=builder.builds(),
            graph_addresses=graph_addresses,
            file_count=len(files),
        )
