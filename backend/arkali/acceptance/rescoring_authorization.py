"""Re-scoring authorization for a previously accepted phase (GOV-001, F-0026).

Owner: acceptance.engine (Protected Core).

WHY THIS EXISTS. GOV-001 established that re-accepting a previously accepted
phase requires explicit authorization from the human governance authority, and
that the implementing actor may not grant itself that authority. Recorded as
prose, the rule depended on the actor choosing to obey it — the same dependency
F-0024 proved unsafe, and the shape of F-0020, where a budget existed as a
number with no way to measure it. This module is the mechanism.

NO SECOND ACCEPTANCE-HISTORY AUTHORITY. Whether a phase is already accepted is
read from `GovernanceState`, which parses `BUILD_STATE.md`. Nothing here records
or caches acceptance history.

AUTHORIZATION IS A HUMAN GOVERNANCE RECORD, NOT AN ARGUMENT. Authorizations are
read from `HUMAN_GATE_RECORDS.md`, the canonical home of human decisions. There
is deliberately no parameter, flag, environment variable or report field by
which a caller can assert authorization: `find_authorization` takes a repository
and a subject, and consults the document. An implementing actor cannot pass one
in because there is nowhere to pass it.

BINDING IS BY SUBJECT, NOT BY PHASE ALONE. An authorization names the phase *and*
the digest of the exact evidence package it authorizes — the phase report plus
its traceability record. An authorization for phase 4 cannot authorize phase 5,
and one granted for a given evidence package cannot authorize a different one,
because changing either file changes the digest. This is the strongest binding
available from existing artifacts and needs no new identity system.

FAIL CLOSED. Missing, malformed, revoked, wrong-phase, wrong-package,
unknown-status and self-issued authorizations all yield no authorization. A
malformed row is reported rather than skipped, so an unreadable authorization is
louder than an absent one.
"""

from __future__ import annotations

import enum
import hashlib
import pathlib
import re
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from arkali.acceptance.governance_source import read_document, refuse

HUMAN_GATE_RECORDS = "docs/acceptance/HUMAN_GATE_RECORDS.md"
AUTHORITY_MAP = "docs/canonical/AUTHORITY_MAP.yaml"
ACCEPTANCE_DIR = "docs/acceptance"

_ROW = re.compile(r"^\|(?P<body>.*)\|\s*$")
_SEPARATOR = re.compile(r"^(?=.*-)[\s:|-]+$")
#: Issuer names that can never authorize a supersession, derived below from
#: AUTHORITY_MAP `stable_mutation.prohibited_actors` plus the generic label.
_ALWAYS_FORBIDDEN_ISSUER = "implementing_actor"


class AuthorizationStatus(str, enum.Enum):
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"
    #: Not declarable. Produced when a row cannot be read.
    MALFORMED = "MALFORMED"


