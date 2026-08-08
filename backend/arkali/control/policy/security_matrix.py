"""Parser for the canonical per-tier operation matrix (SECURITY_ARCHITECTURE §2).

Owner: control.policy (Protected Core).

NO SHADOW SECURITY MODEL. `AUTHORITY_MAP.yaml` declares each operation class's
default and fixed rule; `SECURITY_ARCHITECTURE.md` §2 declares how each class
resolves *per trust tier*. Both are canonical and both are parsed - neither is
transcribed into code. A permanent reconciliation test proves the two agree on
the vocabulary and on every fixed rule, so one cannot drift from the other.

The document's tier columns are grouped (`TRUST-0/1`, `TRUST-2`, `TRUST-3/4`).
Expansion of a grouped column to its individual tiers is the only interpretation
this module performs, and it is stated here rather than left implicit.
"""

from __future__ import annotations

import pathlib
import re

from pydantic import BaseModel, ConfigDict

from arkali.control.policy.authority_source import (
    SECURITY_ARCHITECTURE_RELPATH,
    read_text,
    refuse,
)
from arkali.control.policy.operation_class import Decision

_ROW = re.compile(r"^\|\s*`(?P<name>[A-Z_]+)`\s*\|(?P<rest>.+)\|\s*$", re.M)
_HEADER = re.compile(r"^\|\s*Class\s*\|(?P<cols>.+)\|\s*$", re.M)
#: Tier column headers are grouped: `TRUST-0/1`, `TRUST-2`, `TRUST-3/4`. Every
#: digit in a TRUST column names a tier that column governs.
_TIER_DIGITS = re.compile(r"\d")
#: A cell states its decision as the first ALL-CAPS token, e.g.
#: "AUTO (scoped)" or "ASK_USER". Anything else is a parse failure.
_DECISION = re.compile(r"\b(AUTO|ASK_USER|DENY)\b")


class TierResolution(BaseModel):
    """How one operation class resolves at one trust tier."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    operation_class: str
    tier: str
    decision: Decision
    qualifier: str = ""


def _tiers_in(column: str) -> tuple[str, ...]:
    """`TRUST-0/1` -> ("TRUST-0", "TRUST-1"). Non-tier columns yield nothing."""
    if "TRUST" not in column.upper():
        return ()
    return tuple(f"TRUST-{d}" for d in _TIER_DIGITS.findall(column))


class SecurityMatrix:
    """The §2 matrix, parsed. Construct with `load`."""

    def __init__(
        self,
        resolutions: dict[tuple[str, str], TierResolution],
        fixed_rules: dict[str, str],
        source_path: str,
    ) -> None:
        self._resolutions = resolutions
        self._fixed = fixed_rules
        self.source_path = source_path

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> SecurityMatrix:
        text, source = read_text(repo_root, SECURITY_ARCHITECTURE_RELPATH)
        header = _HEADER.search(text)
        if header is None:
            raise refuse("operation-class matrix header not found", source)
        columns = [c.strip() for c in header.group("cols").split("|")]
        tier_columns = [(index, _tiers_in(c)) for index, c in enumerate(columns)]
        resolutions, fixed = cls._parse_rows(text, tier_columns, source)
        if not resolutions:
            raise refuse("operation-class matrix parsed to zero resolutions", source)
        return cls(resolutions, fixed, source)

    @staticmethod
    def _parse_rows(
        text: str, tier_columns: list[tuple[int, tuple[str, ...]]], source: str
    ) -> tuple[dict[tuple[str, str], TierResolution], dict[str, str]]:
        resolutions: dict[tuple[str, str], TierResolution] = {}
        fixed: dict[str, str] = {}
        for row in _ROW.finditer(text):
            name = row.group("name")
            cells = [c.strip() for c in row.group("rest").split("|")]
            fixed[name] = cells[-1].replace("**", "").strip() if cells else ""
            for index, tiers in tier_columns:
                if not tiers or index >= len(cells):
                    continue
                cell = cells[index]
                found = _DECISION.search(cell.replace("**", ""))
                if found is None:
                    raise refuse(
                        f"{name}: cell {cell!r} states no AUTO/ASK_USER/DENY", source
                    )
                for tier in tiers:
                    resolutions[(name, tier)] = TierResolution(
                        operation_class=name,
                        tier=tier,
                        decision=Decision(found.group(1)),
                        qualifier=cell.replace("**", "").strip(),
                    )
        return resolutions, fixed

    def operation_classes(self) -> tuple[str, ...]:
        return tuple(sorted({name for name, _ in self._resolutions}))

    def tiers(self) -> tuple[str, ...]:
        return tuple(sorted({tier for _, tier in self._resolutions}))

    def resolution(self, operation_class: str, tier: str) -> TierResolution:
        found = self._resolutions.get((operation_class, tier))
        if found is None:
            raise refuse(
                f"matrix declares no resolution for {operation_class} at {tier}",
                self.source_path,
            )
        return found

    def fixed_rule(self, operation_class: str) -> str:
        return self._fixed.get(operation_class, "")
