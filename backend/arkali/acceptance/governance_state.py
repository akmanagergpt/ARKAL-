"""Parsers for authoritative governance state.

Owner: acceptance.engine (Protected Core).

NO SHADOW MODEL: phase status, prerequisites, human-gate records and open
findings are all parsed from the accepted artifacts at call time. Nothing here
stores a second copy of governed data, and nothing here repairs it - malformed
state raises so the checker can fail closed.

REFUSALS ARE BUILT BY `governance_source`, NOT HERE. This module only ever
*raises* the canonical refusal; it never catches or annotates one. Importing the
exception type directly was therefore a second edge from this context to
`kernel.contracts.errors`, whose fan-in budget is 15 and which Phase 6 pushed to
16. ADR-0008 makes decomposition the answer to a budget rather than an
exception, and the budget was pointing at something real: every module reaching
into one error module turns the kernel into a hub. The refusal factory that
already existed in this context is now the single path, exactly as
`control.registry.project` keeps one importer of the kernel taxonomy. Same
exception type, same message, same source - one fewer edge.
"""

from __future__ import annotations

import enum
import pathlib
import re

from pydantic import BaseModel, ConfigDict

from arkali.acceptance.findings import stopping_findings
from arkali.acceptance.governance_source import refuse
from arkali.acceptance.human_gate_authorization import _find_operation_gate_grant

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
        raise refuse("governance artifact missing", relpath)
    return path.read_text(encoding="utf-8")


class DeclaredPhaseState(str, enum.Enum):
    """The states a phase-status cell may declare.

    Read off the canonical vocabulary `BUILD_STATE.md` already uses; nothing here
    is invented. Every state below appears in a live row, and a cell declaring
    anything else is refused rather than guessed at.
    """

    ACCEPTED = "ACCEPTED"
    MACHINE_ACCEPTED = "MACHINE-ACCEPTED"
    UNLOCKED = "UNLOCKED"
    LOCKED = "LOCKED"
    NOT_STARTED = "NOT_STARTED"

    @property
    def grants_acceptance(self) -> bool:
        """Only an affirmative acceptance state accepts a phase.

        Deliberately a whitelist. F-0034's predecessor inferred acceptance from
        the *absence* of a negation, so every unrecognised cell that happened to
        contain the token was accepted.
        """
        return self in (DeclaredPhaseState.ACCEPTED,
                        DeclaredPhaseState.MACHINE_ACCEPTED)


#: The declared state is the LEADING segment of the cell. Bold marks it in every
#: live row (`**MACHINE-ACCEPTED** (66 tests…)`); an unbolded cell is read up to
#: the first separator instead, so the syntax already in use is understood
#: without a document rewrite.
_BOLD_HEAD = re.compile(r"^\s*\*\*(?P<head>[^*]+)\*\*")
_PLAIN_HEAD = re.compile(r"^\s*(?P<head>[^.(<←\n]+)")
#: Em dash, en dash or a double hyphen separates the state from its qualifier.
_QUALIFIER_SPLIT = re.compile(r"\s*(?:—|–|--)\s*")
#: A negation, in any spelling that has appeared in this repository.
_NEGATION = re.compile(r"\bNOT[ _-]ACCEPTED\b")
#: An acceptance token standing on its own, used only to detect contradiction.
_ACCEPTANCE_TOKEN = re.compile(r"\b(?:MACHINE-)?ACCEPTED\b")

_STATE_SPELLINGS = {
    "ACCEPTED": DeclaredPhaseState.ACCEPTED,
    "MACHINE-ACCEPTED": DeclaredPhaseState.MACHINE_ACCEPTED,
    "MACHINE ACCEPTED": DeclaredPhaseState.MACHINE_ACCEPTED,
    "UNLOCKED": DeclaredPhaseState.UNLOCKED,
    "LOCKED": DeclaredPhaseState.LOCKED,
    "NOT_STARTED": DeclaredPhaseState.NOT_STARTED,
    "NOT STARTED": DeclaredPhaseState.NOT_STARTED,
}


def _head_segment(status_text: str) -> str:
    bold = _BOLD_HEAD.match(status_text)
    if bold is not None:
        return bold.group("head").strip()
    plain = _PLAIN_HEAD.match(status_text)
    return plain.group("head").strip() if plain else ""