class RescoringAuthorization(BaseModel):
    """One recorded authorization to supersede an accepted phase verdict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    identifier: str
    phase_id: str
    evidence_digest: str
    issuer: str
    status: AuthorizationStatus
    basis: str = ""
    detail: str = ""

    @property
    def is_granted(self) -> bool:
        return self.status is AuthorizationStatus.GRANTED

    def covers(self, phase_id: str, digest: str) -> bool:
        """Only for this exact phase and this exact evidence package."""
        return (
            self.is_granted
            and self.phase_id == phase_id
            and self.evidence_digest == digest
        )

    def render(self) -> str:
        return (
            f"{self.identifier} phase={self.phase_id} "
            f"package={self.evidence_digest[:19]} issuer={self.issuer} "
            f"{self.status.value}"
        )


def forbidden_issuers(repo_root: pathlib.Path) -> frozenset[str]:
    """Actors that may never issue an authorization.

    Derived from `AUTHORITY_MAP.yaml` `stable_mutation.prohibited_actors` - the
    canonical list of actors barred from mutating stable state - rather than
    written here. An implementing actor cannot authorize its own supersession.
    """
    text, _ = read_document(repo_root, AUTHORITY_MAP)
    raw: Any = yaml.safe_load(text)
    mutation = (raw or {}).get("stable_mutation") or {}
    declared = {str(a).strip().lower() for a in mutation.get("prohibited_actors", [])}
    return frozenset(declared | {_ALWAYS_FORBIDDEN_ISSUER})


def evidence_package_digest(repo_root: pathlib.Path, phase_id: str) -> str:
    """Identity of the exact evidence package a phase is submitting.

    The phase report and its traceability record together. Changing either
    changes the digest, so an authorization cannot be carried across packages.
    """
    parts: list[bytes] = []
    for name in (f"phase_{phase_id}_report.json",
                 f"phase_{phase_id}_traceability.json"):
        path = repo_root / ACCEPTANCE_DIR / name
        if not path.is_file():
            raise refuse(
                f"evidence package incomplete: {name} is absent", str(path)
            )
        parts.append(path.read_bytes())
    digest = hashlib.sha256(b"\x00".join(parts)).hexdigest()
    return f"sha256:{digest}"


def _clean(cell: str) -> str:
    return cell.replace("*", "").replace("`", "").replace("~", "").strip()


def _status_of(raw: str) -> AuthorizationStatus:
    text = _clean(raw).upper()
    if text == "GRANTED":
        return AuthorizationStatus.GRANTED
    if text == "REVOKED":
        return AuthorizationStatus.REVOKED
    return AuthorizationStatus.MALFORMED


def _tables(text: str) -> list[tuple[list[str], list[list[str]]]]:
    found: list[tuple[list[str], list[list[str]]]] = []
    header: list[str] | None = None
    rows: list[list[str]] = []
    for line in text.splitlines():
        match = _ROW.match(line.strip())
        if match is None:
            if header is not None:
                found.append((header, rows))
            header, rows = None, []
            continue
        cells = [c.strip() for c in match.group("body").split("|")]
        if header is None:
            header, rows = cells, []
            continue
        if _SEPARATOR.match("|".join(cells)):
            continue
        rows.append(cells)
    if header is not None:
        found.append((header, rows))
    return found


def parse_authorizations(text: str) -> tuple[RescoringAuthorization, ...]:
    """Every authorization declared by the governance record.

    A table is an authorization table when it declares the columns this
    contract requires. A row inside one that cannot be read becomes MALFORMED
    rather than disappearing.
    """
    required = {"ID", "PHASE", "EVIDENCE PACKAGE", "ISSUER", "STATUS"}
    found: list[RescoringAuthorization] = []
    for header, rows in _tables(text):
        upper = [_clean(c).upper() for c in header]
        if not required <= set(upper):
            continue
        index = {name: upper.index(name) for name in required if name in upper}
        basis_at = upper.index("BASIS") if "BASIS" in upper else -1
        for cells in rows:
            found.append(_row_to_authorization(cells, index, basis_at))
    return tuple(found)


def _row_to_authorization(
    cells: list[str], index: dict[str, int], basis_at: int
) -> RescoringAuthorization:
    def value(name: str) -> str:
        position = index.get(name, -1)
        return _clean(cells[position]) if 0 <= position < len(cells) else ""

    identifier = value("ID")
    status = _status_of(value("STATUS"))
    phase_id = value("PHASE")
    digest = value("EVIDENCE PACKAGE")
    issuer = value("ISSUER")
    basis = _clean(cells[basis_at]) if 0 <= basis_at < len(cells) else ""
    if not identifier or not phase_id or not digest or not issuer:
        return RescoringAuthorization(
            identifier=identifier or "unnamed",
            phase_id=phase_id,
            evidence_digest=digest,
            issuer=issuer,
            status=AuthorizationStatus.MALFORMED,
            basis=basis,
            detail="authorization row is missing a required field",
        )
    return RescoringAuthorization(
        identifier=identifier,
        phase_id=phase_id,
        evidence_digest=digest,
        issuer=issuer,
        status=status,
        basis=basis,
        detail="" if status is not AuthorizationStatus.MALFORMED
        else f"unreadable status {value('STATUS')!r}",
    )


def find_authorization(
    repo_root: pathlib.Path, phase_id: str, digest: str
) -> RescoringAuthorization | None:
    """The authorization covering this exact subject, or None.

    There is no parameter by which a caller can supply one. Malformed rows and
    forbidden issuers never produce an authorization.
    """
    text, _ = read_document(repo_root, HUMAN_GATE_RECORDS)
    barred = forbidden_issuers(repo_root)
    for authorization in parse_authorizations(text):
        if authorization.issuer.strip().lower() in barred:
            continue
        if authorization.covers(phase_id, digest):
            return authorization
    return None
