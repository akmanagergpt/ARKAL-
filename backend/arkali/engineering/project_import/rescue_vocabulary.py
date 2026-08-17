"""The canonical rescue-mode vocabulary, parsed from the Master Specification.

Owner: engineering.import. Concern: `imported_project_lifecycle`.

WHAT THIS EXISTS TO PREVENT. `ARK-REQ-0162` requires "three rescue modes
supported". Writing `("repair_in_place", "controlled_modernization",
"clean_rebuild_with_migration")` into a Python tuple would put the governed
list in a second place — the exact defect class (F-0013) `GraphVocabulary`'s
own docstring warns against — and the canonical document could rename or
extend the set while this module kept enforcing yesterday's list. `MS §Import
/ Rescue / Research / Plugins` declares the set in one sentence:

    Rescue modes: Repair in Place, Controlled Modernization, Clean Rebuild
    with Migration.

so the list is parsed from that sentence at call time, the same idiom
`engineering.codeintel.graph_vocabulary.GraphVocabulary` already established
for a specification-referenced set.

THE NUMBER THREE IS NEVER ASSERTED HERE. `ARK-REQ-0162` says "three", but the
count lives in the register's requirement text, not in this module: whatever
the Master Specification declares is what a caller must support. A control
proves the count follows the document by parsing declarations of several
sizes, so a canonical set that grows to four moves this vocabulary instead of
silently under- or over-enforcing it.

FAILS CLOSED. An absent section, a section carrying no `Rescue modes:`
clause, or a clause with fewer than two entries is refused — a specified set
with nothing to exclude would pass vacuously.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.engineering.project_import.errors import UnknownRescueMode
from arkali.kernel.contracts.error_base import AuthoritativeSourceError

MASTER_SPECIFICATION_RELPATH: Final[str] = (
    "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"
)

#: Bounded by the next `## ` heading, so a sentence in a later section cannot
#: be read as part of this declaration.
_SECTION: Final[re.Pattern[str]] = re.compile(
    r"^##\s*Import\s*/\s*Rescue\s*/\s*Research\s*/\s*Plugins\s*$"
    r"(?P<body>.*?)(?=^##\s|\Z)",
    re.M | re.S,
)

#: `Rescue modes: <list>.` — the closed vocabulary.
_RESCUE_CLAUSE: Final[re.Pattern[str]] = re.compile(
    r"Rescue modes:\s*(?P<list>.+?)\.", re.I | re.S
)

_MINIMUM_ENTRIES: Final[int] = 2


def _split(enumeration: str) -> tuple[str, ...]:
    """`a, b and c` -> the names, in declaration order."""
    parts = [
        piece.strip().strip("`*")
        for chunk in enumeration.split(",")
        for piece in re.split(r"\band\b", chunk)
    ]
    return tuple(part for part in parts if part)


def slug(name: str) -> str:
    """The identifier a rescue-mode name maps onto. Mechanical, not chosen."""
    words = [part for part in re.split(r"\W+", name.lower()) if part]
    return "_".join(words)


class RescueModeVocabulary:
    """The canonical rescue-mode set. Construct with `load`."""

    def __init__(self, modes: tuple[str, ...], source: str) -> None:
        self._modes = modes
        self.source = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> RescueModeVocabulary:
        path = repo_root / MASTER_SPECIFICATION_RELPATH
        if not path.is_file():
            raise AuthoritativeSourceError(
                "canonical master specification not found", source=str(path)
            )
        section = _SECTION.search(path.read_text(encoding="utf-8"))
        if section is None:
            raise AuthoritativeSourceError(
                "no Import / Rescue / Research / Plugins section; refusing "
                "to invent the rescue-mode set",
                source=str(path),
            )
        found = _RESCUE_CLAUSE.search(section.group("body"))
        if found is None:
            raise AuthoritativeSourceError(
                "the Import section declares no 'Rescue modes:' clause",
                source=str(path),
            )
        entries = _split(found.group("list"))
        if len(entries) < _MINIMUM_ENTRIES:
            raise AuthoritativeSourceError(
                f"the canonical rescue-mode set carries {len(entries)} "
                "entr(y/ies); a specified set with nothing to exclude would "
                "pass vacuously",
                source=str(path),
            )
        return cls(entries, str(path))

    def modes(self) -> tuple[str, ...]:
        """Every rescue mode, in the order the document declares them."""
        return self._modes

    def mode_ids(self) -> tuple[str, ...]:
        return tuple(slug(name) for name in self._modes)

    def require_mode(self, mode: str) -> str:
        """The canonical identifier for a rescue mode, or a refusal."""
        identifier = slug(mode)
        if identifier not in self.mode_ids():
            raise UnknownRescueMode(
                f"{mode!r} is not a canonical rescue mode; {self.source} "
                f"specifies {list(self._modes)}",
                source=self.source,
            )
        return identifier


__all__ = ["RescueModeVocabulary", "UnknownRescueMode", "slug"]
