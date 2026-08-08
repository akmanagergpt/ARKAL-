"""Parsers for authoritative governance state.

Owner: acceptance.engine (Protected Core).

NO SHADOW MODEL: phase status, prerequisites, human-gate records and open
findings are all parsed from the accepted artifacts at call time. Nothing here
stores a second copy of governed data, and nothing here repairs it - malformed
state raises so the checker can fail closed.
"""

from __future__ import annotations

import pathlib
import re

from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.errors import AuthoritativeSourceError
from arkali.kernel.contracts.results import Severity

BUILD_STATE = "docs/build/BUILD_STATE.md"
HUMAN_GATES = "docs/acceptance/HUMAN_GATE_RECORDS.md"
OPEN_BLOCKERS = "docs/build/OPEN_BLOCKERS.md"
DEPENDENCY_MATRIX = "docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md"

_PHASE_ROW = re.compile(r"^\|\s*([0-9]{1,2}[AB]?)\s*\|([^|]*)\|([^|]*)\|", re.M)
_MATRIX_ROW = re.compile(
    r"^\|\s*\**([0-9]{1,2}[AB]?)\**\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", re.M
)
_GATE_IN_CELL = re.compile(r"GATE\s*(\d+)", re.I)
_GATE_DECISION = re.compile(
    r"\|\s*\*\*Decision\*\*\s*\|\s*\*\*(?P<decision>[A-Z_]+)\*\*\s*\|"
)
_ACCEPTED_GATE = re.compile(r"##\s+HGR-\d+\s+—\s+HUMAN GATE (?P<gate>\d+)")


def _read(repo_root: pathlib.Path, relpath: str) -> str:
    path = repo_root / relpath
    if not path.is_file():
        raise AuthoritativeSourceError("governance artifact missing", source=relpath)
    return path.read_text(encoding="utf-8")


class PhaseStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase_id: str
    title: str
    status_text: str

    @property
    def is_accepted(self) -> bool:
        upper = self.status_text.upper()
        return "ACCEPTED" in upper and "NOT ACCEPTED" not in upper

    @property
    def is_locked(self) -> bool:
        return "LOCKED" in self.status_text.upper()


class GovernanceState:
    """Parsed governance state. Construct with `load`."""

    def __init__(
        self,
        phases: dict[str, PhaseStatus],
        prerequisites: dict[str, tuple[str, ...]],
        phase_gates: dict[str, str],
        accepted_human_gates: frozenset[str],
        open_stopping_findings: tuple[str, ...],
    ) -> None:
        self.phases = phases
        self.prerequisites = prerequisites
        self.phase_gates = phase_gates
        self.accepted_human_gates = accepted_human_gates
        self.open_stopping_findings = open_stopping_findings

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> GovernanceState:
        matrix = _read(repo_root, DEPENDENCY_MATRIX)
        phases = cls._parse_phases(_read(repo_root, BUILD_STATE))
        prereqs = cls._parse_prerequisites(matrix)
        phase_gates = cls._parse_phase_gates(matrix)
        gates = cls._parse_human_gates(_read(repo_root, HUMAN_GATES))
        findings = cls._parse_open_findings(_read(repo_root, OPEN_BLOCKERS))
        if not phases:
            raise AuthoritativeSourceError(
                "no phase status rows parsed", source=BUILD_STATE
            )
        if not phase_gates:
            raise AuthoritativeSourceError(
                "no phase-to-human-gate mapping parsed", source=DEPENDENCY_MATRIX
            )
        return cls(phases, prereqs, phase_gates, gates, findings)

    @staticmethod
    def _parse_phase_gates(text: str) -> dict[str, str]:
        """Phase -> HUMAN_GATE_n, parsed from the matrix Gate column.

        Never hard-coded: which phase carries which gate is governed data.
        """
        mapping: dict[str, str] = {}
        for match in _MATRIX_ROW.finditer(text):
            gate_cell = match.group(5)
            found = _GATE_IN_CELL.search(gate_cell)
            if found:
                mapping[match.group(1)] = f"HUMAN_GATE_{found.group(1)}"
        return mapping

    @staticmethod
    def _parse_phases(text: str) -> dict[str, PhaseStatus]:
        section = text.split("## Phase status")[1].split("\n## ")[0] \
            if "## Phase status" in text else ""
        found: dict[str, PhaseStatus] = {}
        for match in _PHASE_ROW.finditer(section):
            phase_id = match.group(1)
            found[phase_id] = PhaseStatus(
                phase_id=phase_id,
                title=match.group(2).strip(),
                status_text=match.group(3).strip(),
            )
        return found

    @staticmethod
    def _parse_prerequisites(text: str) -> dict[str, tuple[str, ...]]:
        prereqs: dict[str, tuple[str, ...]] = {}
        for match in _MATRIX_ROW.finditer(text):
            phase_id = match.group(1)
            cell = match.group(3).replace("*", "")
            cell = re.sub(r"GATE\s*\d+", " ", cell, flags=re.I)
            deps = tuple(sorted(set(re.findall(r"\b(\d{1,2}[AB]?)\b", cell))))
            prereqs[phase_id] = deps
        return prereqs

    @staticmethod
    def _parse_human_gates(text: str) -> frozenset[str]:
        """Gates with a recorded ACCEPTED decision. Never inferred."""
        accepted: set[str] = set()
        for block in text.split("\n## ")[1:]:
            header = _ACCEPTED_GATE.search("## " + block)
            decision = _GATE_DECISION.search(block)
            if header and decision and decision.group("decision") == "ACCEPTED":
                accepted.add(f"HUMAN_GATE_{header.group('gate')}")
        return frozenset(accepted)

    #: Markdown table header/separator cells that are never finding ids.
    _NON_ROW_IDS = frozenset({"ID", "FINDING", "BLOCKER", ""})

    @staticmethod
    def _parse_open_findings(text: str) -> tuple[str, ...]:
        """Open BLOCKER/HIGH rows. Struck-through (~~) or CLOSED rows are excluded.

        Header and separator rows are skipped explicitly: a header cell reading
        "Blocker" would otherwise be counted as an open finding.
        """
        open_rows: list[str] = []
        for line in text.splitlines():
            if not line.startswith("|") or "~~" in line:
                continue
            upper = line.upper()
            if "CLOSED" in upper:
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not cells:
                continue
            identifier = cells[0].replace("*", "").strip()
            if identifier.upper() in GovernanceState._NON_ROW_IDS:
                continue
            if set(identifier) <= {"-", ":"}:
                continue
            if any(sev.value in upper for sev in (Severity.BLOCKER, Severity.HIGH)):
                open_rows.append(identifier)
        return tuple(sorted(set(open_rows)))

    def phase(self, phase_id: str) -> PhaseStatus:
        status = self.phases.get(phase_id)
        if status is None:
            raise AuthoritativeSourceError(
                f"phase {phase_id!r} has no status row", source=BUILD_STATE
            )
        return status

    def prerequisites_of(self, phase_id: str) -> tuple[str, ...]:
        if phase_id not in self.prerequisites:
            raise AuthoritativeSourceError(
                f"phase {phase_id!r} absent from the dependency matrix",
                source=DEPENDENCY_MATRIX,
            )
        return self.prerequisites[phase_id]
