"""Protected Core profile check, isolated from the checker (ARK-REQ-0111).

Owner: acceptance.engine (Protected Core).

WHY THIS IS A SEPARATE MODULE. Wiring the profile directly into `checker.py`
pushed that module to four bounded contexts against a
`max_contexts_touched_by_module` budget of 3. The budget was pointing at real
coupling: the checker orchestrates, and orchestration modules accrete
dependencies until they become the central object the constitution forbids. The
dependency on `control.policy` lives here instead, and the checker consumes one
function from its own context.

The membership itself is still not copied - `ProtectedCoreBoundary` reads
`AUTHORITY_MAP.yaml`. This module adds an indirection, not a second authority.
"""

from __future__ import annotations

import pathlib

from arkali.acceptance.phase_report import PhaseReport
from arkali.acceptance.verification_profile import (
    ProfileVerdict,
    ProtectedCoreCandidate,
    evaluate_profile,
    required_categories,
    select_profile,
)
from arkali.control.policy.protected_core import ProtectedCoreBoundary


def load_protected_core(repo_root: pathlib.Path) -> ProtectedCoreBoundary:
    """The boundary, loaded here so the checker needs no `control.policy` edge."""
    return ProtectedCoreBoundary.load(repo_root)


def evaluate_report_profile(
    repo_root: pathlib.Path, report: PhaseReport, boundary: ProtectedCoreBoundary
) -> ProfileVerdict:
    """Select the profile a phase report requires and check its evidence.

    The change set is the report's own created and modified file lists, so the
    profile follows what the phase actually touched. A phase cannot understate
    its change set without also understating its deliverables.
    """
    candidate = ProtectedCoreCandidate(
        candidate_id=f"phase-{report.phase_id}",
        changed_paths=tuple(report.files_created) + tuple(report.files_modified),
    )
    selection = select_profile(candidate, boundary)
    if not selection.requires_stronger_profile:
        return evaluate_profile(selection, report.tests_executed, ())
    return evaluate_profile(
        selection, report.tests_executed, required_categories(repo_root)
    )
