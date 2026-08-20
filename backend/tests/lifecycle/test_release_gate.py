"""`HUMAN_GATE_7`/Final Production Release inherits the real, unmodified
`GovernanceState.accepted_human_gates` singleton mechanism Gate 1 already
uses (ARK-REQ-0007, Phase 26 Package 6). Mirrors `test_human_gate_
authorization.py`'s own fixture pattern - a temporary copy of the real
`docs/` tree with only `HUMAN_GATE_RECORDS.md` replaced. No accepted
repository state is touched.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.human_gate_authorization import SINGLETON_GATES
from arkali.lifecycle.release.release_composition import ReleaseManifestComposition
from arkali.lifecycle.release.release_gate import GATE_7, authorize_release

REPO = pathlib.Path(__file__).resolve().parents[3]
RECORDS = "docs/acceptance/HUMAN_GATE_RECORDS.md"


def repo_with_records(tmp_path: pathlib.Path, records_text: str) -> pathlib.Path:
    target = tmp_path / "repo"
    shutil.copytree(REPO / "docs", target / "docs")
    (target / RECORDS).write_text(records_text, encoding="utf-8")
    return target


def _composition() -> ReleaseManifestComposition:
    return ReleaseManifestComposition(
        release_id="sha256:" + "e" * 64, core_revision_id="sha256:" + "f" * 64,
        provenance_artifact_id="sha256:" + "1" * 64, sbom_artifact_id="sha256:" + "2" * 64,
        review_artifact_id="sha256:" + "3" * 64, manifest_artifact_id="sha256:" + "4" * 64,
    )


class _AlwaysVerifiedRegistrar:
    """A fixed-answer stand-in for `ArtifactRegistrar.verify`, used only to
    isolate this file's own subject (the Gate 7 singleton lookup) from
    Package 6's already-proven `verify_evidence_complete` re-derivation,
    tested for real in `test_release_composition.py`."""

    def verify(self, address: str) -> bool:
        del address
        return True


class TestGate7IsCanonicallyASingleton:
    def test_gate_7_is_declared_a_singleton_alongside_gate_1(self) -> None:
        assert SINGLETON_GATES == frozenset({"HUMAN_GATE_1", "HUMAN_GATE_7"})
        assert GATE_7 in SINGLETON_GATES


class TestReleaseGateSingleton:
    def test_no_recorded_gate_7_acceptance_is_refused(self, tmp_path: pathlib.Path) -> None:
        empty = (
            "# HUMAN GATE RECORDS\n\n"
            "## HGR-1 — HUMAN GATE 1: something else\n\n"
            "| Field | Value |\n|---|---|\n"
            "| **Decision** | **ACCEPTED** |\n"
        )
        repo = repo_with_records(tmp_path, empty)
        state = GovernanceState.load(repo)
        context = authorize_release(state, _AlwaysVerifiedRegistrar(), _composition())
        assert context == {"human_gate_7_recorded": False, "evidence_complete": True}

    def test_a_real_recorded_gate_7_acceptance_is_honoured(
        self, tmp_path: pathlib.Path
    ) -> None:
        text = (
            "# HUMAN GATE RECORDS\n\n"
            "## HGR-900 — HUMAN GATE 7: Final Production Release\n\n"
            "| Field | Value |\n|---|---|\n"
            "| **Decision** | **ACCEPTED** |\n"
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_release(state, _AlwaysVerifiedRegistrar(), _composition())
        assert context == {"human_gate_7_recorded": True, "evidence_complete": True}

    def test_a_pending_gate_7_record_does_not_grant(self, tmp_path: pathlib.Path) -> None:
        text = (
            "# HUMAN GATE RECORDS\n\n"
            "## HGR-901 — HUMAN GATE 7: Final Production Release\n\n"
            "| Field | Value |\n|---|---|\n"
            "| **Decision** | **PENDING** |\n"
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_release(state, _AlwaysVerifiedRegistrar(), _composition())
        assert context == {"human_gate_7_recorded": False, "evidence_complete": True}

    def test_a_different_gates_acceptance_does_not_leak_into_gate_7(
        self, tmp_path: pathlib.Path
    ) -> None:
        text = (
            "# HUMAN GATE RECORDS\n\n"
            "## HGR-902 — HUMAN GATE 2: some unrelated core promotion\n\n"
            "| Field | Value |\n|---|---|\n"
            "| **Decision** | **ACCEPTED** |\n"
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_release(state, _AlwaysVerifiedRegistrar(), _composition())
        assert context == {"human_gate_7_recorded": False, "evidence_complete": True}

    def test_the_real_live_repository_has_not_recorded_gate_7_yet(self) -> None:
        """Mechanically re-verified, not assumed: this repository's own real
        HUMAN_GATE_RECORDS.md has never granted the Final Production Release
        gate - proven directly against live repository state, the same
        discipline every gate-scope test in this session already applies."""
        state = GovernanceState.load(REPO)
        assert GATE_7 not in state.accepted_human_gates
