"""The canonical C-20 node-kind and control-construct vocabulary, parsed.

Owner: `execution.workflow`.

NO SHADOW MODEL. This module contains no node kind and no control construct of
its own. Both lists are parsed from
`docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md` §"Workflow Studio
execution identity" at call time, so the canonical document alone decides what a
node kind or a control construct is - the same rule `worker_vocabulary.py`
(`execution.scheduler`) already follows for worker classes. A private copy here
would be the F-0013 defect applied to workflow graphs.

WHY THE VDC, NOT THE MASTER SPECIFICATION. Both documents state the two lists;
the Master Specification states them as prose fragments ("Nodes include
triggers, AI, agents, ... Supports IF/ELSE/SWITCH/...") with no single
machine-stable delimiter, while the VDC states both lists as one em-dash
delimited, comma-separated enumeration purpose-built for exactly this
requirement (ARK-REQ-0329: "execution evidence for every node type and control
construct"). Parsing the VDC's enumeration is parsing the requirement's own
denominator, not a second restating of it.

The parse fails closed: a missing section or an empty/malformed list raises
rather than yielding a permissive default.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.execution.workflow.errors import (
    CanonicalWorkflowSourceError,
    UnknownControlConstruct,
    UnknownNodeKind,
)

VDC_RELPATH: Final[str] = "docs/ARKALI_GENESIS_V2_VERIFICATION_AND_DELIVERY_CONTRACT.md"

#: The section that states both canonical lists. Located by heading rather than
#: by section number so a renumbering is visible as a refusal, not a silent miss.
SECTION_HEADING: Final[str] = "Workflow Studio execution identity"

_NODE_KINDS: Final[re.Pattern[str]] = re.compile(
    r"canonical node type\s*[—-]\s*([^—]+?)\s*[—-]"
)
_CONSTRUCTS: Final[re.Pattern[str]] = re.compile(
    r"control construct\s*[—-]\s*([^—]+?)\s*[—-]"
)

#: The one node kind that governs branching; only this kind may declare a
#: control construct (ARK-ERR-0119 / `ConstructKindMismatch`).
LOGIC_KIND: Final[str] = "logic"

#: The one node kind every graph needs at least one of, to have an entry point.
TRIGGER_KIND: Final[str] = "trigger"


def _items(match: re.Match[str] | None, what: str, source: str) -> tuple[str, ...]:
    if match is None:
        raise CanonicalWorkflowSourceError(
            f"section {SECTION_HEADING!r} states no {what}; the canonical list "
            "is never assumed",
            source=source,
        )
    found = tuple(part.strip() for part in match.group(1).split(",") if part.strip())
    if not found:
        raise CanonicalWorkflowSourceError(
            f"section {SECTION_HEADING!r} states an empty {what} list", source=source
        )
    duplicated = sorted({item for item in found if found.count(item) > 1})
    if duplicated:
        raise CanonicalWorkflowSourceError(
            f"canonical {what} list repeats {duplicated}", source=source
        )
    return found


class GraphVocabulary:
    """The canonical node kinds and control constructs. Use `load`."""

    def __init__(
        self, node_kinds: tuple[str, ...], constructs: tuple[str, ...], source: str
    ) -> None:
        self._node_kinds = node_kinds
        self._constructs = constructs
        self.source_path = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> GraphVocabulary:
        path = repo_root / VDC_RELPATH
        if not path.is_file():
            raise CanonicalWorkflowSourceError(
                "canonical VDC document not found", source=str(path)
            )
        text = path.read_text(encoding="utf-8")
        source = str(path)
        if SECTION_HEADING not in text:
            raise CanonicalWorkflowSourceError(
                f"canonical document declares no {SECTION_HEADING!r} section",
                source=source,
            )
        section = text.split(SECTION_HEADING, 1)[1].split("\n## ", 1)[0]
        node_kinds = _items(_NODE_KINDS.search(section), "node type", source)
        constructs = _items(_CONSTRUCTS.search(section), "control construct", source)
        if TRIGGER_KIND not in node_kinds:
            raise CanonicalWorkflowSourceError(
                f"canonical node type list does not include {TRIGGER_KIND!r}, "
                "which a graph needs for an entry point",
                source=source,
            )
        if LOGIC_KIND not in node_kinds:
            raise CanonicalWorkflowSourceError(
                f"canonical node type list does not include {LOGIC_KIND!r}, "
                "which owns every control construct",
                source=source,
            )
        return cls(node_kinds, constructs, source)

    def node_kinds(self) -> tuple[str, ...]:
        """Canonical node kinds, in the order the VDC states them."""
        return self._node_kinds

    def control_constructs(self) -> tuple[str, ...]:
        """Canonical control constructs, in the order the VDC states them."""
        return self._constructs

    def require_node_kind(self, name: str) -> str:
        if name not in self._node_kinds:
            raise UnknownNodeKind(
                f"unknown node kind {name!r}; the canonical kinds are "
                f"{list(self._node_kinds)}",
                source=self.source_path,
            )
        return name

    def require_control_construct(self, name: str) -> str:
        if name not in self._constructs:
            raise UnknownControlConstruct(
                f"unknown control construct {name!r}; the canonical constructs "
                f"are {list(self._constructs)}",
                source=self.source_path,
            )
        return name
