"""Scoped human-gate authorization (HUMAN_GATE_SCOPE_GAP remediation).

Owner: `acceptance.engine` (Protected Core).

THE DEFECT THIS CLOSES. `GovernanceState.accepted_human_gates` is a flat
`frozenset[str]` keyed only by gate ID (`governance_state.py::_parse_human_gates`,
unchanged by this module). A grant recorded for one candidate/phase/operation
therefore mechanically satisfied *any* future check of the same gate number -
proven for `HUMAN_GATE_4` by HGR-002's own "KNOWN MECHANISM GAP" note, and
proven for `HUMAN_GATE_6` by direct probe against the real PDP and the real
`step_apply` before this module existed. This module makes gate satisfaction a
function of the exact reviewed *subject*, not the gate number alone.

TWO SCOPE KINDS, NOT ONE. A phase acceptance reviews a finished, already-built
evidence package - `_PhaseGateGrant` mirrors `rescoring_authorization.
RescoringAuthorization` exactly (same digest-binding pattern, same table
discipline) because it is the identical problem GOV-001 already solved. A
runtime operation (`APPLY_MIGRATION` to real-or-stable data) authorizes an
event that does not exist yet at record-writing time; `_OperationGateGrant`
binds to the target and revision identity the operation resolves at call time,
not to a phase or a report. Collapsing these into one shape would either
under-scope the phase case or force an operation grant to pretend it has a
phase, both invented semantics this module refuses.

WHY GATE_1 AND GATE_7 ARE THE ONLY EXEMPTIONS. `IMPLEMENTATION_DEPENDENCY_
MATRIX.md` names `HUMAN_GATE_1` on exactly one row (`0B`, "PHASE 0 canonical
architecture acceptance") and `HUMAN_GATE_7` on exactly one row (`37`, "Final
Production Release") - not coincidentally, but because both gates' own
canonical descriptions in `CLAUDE_..._BUILD_PROTOCOL.md` §Canonical HUMAN
GATES name a unique, non-repeatable project event. Every other gate's
canonical description names a repeatable category ("a migration", "an
exceptional... waiver", "an exception") and is explicitly, mechanically
scoped by this module. `SINGLETON_GATES` is therefore a narrow, canon-cited
carve-out - not a general mechanism - and legacy unscoped records (HGR-001)
remain sufficient for it without migration; a scoped record is required for
everything else, including gates whose matrix row count happens to be one
today (`HUMAN_GATE_6`), because that count is not a canonical guarantee the
way gates 1 and 7's own definitions are.

REUSE, NOT DUPLICATION. Table parsing (`_tables`) and the forbidden-issuer
list are imported from `rescoring_authorization.py` rather than
re-implemented - the identical generic markdown-table reader and the identical
`stable_mutation.prohibited_actors`-derived barred-issuer set. No second table
parser, no second issuer list.

FAIL CLOSED. A row missing a required field, an unreadable status, or a
forbidden issuer all yield no grant - never a partial or best-effort match.
"""

from __future__ import annotations

import enum
import pathlib
from typing import Final

from pydantic import BaseModel, ConfigDict

from arkali.acceptance.governance_source import read_document
from arkali.acceptance.rescoring_authorization import (
    HUMAN_GATE_RECORDS,
    _tables,
    forbidden_issuers,
)

#: Gates whose own canonical description (BUILD_PROTOCOL.md §Canonical HUMAN
#: GATES, items 1 and 7) names a unique, non-repeatable project event rather
#: than a repeatable category. A legacy, gate-ID-only record remains
#: sufficient for these two and only these two - see the module docstring.
SINGLETON_GATES: Final[frozenset[str]] = frozenset({"HUMAN_GATE_1", "HUMAN_GATE_7"})


class _GrantStatus(str, enum.Enum):
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"
    #: Not declarable. Produced when a row cannot be read.
    MALFORMED = "MALFORMED"


def _status_of(raw: str) -> _GrantStatus:
    text = raw.replace("*", "").replace("`", "").replace("~", "").strip().upper()
    if text == "GRANTED":
        return _GrantStatus.GRANTED
    if text == "REVOKED":
        return _GrantStatus.REVOKED
    return _GrantStatus.MALFORMED


def _clean(cell: str) -> str:
    return cell.replace("*", "").replace("`", "").replace("~", "").strip()


class _PhaseGateGrant(BaseModel):
    """A human-gate grant scoped to one phase's exact evidence package.

    Same binding discipline as `RescoringAuthorization`: a grant for phase 19
    cannot cover phase 21, and one granted for a given evidence digest cannot
    cover a different one, because changing either report or traceability
    file changes the digest.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    gate_id: str
    phase_id: str
    evidence_digest: str
    issuer: str
    status: _GrantStatus
    basis: str = ""

    @property
    def is_granted(self) -> bool:
        return self.status is _GrantStatus.GRANTED

    def covers(self, gate_id: str, phase_id: str, digest: str) -> bool:
        return (
            self.is_granted
            and self.gate_id == gate_id
            and self.phase_id == phase_id
            and self.evidence_digest == digest
        )

    def render(self) -> str:
        return (
            f"{self.identifier} gate={self.gate_id} phase={self.phase_id} "
            f"package={self.evidence_digest[:19]} issuer={self.issuer} "
            f"{self.status.value}"
        )


class _OperationGateGrant(BaseModel):
    """A human-gate grant scoped to one exact runtime operation.

    `target_identity` and `revision_identity` are the caller's *mechanically
    derived* facts about the exact operation reviewed - for `APPLY_MIGRATION`,
    the pre-migration backup's content digest and the resolved target
    revision (`migration_safety_steps.py`). Neither is a label a caller may
    assert freely; both come from `kernel.persistence`-computed values a
    confused deputy cannot fabricate to match a stale grant.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    gate_id: str
    operation_class: str
    target_identity: str
    revision_identity: str
    issuer: str
    status: _GrantStatus
    basis: str = ""

    @property
    def is_granted(self) -> bool:
        return self.status is _GrantStatus.GRANTED

    def covers(
        self, gate_id: str, operation_class: str, target_identity: str,
        revision_identity: str,
    ) -> bool:
        return (
            self.is_granted
            and self.gate_id == gate_id
            and self.operation_class == operation_class
            and self.target_identity == target_identity
            and self.revision_identity == revision_identity
        )

    def render(self) -> str:
        return (
            f"{self.identifier} gate={self.gate_id} op={self.operation_class} "
            f"target={self.target_identity[:19]} revision={self.revision_identity} "
            f"issuer={self.issuer} {self.status.value}"
        )


