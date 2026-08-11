"""Markdown primitives shared by the handoff drift controls.

Validation tool, not application source code.

ADR-0008 decomposition. `check_handoff.py` reached the 400 logical-line budget
when the F-0047 architecture controls were added, and the seam is real: reading
a section out of a markdown document is parsing, while deciding whether the
manifest agrees with the repository is governance. This module holds the first
and knows nothing about either.

No GATE 8 exception was requested.
"""
from __future__ import annotations

import re
from typing import Any, Protocol


class DriftReport(Protocol):
    """The reporting surface a control needs, so a control never owns a verdict."""

    def check(self, name: str, claimed: Any, actual: Any) -> None: ...

    def assert_true(self, name: str, condition: bool, detail: str = "") -> None: ...


def section(text: str, heading_pattern: str) -> str:
    """The body of one `## ` section, or "" when it is absent.

    The heading is matched by ROLE rather than by number, so a section can be
    renumbered without expiring the controls that read it.
    """
    match = re.search(heading_pattern, text, re.MULTILINE)
    if match is None:
        return ""
    rest = text[match.end():]
    end = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def plain(text: str) -> str:
    """Markdown emphasis removed, so a control matches facts and not formatting.

    The arrow is normalised too: the manifest writes an orchestration path with
    U+2192 and the measurement returns a tuple, and a control that compared the
    rendering rather than the path would be about typography.
    """
    return text.replace("*", "").replace("`", "").replace("→", "->")


def first_int(text: str) -> int | None:
    """The first integer in a string, or None when it states no number."""
    found = re.search(r"\d+", text)
    return int(found.group(0)) if found else None
