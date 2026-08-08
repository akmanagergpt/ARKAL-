"""Stronger verification profile for Protected Core changes (ARK-REQ-0111).

Owner: acceptance.engine (Protected Core). Closes F-0024.

CANONICAL OBLIGATION, PARSED NOT ASSUMED. `MS §Protected Core` states that
Protected Core "is modified only through the Stable Core candidate lifecycle,
under a stronger verification profile requiring security review, adversarial
review and full regression, and requires HUMAN GATE 2." The three required
categories are extracted from that sentence at call time rather than written
here, so the profile follows the canonical text if it ever changes.

MEMBERSHIP IS NOT COPIED. Which paths are Protected Core comes from
`control.policy.protected_core.ProtectedCoreBoundary`, which reads
`AUTHORITY_MAP.yaml`. `acceptance.engine` is layer rank 2 and `control.policy`
is rank 1, so this edge is legal; no private path list exists anywhere here.

THE ACTOR CANNOT DOWNGRADE ITS OWN PROFILE. `select_profile` takes a change set
and returns the required profile. There is no parameter by which a caller can
propose one, and `ProtectedCoreCandidate` has no profile field. A change that
touches Protected Core gets the stronger profile because of what it touches, not
because of what its author declared.

EVIDENCE IS EXECUTION, NOT A BOOLEAN. Each required category is satisfied only
by a `TestExecutionRecord` naming a real command and its exit code. There is no
`mark_satisfied` and no boolean anywhere in this module. A category with no
record, or with a non-zero exit code, is missing.

FAIL CLOSED. A path whose ownership cannot be resolved makes the selection
UNRESOLVED, which is treated as Protected Core - the strict side - and the
profile verdict is incomplete until it is classified.
"""

from __future__ import annotations

import enum
import pathlib
import re

from pydantic import BaseModel, ConfigDict

from arkali.acceptance.phase_report import TestExecutionRecord
from arkali.control.policy.protected_core import ProtectedCoreBoundary
from arkali.kernel.contracts.errors import AuthoritativeSourceError

MASTER_SPEC_RELPATH = "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md"

#: The canonical sentence that declares the stronger profile's categories.
_PROFILE_SENTENCE = re.compile(
    r"stronger verification profile requiring\s+(?P<categories>[^.]+?),?\s+and requires",
    re.I,
)


class Profile(str, enum.Enum):
    """Which verification profile a change set requires."""

    NORMAL = "NORMAL"
    PROTECTED_CORE = "PROTECTED_CORE"


class ProtectedCoreCandidate(BaseModel):
    """A change set submitted for verification.

    Deliberately carries no profile field: the profile is derived from the
    changed paths, never declared by the actor making the change.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    changed_paths: tuple[str, ...]


class ProfileSelection(BaseModel):
    """The deterministic answer to 'which profile does this change need?'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_id: str
    profile: Profile
    protected_members: tuple[str, ...]
    protected_paths: tuple[str, ...]
    unresolved_paths: tuple[str, ...]
    rationale: str

    @property
    def requires_stronger_profile(self) -> bool:
        return self.profile is Profile.PROTECTED_CORE


class ProfileVerdict(BaseModel):
    """Whether the required evidence for the selected profile is present."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    selection: ProfileSelection
    required_categories: tuple[str, ...]
    supplied: tuple[TestExecutionRecord, ...]
    satisfied_categories: tuple[str, ...]
    missing_categories: tuple[str, ...]
    failing_commands: tuple[str, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_categories and not self.failing_commands

    def render(self) -> str:
        verdict = "COMPLETE" if self.complete else "INCOMPLETE"
        return (
            f"{verdict} {self.selection.candidate_id} "
            f"profile={self.selection.profile.value} "
            f"required={list(self.required_categories)} "
            f"satisfied={list(self.satisfied_categories)} "
            f"missing={list(self.missing_categories)} "
            f"failing={list(self.failing_commands)}"
        )


def required_categories(repo_root: pathlib.Path) -> tuple[str, ...]:
    """The stronger profile's evidence categories, parsed from the Master Spec."""
    path = repo_root / MASTER_SPEC_RELPATH
    if not path.is_file():
        raise AuthoritativeSourceError(
            "master specification not found", source=str(path)
        )
    found = _PROFILE_SENTENCE.search(path.read_text(encoding="utf-8"))
    if found is None:
        raise AuthoritativeSourceError(
            "the Master Specification declares no stronger verification profile; "
            "refusing to invent its categories",
            source=str(path),
        )
    categories = tuple(
        part.strip().lower()
        for part in re.split(r",|\band\b", found.group("categories"))
        if part.strip()
    )
    if not categories:
        raise AuthoritativeSourceError(
            "stronger verification profile declares no categories", source=str(path)
        )
    return categories


def select_profile(
    candidate: ProtectedCoreCandidate, boundary: ProtectedCoreBoundary
) -> ProfileSelection:
    """Derive the required profile from what the change actually touches."""
    members: set[str] = set()
    protected: list[str] = []
    unresolved: list[str] = []
    for raw in candidate.changed_paths:
        path = raw.strip()
        if not path:
            unresolved.append(raw)
            continue
        owner = boundary.owning_context(path)
        if owner is not None:
            members.add(owner)
            protected.append(path)
    if members or unresolved:
        reason = (
            f"touches protected-core contexts {sorted(members)}"
            if members
            else "path ownership could not be resolved; failing closed"
        )
        return ProfileSelection(
            candidate_id=candidate.candidate_id,
            profile=Profile.PROTECTED_CORE,
            protected_members=tuple(sorted(members)),
            protected_paths=tuple(sorted(protected)),
            unresolved_paths=tuple(sorted(unresolved)),
            rationale=reason,
        )
    return ProfileSelection(
        candidate_id=candidate.candidate_id,
        profile=Profile.NORMAL,
        protected_members=(),
        protected_paths=(),
        unresolved_paths=(),
        rationale="no protected-core member touched",
    )


def evaluate_profile(
    selection: ProfileSelection,
    supplied: tuple[TestExecutionRecord, ...],
    categories: tuple[str, ...],
) -> ProfileVerdict:
    """Check the supplied executions against the categories the profile requires.

    A record satisfies a category when its `summary` names the category and its
    exit code is zero. Naming is required because evidence must be linked to the
    obligation it discharges; a zero exit code alone proves only that something
    ran.
    """
    required = categories if selection.requires_stronger_profile else ()
    satisfied: list[str] = []
    failing = [r.command for r in supplied if r.exit_code != 0]
    for category in required:
        matches = [
            r for r in supplied
            if category in r.summary.lower() and r.exit_code == 0
        ]
        if matches:
            satisfied.append(category)
    missing = tuple(c for c in required if c not in satisfied)
    return ProfileVerdict(
        selection=selection,
        required_categories=required,
        supplied=supplied,
        satisfied_categories=tuple(satisfied),
        missing_categories=missing,
        failing_commands=tuple(sorted(set(failing))),
    )
