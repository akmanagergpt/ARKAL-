"""The canonical C-21 worker vocabulary, parsed.

Owner: `execution.scheduler`.

NO SHADOW MODEL. This module contains no worker-class name and no declaration
dimension of its own. Both lists are parsed from
`docs/canonical/EXECUTION_AND_CAPABILITY.md` §4 at call time, so the canonical
document alone decides what a worker class is and what a worker declares. A
private copy here would be the F-0013 defect applied to allocation, and it is
the same rule `operation_class.py` and `isolation_contract.py` already follow.

WHY PROSE IS PARSED RATHER THAN A YAML SECTION. `AUTHORITY_MAP.yaml` declares no
worker section, and inventing one would move canonical authority to make parsing
convenient. §4 is where the canonical set states these lists, so §4 is what is
read. The parse fails closed: a missing section, a missing list or an empty list
raises rather than yielding a permissive default.

CANONICAL SPELLING IS PRESERVED EXACTLY. `build/test`, `local-AI` and
`computer-use` are returned as written. Nothing here normalises case, separators
or word order, because a normalised copy is a second vocabulary that agrees with
the first only until one of them changes.
"""

from __future__ import annotations

import pathlib
import re
from typing import Final

from arkali.execution.scheduler.errors import (
    CanonicalWorkerSourceError,
    UnknownWorkerClass,
)

EXECUTION_RELPATH: Final[str] = "docs/canonical/EXECUTION_AND_CAPABILITY.md"

#: The §4 heading that owns worker allocation. Located by heading rather than by
#: section number so a renumbering is visible as a refusal, not a silent miss.
SECTION_HEADING: Final[str] = "Worker / resource scheduler architecture"

#: Both lists are stated as `<lead-in>: a, b, c.` sentences.
_CLASSES: Final[re.Pattern[str]] = re.compile(r"Worker classes:\s*([^.]+)\.")
_DIMENSIONS: Final[re.Pattern[str]] = re.compile(r"Each worker declares:\s*([^.]+)\.")


def _items(match: re.Match[str] | None, what: str, source: str) -> tuple[str, ...]:
    if match is None:
        raise CanonicalWorkerSourceError(
            f"section {SECTION_HEADING!r} states no {what}; the canonical list "
            "is never assumed",
            source=source,
        )
    found = tuple(part.strip() for part in match.group(1).split(",") if part.strip())
    if not found:
        raise CanonicalWorkerSourceError(
            f"section {SECTION_HEADING!r} states an empty {what} list", source=source
        )
    duplicated = sorted({item for item in found if found.count(item) > 1})
    if duplicated:
        raise CanonicalWorkerSourceError(
            f"canonical {what} list repeats {duplicated}", source=source
        )
    return found


class WorkerVocabulary:
    """The canonical worker classes and declaration dimensions. Use `load`."""

    def __init__(
        self, classes: tuple[str, ...], dimensions: tuple[str, ...], source: str
    ) -> None:
        self._classes = classes
        self._dimensions = dimensions
        self.source_path = source

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> WorkerVocabulary:
        path = repo_root / EXECUTION_RELPATH
        if not path.is_file():
            raise CanonicalWorkerSourceError(
                "canonical execution document not found", source=str(path)
            )
        text = path.read_text(encoding="utf-8")
        source = str(path)
        if SECTION_HEADING not in text:
            raise CanonicalWorkerSourceError(
                f"canonical document declares no {SECTION_HEADING!r} section",
                source=source,
            )
        section = text.split(SECTION_HEADING, 1)[1].split("\n## ", 1)[0]
        return cls(
            _items(_CLASSES.search(section), "worker class", source),
            _items(_DIMENSIONS.search(section), "declaration dimension", source),
            source,
        )

    def classes(self) -> tuple[str, ...]:
        """Canonical worker classes, in the order the canonical set states them."""
        return self._classes

    def dimensions(self) -> tuple[str, ...]:
        """Canonical declaration dimensions, in canonical order."""
        return self._dimensions

    def require_class(self, name: str) -> str:
        """The canonical class, or a refusal. A class is never inferred.

        Raises the contract type rather than an authority-source error: an
        unknown class means the *declaration* is wrong, not that the canonical
        document is unreadable, and a negative control must be able to tell
        those two failures apart.
        """
        if name not in self._classes:
            raise UnknownWorkerClass(
                f"unknown worker class {name!r}; the canonical classes are "
                f"{list(self._classes)}",
                source=self.source_path,
            )
        return name
