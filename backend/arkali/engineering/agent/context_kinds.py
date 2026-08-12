"""The kinds of context that may be sent, parsed from the canonical document.

Owner: engineering.agent. Concern: `agent_task_bounding_and_context`.

WHAT "ONLY RELEVANT CONTEXT" MEANS, MECHANICALLY. `MS §Context Compiler` is one
sentence: "ARKALI sends only relevant files, symbols, contracts, tests, ADRs,
failures and verified knowledge to a model. Context provenance is recorded."
That sentence enumerates the admissible KINDS, and `ARK-REQ-0055` makes sending
only those a MANDATORY requirement. So "relevant" is not a judgement this module
makes — it is a closed vocabulary the canonical document declares, and anything
outside it is refused.

THE VOCABULARY APPEARS NOWHERE IN THIS FILE. Same rule, and same reason, as
`harness_elements.py`: writing the kinds into a Python tuple would put a governed
value in a second place (F-0013), and the canonical set could gain or rename a
kind while this module kept enforcing yesterday's list and reporting PASS. The
sentence is parsed at call time and the count is never asserted.

FAILS CLOSED, AND ANTI-VACUITY IS EXPLICIT. An absent section, a section with no
enumeration, or an enumeration of fewer than two kinds are each refused. A kind
list with nothing in it would make "only relevant context" unfalsifiable — every
package would trivially satisfy it by having no kind that could be wrong
(F-0016, F-0017).

THIS MODULE JUDGES RELEVANCE, NOT SENSITIVITY. Whether a payload may be sent at
all is `control.policy`'s question, and C-09's `assert_no_raw_secret` is the
boundary that answers it. Nothing here re-implements that check.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.kernel.contracts.error_base import AuthoritativeSourceError

MASTER_SPEC_RELPATH: Final[str] = "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"

_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^#+\s*Context Compiler\s*$(?P<body>.*?)(?=^#+\s|\Z)", re.M | re.S
)

#: The enumeration itself: what follows "sends only relevant" up to "to a model".
#: Anchored to the canonical verb phrase rather than to a comma-list anywhere in
#: the section, so ordinary prose cannot be mistaken for the vocabulary.
_ENUMERATION: Final[re.Pattern[str]] = re.compile(
    r"sends\s+only\s+relevant\s+(?P<list>.+?)\s+to\s+a\s+model", re.I | re.S
)

_MINIMUM_KINDS: Final[int] = 2


def _split(enumeration: str) -> tuple[str, ...]:
    """`a, b, c and d` -> the four names, in declaration order."""
    parts = [
        piece.strip()
        for chunk in enumeration.split(",")
        for piece in re.split(r"\band\b", chunk)
    ]
    return tuple(part for part in parts if part)


def slug(name: str) -> str:
    """The identifier a kind name maps onto. Mechanical, not chosen."""
    return "_".join(part for part in re.split(r"\W+", name.lower()) if part)


class ContextKindAuthority:
    """The canonical admissible context kinds. Construct with `load`."""

    def __init__(self, kinds: tuple[str, ...], source: str) -> None:
        self._kinds = kinds
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> ContextKindAuthority:
        path = repo_root / MASTER_SPEC_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError(
                "canonical context document not found", source=str(path)
            )
        section = _SECTION.search(path.read_text(encoding="utf-8"))
        if section is None:
            raise AuthoritativeSourceError(
                "no Context Compiler section; refusing to invent the admissible "
                "context kinds",
                source=str(path),
            )
        found = _ENUMERATION.search(section.group("body"))
        if found is None:
            raise AuthoritativeSourceError(
                "the Context Compiler section enumerates no context kinds",
                source=str(path),
            )
        kinds = _split(found.group("list"))
        if len(kinds) < _MINIMUM_KINDS:
            raise AuthoritativeSourceError(
                f"the Context Compiler declares {len(kinds)} kind(s); a "
                "relevance rule with nothing to exclude would pass vacuously",
                source=str(path),
            )
        return cls(kinds, str(path))

    def kinds(self) -> tuple[str, ...]:
        """Every admissible kind, in the order the document declares them."""
        return self._kinds

    def identifiers(self) -> tuple[str, ...]:
        """The slug form a context item declares its kind as."""
        return tuple(slug(name) for name in self._kinds)

    def admits(self, kind: str) -> bool:
        """Whether this kind may be sent at all. Closed vocabulary."""
        return slug(kind) in self.identifiers()

    def __len__(self) -> int:
        return len(self._kinds)
