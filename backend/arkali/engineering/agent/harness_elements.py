"""The canonical harness elements, parsed from the canonical documents.

Owner: engineering.agent. Concern: `agent_task_bounding_and_context`.

WHAT THIS EXISTS TO PREVENT. `ARK-REQ-0231` requires every AI engineering task to
be bounded by "the eight harness elements". Writing those eight names into a
Python list would put a governed value in a second place, which is defect class
F-0013 — the canonical set could gain, lose or rename an element and this module
would keep enforcing yesterday's contract while reporting PASS. So the element
list appears nowhere in this file. It is parsed at call time, and the number
eight is never asserted: whatever the canonical documents declare is what a
bounded task must carry.

TWO DOCUMENTS DECLARE IT, AND BOTH ARE CANONICAL. The register assigns
`ARK-REQ-0054` to `MS §Harness` and `ARK-REQ-0231` to `BP §Harness`, so neither
may be ignored in favour of the other. They are parsed independently and
reconciled positionally; a disagreement in COUNT or in ORDER fails closed rather
than being resolved by preference.

THE NAMES COME FROM THE MASTER SPECIFICATION, AND THE REASON IS STRUCTURAL, NOT
A COIN TOSS. The two declarations differ only in abbreviation — the Build
Protocol writes `Task Spec` and `Context` where the Master Specification writes
`Task Specification` and `Context Package`. Every such pair is a word-wise
ABBREVIATION of the other, which is a property this module CHECKS rather than
assumes: at each position one name must be a refinement of the other, or the
load fails. Where they differ, the unabbreviated name is taken, because an
abbreviation carries strictly less information than what it abbreviates. No
alias table exists here — an alias table would be the same F-0013 defect wearing
a different hat.

FAILS CLOSED, AND ANTI-VACUITY IS EXPLICIT. An absent section, a section with no
element sentence, a sentence declaring fewer than two elements, a count
mismatch between the documents, or a position where neither name refines the
other are each refused. A list with nothing in it would let every later
boundedness check pass vacuously by having no element to miss (F-0016, F-0017).
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.kernel.contracts.error_base import AuthoritativeSourceError

#: Where each declaration lives. These are file LOCATIONS, not governed values:
#: the elements themselves are read out of the documents, never from here.
MASTER_SPEC_RELPATH: Final[str] = "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"
BUILD_PROTOCOL_RELPATH: Final[str] = "docs/CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md"

#: The section both documents declare the harness under.
_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^#+\s*Harness Engineering\s*$(?P<body>.*?)(?=^#+\s|\Z)", re.M | re.S
)

#: The declaration itself: a run of names joined by `+`. One separator is the
#: floor, because two elements is the fewest a boundedness rule can meaningfully
#: require; a line with no `+` at all is not a declaration and is not read as
#: one. The search is anchored to the Harness Engineering section, so a `+` line
#: elsewhere in the document cannot be mistaken for it.
_DECLARATION: Final[re.Pattern[str]] = re.compile(
    r"^(?P<line>[^\n+]+(?:\+[^\n+]+)+)\.?\s*$", re.M
)

#: Minimum a declaration must carry before it is treated as one at all.
_MINIMUM_ELEMENTS: Final[int] = 2


def _words(name: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"\W+", name.lower()) if part)


def _refines(shorter: str, longer: str) -> bool:
    """Whether `longer` is the unabbreviated form of `shorter`.

    Word-wise: `Task Spec` refines into `Task Specification`, and `Context` into
    `Context Package`. Derived from the two spellings themselves rather than
    from a table, so a document that renames an element is reconciled or refused
    on its own terms.
    """
    left, right = _words(shorter), _words(longer)
    if not left or len(left) > len(right):
        return False
    return all(
        full.startswith(part) for part, full in zip(left, right, strict=False)
    )


def slug(name: str) -> str:
    """The field identifier an element name maps onto. Mechanical, not chosen."""
    return "_".join(_words(name))


def _declaration_in(text: str, source: str) -> tuple[str, ...]:
    section = _SECTION.search(text)
    if section is None:
        raise AuthoritativeSourceError(
            "no Harness Engineering section; refusing to invent the harness "
            "elements",
            source=source,
        )
    found = _DECLARATION.search(section.group("body"))
    if found is None:
        raise AuthoritativeSourceError(
            "the Harness Engineering section declares no element sentence",
            source=source,
        )
    elements = tuple(
        part.strip().rstrip(".").strip()
        for part in found.group("line").split("+")
        if part.strip().rstrip(".").strip()
    )
    if len(elements) < _MINIMUM_ELEMENTS:
        raise AuthoritativeSourceError(
            f"the harness declaration carries {len(elements)} element(s); a "
            "boundedness rule with nothing to require would pass vacuously",
            source=source,
        )
    return elements


class HarnessElementAuthority:
    """The canonical harness elements. Construct with `load`."""

    def __init__(self, elements: tuple[str, ...], sources: tuple[str, ...]) -> None:
        self._elements = elements
        self.sources = sources

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> HarnessElementAuthority:
        declarations: list[tuple[str, ...]] = []
        sources: list[str] = []
        for relpath in (MASTER_SPEC_RELPATH, BUILD_PROTOCOL_RELPATH):
            path = repo_root / relpath
            if not path.is_file():
                raise AuthoritativeSourceError(
                    "canonical harness document not found", source=str(path)
                )
            declarations.append(
                _declaration_in(path.read_text(encoding="utf-8"), str(path))
            )
            sources.append(str(path))
        specification, protocol = declarations
        return cls(cls._reconcile(specification, protocol, sources), tuple(sources))

    @staticmethod
    def _reconcile(
        specification: tuple[str, ...],
        protocol: tuple[str, ...],
        sources: list[str],
    ) -> tuple[str, ...]:
        """One element list, or a refusal. Never a preference."""
        if len(specification) != len(protocol):
            raise AuthoritativeSourceError(
                f"the canonical documents declare {len(specification)} and "
                f"{len(protocol)} harness elements; they must agree before any "
                "task can be judged bounded",
                source=" + ".join(sources),
            )
        agreed: list[str] = []
        for index, (left, right) in enumerate(zip(specification, protocol, strict=True)):
            if _refines(right, left):
                agreed.append(left)
            elif _refines(left, right):
                agreed.append(right)
            else:
                raise AuthoritativeSourceError(
                    f"harness element {index} is declared {left!r} and {right!r}; "
                    "neither is an abbreviation of the other, so the canonical "
                    "documents disagree and no element list can be derived",
                    source=" + ".join(sources),
                )
        return tuple(agreed)

    def elements(self) -> tuple[str, ...]:
        """Every canonical element, in the order the documents declare them."""
        return self._elements

    def field_names(self) -> tuple[str, ...]:
        """The identifiers a task model must carry, one per element."""
        return tuple(slug(name) for name in self._elements)

    def __len__(self) -> int:
        return len(self._elements)