def parse_declared_state(
    status_text: str, phase_id: str = "?"
) -> DeclaredPhaseState:
    """The state a status cell declares. Explanatory prose has no effect.

    Closes **F-0034**. The predecessor asked whether the substring `ACCEPTED`
    appeared anywhere in the whole cell and whether `NOT ACCEPTED` did not, so
    prose decided acceptance: "Prerequisites Phases 5 and 6 are accepted" on
    Phase 7's own row accepted Phase 7, and `NOT_ACCEPTED` with an underscore
    accepted a phase that said the opposite. That is a fail-**open** in the
    acceptance path, because `checker.check_prerequisites` reads the same
    property.

    The rule now mirrors `findings.py` (F-0025): state comes only from the
    declared leading segment, everything after it is commentary, and anything
    unreadable or self-contradictory is REFUSED rather than resolved to a
    default. There is no path by which absence of a negation becomes acceptance.
    """
    head = _head_segment(status_text).upper()
    if not head:
        raise refuse(
            f"phase {phase_id!r} declares no status; a status cell must begin "
            "with a canonical state",
            source=BUILD_STATE,
        )
    parts = [part.strip() for part in _QUALIFIER_SPLIT.split(head, maxsplit=1)]
    primary_text = parts[0]
    qualifier = parts[1] if len(parts) > 1 else ""
    state = _STATE_SPELLINGS.get(primary_text)
    if state is None:
        raise refuse(
            f"phase {phase_id!r} declares the unknown state {primary_text!r}; "
            f"the canonical vocabulary is {sorted(_STATE_SPELLINGS)}",
            source=BUILD_STATE,
        )
    _refuse_contradiction(state, qualifier, phase_id)
    return state


def _refuse_contradiction(
    state: DeclaredPhaseState, qualifier: str, phase_id: str
) -> None:
    """A qualifier may narrow a state; it may never reverse it.

    `UNLOCKED — IN PROGRESS, NOT ACCEPTED` narrows and is legal. An accepting
    state carrying a negation, or a non-accepting state carrying a bare
    acceptance token, is ambiguous and fails closed - the strict side, since the
    alternative is choosing which half of a contradiction to believe.
    """
    negated = bool(_NEGATION.search(qualifier))
    if state.grants_acceptance and negated:
        raise refuse(
            f"phase {phase_id!r} declares {state.value} qualified by a negation "
            f"({qualifier!r}); a status cell may not both accept and refuse",
            source=BUILD_STATE,
        )
    if not state.grants_acceptance and _ACCEPTANCE_TOKEN.search(
        _NEGATION.sub("", qualifier)
    ):
        raise refuse(
            f"phase {phase_id!r} declares the non-accepting state {state.value} "
            f"qualified by an acceptance token ({qualifier!r})",
            source=BUILD_STATE,
        )


class PhaseStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase_id: str
    title: str
    status_text: str
    #: Parsed once, at load time, so a malformed cell stops the checker rather
    #: than being re-guessed at every call site.
    declared_state: DeclaredPhaseState

    @classmethod
    def parse(cls, phase_id: str, title: str, status_text: str) -> PhaseStatus:
        return cls(
            phase_id=phase_id,
            title=title,
            status_text=status_text,
            declared_state=parse_declared_state(status_text, phase_id),
        )

    @property
    def is_accepted(self) -> bool:
        return self.declared_state.grants_acceptance

    @property
    def is_unlocked(self) -> bool:
        """Declared UNLOCKED. Not inferred from the absence of LOCKED."""
        return self.declared_state is DeclaredPhaseState.UNLOCKED

    @property
    def is_locked(self) -> bool:
        """Declared LOCKED.

        The predecessor asked whether `LOCKED` appeared in the cell, so every
        `UNLOCKED` row reported itself locked. No caller consumed it, which is
        the only reason that never surfaced; it is corrected rather than left
        as a trap for the first caller who does.
        """
        return self.declared_state is DeclaredPhaseState.LOCKED


