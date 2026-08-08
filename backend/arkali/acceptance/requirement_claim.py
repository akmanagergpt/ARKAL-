"""Requirement claim states and the false-discharge guard (closes F-0024).

Owner: acceptance.engine (Protected Core).

THE DEFECT THIS PREVENTS. Phase 4 shipped two artifacts that disagreed. The
traceability map recorded `ARK-REQ-0111` as DEFERRED - which was true - while the
phase report listed the same id among the requirements it discharged, which is
the field check C2 reads. C2 passed. The honest artifact and the false one were
authored by the same actor in the same commit, and nothing compared them.

THE STANDING RULE. A requirement may appear in a phase report's discharged set
only if the traceability record claims it SATISFIED. Every other canonical state
- DEFERRED, NOT_TESTED, NOT_CONFIGURED, UNSUPPORTED, BLOCKED, FAIL - is a
non-discharge, and a requirement carrying one may not be counted.

FAIL CLOSED IN BOTH DIRECTIONS. A discharged id with no traceability entry fails,
because an unexplained claim is not evidence. A SATISFIED claim naming no
evidence fails, because a claim is not its own proof. An id that is not in the
register at all fails, since the register is the sole denominator.
"""

from __future__ import annotations

import enum
import json
import pathlib

from pydantic import BaseModel, ConfigDict

from arkali.kernel.contracts.errors import AuthoritativeSourceError


class ClaimState(str, enum.Enum):
    """The states a requirement claim may take. Only one permits discharge."""

    SATISFIED = "SATISFIED"
    DEFERRED = "DEFERRED"
    NOT_TESTED = "NOT_TESTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    UNSUPPORTED = "UNSUPPORTED"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"

    @property
    def permits_discharge(self) -> bool:
        return self is ClaimState.SATISFIED


class RequirementClaim(BaseModel):
    """One requirement's claimed state, with what backs it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    req_id: str
    state: ClaimState
    implementation: str = ""
    evidence: str = ""
    note: str = ""

    @property
    def is_backed(self) -> bool:
        """A SATISFIED claim must name an implementation and an evidence source."""
        if not self.state.permits_discharge:
            return True
        return bool(self.implementation.strip()) and bool(self.evidence.strip())


class TraceabilityRecord:
    """Every claim for one phase. Construct with `load`."""

    def __init__(self, phase_id: str, claims: dict[str, RequirementClaim],
                 source_path: str) -> None:
        self.phase_id = phase_id
        self._claims = claims
        self.source_path = source_path

    @classmethod
    def load(cls, repo_root: pathlib.Path, phase_id: str) -> TraceabilityRecord:
        path = repo_root / "docs" / "acceptance" / f"phase_{phase_id}_traceability.json"
        if not path.is_file():
            raise AuthoritativeSourceError(
                f"no traceability record for phase {phase_id}; a phase report "
                "cannot be reconciled against nothing",
                source=str(path),
            )
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise AuthoritativeSourceError(
                f"traceability record is not parseable JSON: {exc}", source=str(path)
            ) from exc
        entries = raw.get("claims")
        if not isinstance(entries, list) or not entries:
            raise AuthoritativeSourceError(
                "traceability record declares no claims", source=str(path)
            )
        claims: dict[str, RequirementClaim] = {}
        for entry in entries:
            claim = RequirementClaim(**entry)
            if claim.req_id in claims:
                raise AuthoritativeSourceError(
                    f"duplicate claim for {claim.req_id}", source=str(path)
                )
            claims[claim.req_id] = claim
        return cls(str(raw.get("phase_id", phase_id)), claims, str(path))

    def __len__(self) -> int:
        return len(self._claims)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._claims))

    def get(self, req_id: str) -> RequirementClaim | None:
        return self._claims.get(req_id)

    def satisfied_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(r for r, c in self._claims.items() if c.state.permits_discharge)
        )

    def non_satisfied(self) -> tuple[RequirementClaim, ...]:
        return tuple(
            sorted(
                (c for c in self._claims.values() if not c.state.permits_discharge),
                key=lambda c: c.req_id,
            )
        )


def reconcile_discharge(
    discharged: tuple[str, ...],
    record: TraceabilityRecord,
    register_ids: frozenset[str],
) -> tuple[str, ...]:
    """Violations preventing the discharged set from being trusted.

    Empty result means the phase report's claims agree with the traceability
    record and the register. Any entry is a false discharge.
    """
    violations: list[str] = []
    for req_id in sorted(set(discharged)):
        if req_id not in register_ids:
            violations.append(f"{req_id}: discharged but absent from the register")
            continue
        claim = record.get(req_id)
        if claim is None:
            violations.append(
                f"{req_id}: discharged but has no traceability claim"
            )
            continue
        if not claim.state.permits_discharge:
            violations.append(
                f"{req_id}: discharged while traceability claims "
                f"{claim.state.value}"
            )
            continue
        if not claim.is_backed:
            violations.append(
                f"{req_id}: claimed SATISFIED without naming an implementation "
                "and an evidence source"
            )
    return tuple(violations)