def _phase_grants(text: str) -> tuple[_PhaseGateGrant, ...]:
    required = {"ID", "GATE", "PHASE", "EVIDENCE PACKAGE", "ISSUER", "STATUS"}
    found: list[_PhaseGateGrant] = []
    for header, rows in _tables(text):
        upper = [_clean(c).upper() for c in header]
        if not required <= set(upper):
            continue
        index = {name: upper.index(name) for name in required}
        basis_at = upper.index("BASIS") if "BASIS" in upper else -1
        for cells in rows:
            found.append(_row_to_phase_grant(cells, index, basis_at))
    return tuple(found)


def _row_to_phase_grant(
    cells: list[str], index: dict[str, int], basis_at: int
) -> _PhaseGateGrant:
    def value(name: str) -> str:
        pos = index[name]
        return _clean(cells[pos]) if pos < len(cells) else ""

    identifier = value("ID")
    gate_id = value("GATE")
    phase_id = value("PHASE")
    digest = value("EVIDENCE PACKAGE")
    issuer = value("ISSUER")
    basis = _clean(cells[basis_at]) if 0 <= basis_at < len(cells) else ""
    if not identifier or not gate_id or not phase_id or not digest or not issuer:
        return _PhaseGateGrant(
            identifier=identifier or "unnamed", gate_id=gate_id, phase_id=phase_id,
            evidence_digest=digest, issuer=issuer, status=_GrantStatus.MALFORMED,
            basis=basis,
        )
    return _PhaseGateGrant(
        identifier=identifier, gate_id=gate_id, phase_id=phase_id,
        evidence_digest=digest, issuer=issuer, status=_status_of(value("STATUS")),
        basis=basis,
    )


def _operation_grants(text: str) -> tuple[_OperationGateGrant, ...]:
    required = {"ID", "GATE", "OPERATION", "TARGET", "REVISION", "ISSUER", "STATUS"}
    found: list[_OperationGateGrant] = []
    for header, rows in _tables(text):
        upper = [_clean(c).upper() for c in header]
        if not required <= set(upper):
            continue
        index = {name: upper.index(name) for name in required}
        basis_at = upper.index("BASIS") if "BASIS" in upper else -1
        for cells in rows:
            found.append(_row_to_operation_grant(cells, index, basis_at))
    return tuple(found)


def _row_to_operation_grant(
    cells: list[str], index: dict[str, int], basis_at: int
) -> _OperationGateGrant:
    def value(name: str) -> str:
        pos = index[name]
        return _clean(cells[pos]) if pos < len(cells) else ""

    identifier = value("ID")
    gate_id = value("GATE")
    operation = value("OPERATION")
    target = value("TARGET")
    revision = value("REVISION")
    issuer = value("ISSUER")
    basis = _clean(cells[basis_at]) if 0 <= basis_at < len(cells) else ""
    if not identifier or not gate_id or not operation or not target or not revision \
            or not issuer:
        return _OperationGateGrant(
            identifier=identifier or "unnamed", gate_id=gate_id,
            operation_class=operation, target_identity=target,
            revision_identity=revision, issuer=issuer, status=_GrantStatus.MALFORMED,
            basis=basis,
        )
    return _OperationGateGrant(
        identifier=identifier, gate_id=gate_id, operation_class=operation,
        target_identity=target, revision_identity=revision, issuer=issuer,
        status=_status_of(value("STATUS")), basis=basis,
    )


def _find_phase_gate_grant(
    repo_root: pathlib.Path, gate_id: str, phase_id: str, digest: str
) -> _PhaseGateGrant | None:
    """The scoped grant covering this exact phase and evidence digest, or None.

    Forbidden issuers (`stable_mutation.prohibited_actors`, the same governed
    list `rescoring_authorization.py` reads) can never produce a grant.
    """
    text, _ = read_document(repo_root, HUMAN_GATE_RECORDS)
    barred = forbidden_issuers(repo_root)
    for grant in _phase_grants(text):
        if grant.issuer.strip().lower() in barred:
            continue
        if grant.covers(gate_id, phase_id, digest):
            return grant
    return None


def _find_operation_gate_grant(
    repo_root: pathlib.Path, gate_id: str, operation_class: str,
    target_identity: str, revision_identity: str,
) -> _OperationGateGrant | None:
    """The scoped grant covering this exact operation, target and revision."""
    text, _ = read_document(repo_root, HUMAN_GATE_RECORDS)
    barred = forbidden_issuers(repo_root)
    for grant in _operation_grants(text):
        if grant.issuer.strip().lower() in barred:
            continue
        if grant.covers(gate_id, operation_class, target_identity, revision_identity):
            return grant
    return None