class GovernanceState:
    """Parsed governance state. Construct with `load`."""

    def __init__(
        self,
        phases: dict[str, PhaseStatus],
        prerequisites: dict[str, tuple[str, ...]],
        phase_gates: dict[str, str],
        accepted_human_gates: frozenset[str],
        open_stopping_findings: tuple[str, ...],
        repo_root: pathlib.Path,
    ) -> None:
        self.phases = phases
        self.prerequisites = prerequisites
        self.phase_gates = phase_gates
        self.accepted_human_gates = accepted_human_gates
        self.open_stopping_findings = open_stopping_findings
        self.repo_root = repo_root

    def operation_grant(
        self, gate_id: str, operation_class: str, target_identity: str,
        revision_identity: str,
    ) -> bool:
        """Whether a scoped human-gate grant exists for this exact operation.

        HUMAN_GATE_SCOPE_GAP remediation. Satisfies the `HumanGateSource`
        `Protocol` `lifecycle.recovery`'s migration-safety Apply step composes
        (`migration_safety_types.py`) - never an import in that direction,
        since `acceptance.engine`'s own chain into `kernel.contracts` is
        already 4 of 4. `target_identity` and `revision_identity` must already
        be mechanically derived by the caller from real facts (a backup
        content digest, a resolved migration revision); this method does not
        trust them, it only asks whether a matching recorded grant exists.
        """
        return _find_operation_gate_grant(
            self.repo_root, gate_id, operation_class, target_identity,
            revision_identity,
        ) is not None

    @classmethod
    def load(cls, repo_root: pathlib.Path) -> GovernanceState:
        matrix = _read(repo_root, DEPENDENCY_MATRIX)
        phases = cls._parse_phases(_read(repo_root, BUILD_STATE))
        prereqs = cls._parse_prerequisites(matrix)
        phase_gates = cls._parse_phase_gates(matrix)
        gates = cls._parse_human_gates(_read(repo_root, HUMAN_GATES))
        findings = cls._parse_open_findings(_read(repo_root, OPEN_BLOCKERS))
        if not phases:
            raise refuse(
                "no phase status rows parsed", source=BUILD_STATE
            )
        if not phase_gates:
            raise refuse(
                "no phase-to-human-gate mapping parsed", source=DEPENDENCY_MATRIX
            )
        return cls(phases, prereqs, phase_gates, gates, findings, repo_root)

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
            found[phase_id] = PhaseStatus.parse(
                phase_id, match.group(2).strip(), match.group(3).strip()
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

    @staticmethod
    def _parse_open_findings(text: str) -> tuple[str, ...]:
        """Findings that stop acceptance, read from declared Status cells.

        Defect F-0025: the predecessor decided closure by searching the whole
        row for the substring `CLOSED`, so a finding could be hidden by its own
        prose. State now comes only from the Status column, and a row that
        cannot be read is returned as stopping rather than skipped.

        Delegates to `arkali.acceptance.findings`, which owns the structure.
        """
        return stopping_findings(text)

    def phase(self, phase_id: str) -> PhaseStatus:
        status = self.phases.get(phase_id)
        if status is None:
            raise refuse(
                f"phase {phase_id!r} has no status row", source=BUILD_STATE
            )
        return status

    def current_work_phase(self) -> str | None:
        """The single phase declared UNLOCKED that carries no acceptance.

        One derivation, owned here, so no consumer re-implements it. `F-0029`
        established the rule; `F-0034` showed the cost of a consumer restating
        it in prose terms - `check_handoff.py` had its own
        `"UNLOCKED" in status_text` test, which a sentence on an unrelated row
        could satisfy.

        `None` when the answer is not exactly one phase, which is ambiguous and
        must be reported as drift rather than resolved by picking the first.
        """
        found = sorted(
            pid for pid, status in self.phases.items()
            if status.is_unlocked and not status.is_accepted
        )
        return found[0] if len(found) == 1 else None

    def prerequisites_of(self, phase_id: str) -> tuple[str, ...]:
        if phase_id not in self.prerequisites:
            raise refuse(
                f"phase {phase_id!r} absent from the dependency matrix",
                source=DEPENDENCY_MATRIX,
            )
        return self.prerequisites[phase_id]
