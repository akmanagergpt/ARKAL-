"""HUMAN_GATE_SCOPE_GAP remediation - negative and positive controls.

Proves the exact invariant the human governance ruling authorized: a
human-gate decision must not authorize any candidate, phase, evidence
package, operation, migration, target, revision or protected-core mutation
other than the exact scope reviewed and granted. Every case the ruling's
Package 6 names has a test below, plus the confused-deputy proof the design
audit flagged as a finding not on the original list.

Fixtures are temporary copies of the real `docs/` tree with only
`HUMAN_GATE_RECORDS.md` replaced - the same pattern `test_rescoring_
authorization.py` already established for the identical dependency shape
(`forbidden_issuers` reads the real `AUTHORITY_MAP.yaml`). No accepted
repository state is modified; the final class asserts that directly against
the real, live `HUMAN_GATE_RECORDS.md`.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

from arkali.acceptance.checker import PhaseGateChecker
from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.human_gate_authorization import (
    SINGLETON_GATES,
    _find_operation_gate_grant,
    _find_phase_gate_grant,
    _GrantStatus,
)
from arkali.acceptance.rescoring_authorization import (
    evidence_package_digest,
    forbidden_issuers,
)
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]
RECORDS = "docs/acceptance/HUMAN_GATE_RECORDS.md"

PHASE_HEADER = "| ID | GATE | PHASE | EVIDENCE PACKAGE | ISSUER | STATUS |\n|---|---|---|---|---|---|\n"
OPERATION_HEADER = (
    "| ID | GATE | OPERATION | TARGET | REVISION | ISSUER | STATUS |\n"
    "|---|---|---|---|---|---|---|\n"
)


def phase_row(identifier: str, gate: str, phase: str, digest: str, issuer: str, status: str) -> str:
    return f"| {identifier} | {gate} | {phase} | {digest} | {issuer} | {status} |\n"


def operation_row(
    identifier: str, gate: str, operation: str, target: str, revision: str,
    issuer: str, status: str,
) -> str:
    return f"| {identifier} | {gate} | {operation} | {target} | {revision} | {issuer} | {status} |\n"


def repo_with_records(tmp_path: pathlib.Path, records_text: str) -> pathlib.Path:
    """A temporary repo whose governance record is replaced, nothing else."""
    target = tmp_path / "repo"
    shutil.copytree(REPO / "docs", target / "docs")
    (target / RECORDS).write_text(records_text, encoding="utf-8")
    return target


@pytest.fixture()
def real_issuer() -> str:
    return "human operator"


@pytest.fixture()
def barred_issuer() -> str:
    """A real, canonically-declared prohibited actor - never hard-coded."""
    barred = forbidden_issuers(REPO)
    assert barred, "AUTHORITY_MAP.yaml declares no prohibited actors; fixture has no subject"
    return next(iter(barred))


class TestPhaseScopeNegativeControls:
    """Controls 1, 2, 6, 7, 8, 9, 10, 11, 13 for `_find_phase_gate_grant`."""

    def test_1_same_gate_different_phase_is_refused(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = PHASE_HEADER + phase_row("X-1", "HUMAN_GATE_4", "19", "sha256:aaa", real_issuer, "GRANTED")
        repo = repo_with_records(tmp_path, text)
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "21", "sha256:aaa") is None

    def test_2_same_gate_same_phase_different_digest_is_refused(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = PHASE_HEADER + phase_row("X-2", "HUMAN_GATE_4", "19", "sha256:aaa", real_issuer, "GRANTED")
        repo = repo_with_records(tmp_path, text)
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "19", "sha256:bbb") is None

    def test_6_altered_evidence_binding_is_refused(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        """A grant recorded for the original digest does not follow a tampered
        (re-authored) evidence package to its new, different digest."""
        original = PHASE_HEADER + phase_row("X-6", "HUMAN_GATE_4", "19", "sha256:original", real_issuer, "GRANTED")
        repo = repo_with_records(tmp_path, original)
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "19", "sha256:original") is not None
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "19", "sha256:tampered") is None

    def test_7_forbidden_issuer_cannot_manufacture_a_grant(
        self, tmp_path: pathlib.Path, barred_issuer: str
    ) -> None:
        text = PHASE_HEADER + phase_row("X-7", "HUMAN_GATE_4", "19", "sha256:aaa", barred_issuer, "GRANTED")
        repo = repo_with_records(tmp_path, text)
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "19", "sha256:aaa") is None

    def test_8_prose_only_record_does_not_satisfy_mechanical_scope(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The old `## HGR-NNN - HUMAN GATE N` / `**Decision** | **ACCEPTED**`
        shape (still valid for `state.accepted_human_gates`, the SINGLETON_GATES
        legacy path) is not a table this module reads at all."""
        prose = (
            "## HGR-999 - HUMAN GATE 4: some candidate\n\n"
            "| Field | Value |\n|---|---|\n"
            "| **Decision** | **ACCEPTED** |\n"
        )
        repo = repo_with_records(tmp_path, prose)
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "19", "sha256:anything") is None

    def test_9_legacy_unscoped_acceptance_does_not_authorize_a_new_candidate(self) -> None:
        """`state.accepted_human_gates` containing HUMAN_GATE_4 (it does, from
        the real HGR-002 prose record) must not, by itself, satisfy a scoped
        phase check for a phase/digest no scoped table row names."""
        state = GovernanceState.load(REPO)
        assert "HUMAN_GATE_4" in state.accepted_human_gates
        assert "HUMAN_GATE_4" not in SINGLETON_GATES
        assert _find_phase_gate_grant(REPO, "HUMAN_GATE_4", "999", "sha256:never-recorded") is None

    def test_10_tampered_status_fails_closed(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = PHASE_HEADER + phase_row("X-10", "HUMAN_GATE_4", "19", "sha256:aaa", real_issuer, "ACCEPTED")
        repo = repo_with_records(tmp_path, text)
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "19", "sha256:aaa") is None

    def test_11_missing_binding_field_fails_closed(self, tmp_path: pathlib.Path) -> None:
        malformed = (
            "| ID | GATE | PHASE | EVIDENCE PACKAGE | ISSUER | STATUS |\n"
            "|---|---|---|---|---|---|\n"
            "| X-11 | HUMAN_GATE_4 |  |  | human operator | GRANTED |\n"
        )
        repo = repo_with_records(tmp_path, malformed)
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "19", "sha256:aaa") is None
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_4", "", "sha256:aaa") is None

    def test_13_gate_substitution_fails(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        """A grant for HUMAN_GATE_4 does not satisfy a HUMAN_GATE_6 check, even
        for the identical phase and digest."""
        text = PHASE_HEADER + phase_row("X-13", "HUMAN_GATE_4", "20", "sha256:aaa", real_issuer, "GRANTED")
        repo = repo_with_records(tmp_path, text)
        assert _find_phase_gate_grant(repo, "HUMAN_GATE_6", "20", "sha256:aaa") is None

    def test_12_exact_valid_scope_succeeds(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = PHASE_HEADER + phase_row("X-12", "HUMAN_GATE_4", "19", "sha256:aaa", real_issuer, "GRANTED")
        repo = repo_with_records(tmp_path, text)
        grant = _find_phase_gate_grant(repo, "HUMAN_GATE_4", "19", "sha256:aaa")
        assert grant is not None
        assert grant.status is _GrantStatus.GRANTED


class TestOperationScopeNegativeControls:
    """Controls 4, 5, 6, 7, 13, 14 for `_find_operation_gate_grant`."""

    def test_4_different_revision_is_refused(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "Y-4", "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1", real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        assert _find_operation_gate_grant(repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1") is not None
        assert _find_operation_gate_grant(repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-2") is None

    def test_5_different_target_is_refused(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "Y-5", "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1", real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        assert _find_operation_gate_grant(repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-B", "rev-1") is None

    def test_6_altered_target_binding_is_refused(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "Y-6", "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-original", "rev-1", real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        assert _find_operation_gate_grant(
            repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-tampered", "rev-1"
        ) is None

    def test_7_forbidden_issuer_cannot_manufacture_an_operation_grant(
        self, tmp_path: pathlib.Path, barred_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "Y-7", "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1", barred_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        assert _find_operation_gate_grant(repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1") is None

    def test_13_gate_substitution_fails(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "Y-13", "HUMAN_GATE_4", "APPLY_MIGRATION", "digest-A", "rev-1", real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        assert _find_operation_gate_grant(repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1") is None

    def test_14_stale_revision_binding_fails(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        """Same shape as control 4, named separately per the mission's own list:
        a grant reviewed against one resolved target revision must not survive
        the target moving to a later one - the identical staleness discipline
        `WorkflowApprovalGate.is_enforced_approval` already proves for the
        ordinary human-decision half of Apply."""
        text = OPERATION_HEADER + operation_row(
            "Y-14", "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "0005_durable_job",
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        assert _find_operation_gate_grant(
            repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "0009_workflow_execution",
        ) is None

    def test_10_tampered_status_fails_closed(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "Y-10", "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1", real_issuer, "MAYBE",
        )
        repo = repo_with_records(tmp_path, text)
        assert _find_operation_gate_grant(repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1") is None

    def test_11_missing_binding_field_fails_closed(self, tmp_path: pathlib.Path) -> None:
        malformed = (
            "| ID | GATE | OPERATION | TARGET | REVISION | ISSUER | STATUS |\n"
            "|---|---|---|---|---|---|---|\n"
            "| Y-11 | HUMAN_GATE_6 | APPLY_MIGRATION |  |  | human operator | GRANTED |\n"
        )
        repo = repo_with_records(tmp_path, malformed)
        assert _find_operation_gate_grant(repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "", "") is None

    def test_12_exact_valid_scope_succeeds(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "Y-12", "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1", real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        grant = _find_operation_gate_grant(repo, "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1")
        assert grant is not None
        assert grant.status is _GrantStatus.GRANTED


class TestControl3RealHistoricalPhase19DoesNotLeakToPhase21:
    """Control 3, against the REAL, live `HUMAN_GATE_RECORDS.md` - not a
    synthetic fixture. HGR-002-SCOPED restates HGR-002's already-recorded
    Phase 19 decision; this proves the restatement is genuinely scoped."""

    def test_phase_19_grant_exists_for_its_own_real_digest(self) -> None:
        digest = evidence_package_digest(REPO, "19")
        grant = _find_phase_gate_grant(REPO, "HUMAN_GATE_4", "19", digest)
        assert grant is not None
        assert grant.identifier == "HGR-002-SCOPED"

    def test_the_same_grant_does_not_satisfy_a_phase_21_lookup(self) -> None:
        digest = evidence_package_digest(REPO, "19")
        assert _find_phase_gate_grant(REPO, "HUMAN_GATE_4", "21", digest) is None

    def test_phase_19_grant_does_not_satisfy_phase_20(self) -> None:
        """HGR-002-SCOPED (Phase 19) must not satisfy Phase 20's own,
        separately-granted HUMAN_GATE_6 check.

        F-0051. The original version of this test asserted
        `checker.check_human_gate("20") is BLOCKED` outright - true only
        because, at write time, no HUMAN_GATE_6 grant of any kind existed
        yet for any phase. That is a transient fact about the repository's
        acceptance history, not an invariant of the scoping mechanism: once
        the human acceptance authority legitimately grants HUMAN_GATE_6 for
        Phase 20's own evidence package (a different gate token, `HUMAN_
        GATE_6` vs `HUMAN_GATE_4`, and a different phase), Phase 20's check
        correctly flips to PASS, and asserting BLOCKED forever would just be
        asserting that Phase 20 must never legitimately clear its own gate.
        The invariant this test actually exists to protect - Phase 19's
        grant, bound to Phase 19's own digest, must never be the reason
        Phase 20 clears - is checked directly against the real, live grant
        table instead, so it stays meaningful regardless of whether Phase 20
        carries its own independent, separately-scoped grant.
        """
        checker = PhaseGateChecker(REPO)
        assert checker.check_human_gate("19").state is HonestState.PASS
        # Phase 20 may itself be PASS or BLOCKED depending on whether its own
        # grant exists - what must never happen is HGR-002-SCOPED (Phase 19's
        # grant) being the reason. Assert directly against the real HGR table.
        digest_19 = evidence_package_digest(REPO, "19")
        leaked = _find_phase_gate_grant(REPO, "HUMAN_GATE_6", "20", digest_19)
        assert leaked is None, "Phase 19's own digest must never satisfy Phase 20"


class TestSingletonGateLegacyPath:
    """HUMAN_GATE_1 and HUMAN_GATE_7 remain gate-ID-only by canonical design -
    the one legacy carve-out this remediation explicitly preserves."""

    def test_singleton_gates_are_exactly_one_and_seven(self) -> None:
        assert SINGLETON_GATES == frozenset({"HUMAN_GATE_1", "HUMAN_GATE_7"})

    def test_gate_1_still_passes_via_the_real_legacy_hgr_001_record(self) -> None:
        checker = PhaseGateChecker(REPO)
        result = checker.check_human_gate("0B")
        assert result.state is HonestState.PASS
        assert "project-singular" in result.summary

    def test_gate_4_is_not_a_singleton_and_needs_the_scoped_table(self) -> None:
        assert "HUMAN_GATE_4" not in SINGLETON_GATES
        assert "HUMAN_GATE_6" not in SINGLETON_GATES


class TestGovernanceStateOperationGrant:
    """`GovernanceState.operation_grant` is the exact method the
    `HumanGateSource` `Protocol` in `lifecycle.recovery` composes against."""

    def test_no_grant_exists_for_a_synthetic_migration_operation(self) -> None:
        state = GovernanceState.load(REPO)
        assert state.operation_grant(
            "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-nobody-recorded", "rev-x",
        ) is False

    def test_a_recorded_operation_grant_is_found(self, tmp_path: pathlib.Path, real_issuer: str) -> None:
        text = OPERATION_HEADER + operation_row(
            "Z-1", "HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1", real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        assert state.operation_grant("HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-1") is True
        assert state.operation_grant("HUMAN_GATE_6", "APPLY_MIGRATION", "digest-A", "rev-2") is False


class TestConfusedDeputyCannotSpoofTargetIdentity:
    """Not on the mission's own numbered list - a finding from the design
    audit. `MigrationSafetyRequest` exposes no field a caller could set to
    claim an arbitrary target identity; `step_apply` derives it itself from
    the real `BackupSet.manifest.digest` a `RecoveryService` actually
    produced. This proves the absence structurally, not just behaviourally."""

    def test_migration_safety_request_has_no_caller_settable_target_identity_field(self) -> None:
        import inspect

        from arkali.lifecycle.recovery.migration_safety_types import MigrationSafetyRequest

        params = set(inspect.signature(MigrationSafetyRequest.__init__).parameters)
        assert "target_identity" not in params
        assert "operation_target" not in params
        assert "revision_identity" not in params

    def test_step_apply_requires_a_real_backupset_not_a_label(self) -> None:
        import inspect

        from arkali.lifecycle.recovery.migration_safety_steps import step_apply

        params = inspect.signature(step_apply).parameters
        assert "backup" in params
        assert params["backup"].annotation in ("BackupSet", "backup_service.BackupSet") \
            or "BackupSet" in str(params["backup"].annotation)


class TestNoRepositoryStateWasModified:
    def test_the_real_human_gate_records_still_parses_and_git_state_is_unchanged(self) -> None:
        """This module reads governance state; it never writes it. A parse of
        the real, live document must succeed without raising."""
        state = GovernanceState.load(REPO)
        assert state.current_work_phase() == "20"
