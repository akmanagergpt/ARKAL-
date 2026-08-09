"""Negative controls for GOV-001 enforcement (closes F-0026).

GOV-001 required explicit authorization before a previously accepted phase may
be re-scored, but recorded as prose it depended on the implementing actor
choosing to obey it — the dependency F-0024 proved unsafe. These controls prove
the mechanism, not the intention.

All fourteen cases the ruling requires have a test below. Fixtures are in-memory
or temporary copies; no accepted repository state is modified, and the final
class asserts that.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil

import pytest
from arkali.acceptance.checker import PhaseGateChecker
from arkali.acceptance.gate_verdict import Verdict
from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.rescoring_authorization import (
    AuthorizationStatus,
    evidence_package_digest,
    find_authorization,
    forbidden_issuers,
    parse_authorizations,
)
from arkali.kernel.contracts.errors import AuthoritativeSourceError
from arkali.kernel.contracts.results import HonestState

REPO = pathlib.Path(__file__).resolve().parents[3]
RECORDS = "docs/acceptance/HUMAN_GATE_RECORDS.md"

HEADER = (
    "| ID | Phase | Evidence package | Issuer | Status | Basis |\n"
    "|---|---|---|---|---|---|\n"
)


def row(identifier: str, phase: str, digest: str, issuer: str, status: str) -> str:
    return f"| {identifier} | {phase} | {digest} | {issuer} | {status} | basis |\n"


def table(*rows: str) -> str:
    return HEADER + "".join(rows)


@pytest.fixture(scope="module")
def live_digest() -> str:
    return evidence_package_digest(REPO, "4")


def repo_with_records(tmp_path: pathlib.Path, records_text: str) -> pathlib.Path:
    """A temporary repo whose governance record is replaced, nothing else."""
    target = tmp_path / "repo"
    shutil.copytree(REPO / "docs", target / "docs")
    (target / RECORDS).write_text(records_text, encoding="utf-8")
    return target


class TestControl1FirstAcceptanceNeedsNoAuthorization:
    def test_an_unaccepted_phase_takes_the_first_acceptance_path(self) -> None:
        """Control 1. Phase 5 is unlocked and not accepted."""
        state = GovernanceState.load(REPO)
        assert not state.phase("5").is_accepted
        checker = PhaseGateChecker(REPO)
        report = _report_for(checker, "5")
        result = checker.check_rescoring_authority(report)
        assert result.state is HonestState.NOT_APPLICABLE

    def test_control_14_phase_5_is_not_treated_as_a_rescore(self) -> None:
        """Control 14. Phase 4 being superseded must not contaminate Phase 5."""
        checker = PhaseGateChecker(REPO)
        result = checker.check_rescoring_authority(_report_for(checker, "5"))
        assert result.state is HonestState.NOT_APPLICABLE
        assert "no prior acceptance record" in result.summary


def _report_for(checker: PhaseGateChecker, phase_id: str):
    from arkali.acceptance.phase_report import PhaseReport, TestExecutionRecord

    return PhaseReport(
        phase_id=phase_id,
        objective="fixture",
        ark_req_ids_closed=(),
        files_created=("README.md",),
        files_modified=(),
        public_contracts=(),
        migrations=(),
        state_machine_capability_changes="none",
        tests_executed=(TestExecutionRecord(command="pytest -q", exit_code=0),),
        architecture_checks="n/a",
        duplicate_shadow_check="n/a",
        security_findings="none",
        fake_success_scan="clean",
        evidence_created=("EV-0001",),
        limitations="fixture",
        blockers="none",
        next_exact_action="n/a",
        status=HonestState.PASS,
    )


class TestControl2And3AuthorizationGovernsTheVerdict:
    def test_2_accepted_phase_without_authorization_cannot_be_re_accepted(
        self, tmp_path: pathlib.Path, live_digest: str
    ) -> None:
        """Control 2."""
        root = repo_with_records(tmp_path, "# no authorizations declared\n")
        checker = PhaseGateChecker(REPO)
        result = checker.check_rescoring_authority(_report_for(checker, "4"))
        assert result.state is HonestState.PASS  # the live repo IS authorized
        assert find_authorization(root, "4", live_digest) is None

    def test_2b_the_verdict_is_awaiting_rescoring_authority(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = repo_with_records(tmp_path, "# none\n")
        assert find_authorization(root, "4", "sha256:whatever") is None

    def test_3_valid_exact_authorization_permits_evaluation(
        self, live_digest: str
    ) -> None:
        """Control 3. The live repository carries RSA-001 for this package."""
        found = find_authorization(REPO, "4", live_digest)
        assert found is not None
        assert found.identifier == "RSA-001"
        assert found.is_granted

    def test_the_live_phase_4_verdict_is_accepted(self) -> None:
        checker = PhaseGateChecker(REPO)
        result = checker.check_rescoring_authority(_report_for(checker, "4"))
        assert result.state is HonestState.PASS
        assert "RSA-001" in result.summary


class TestControls4To6BindingIsExact:
    def test_4_authorization_for_one_phase_cannot_authorize_another(
        self, tmp_path: pathlib.Path, live_digest: str
    ) -> None:
        """Control 4."""
        root = repo_with_records(
            tmp_path, table(row("RSA-9", "4", live_digest, "human authority", "GRANTED"))
        )
        assert find_authorization(root, "4", live_digest) is not None
        assert find_authorization(root, "5", live_digest) is None
        assert find_authorization(root, "2", live_digest) is None

    def test_5_authorization_for_one_candidate_cannot_authorize_another(
        self, tmp_path: pathlib.Path, live_digest: str
    ) -> None:
        """Control 5. A different candidate produces a different package digest."""
        other = "sha256:" + hashlib.sha256(b"a different candidate").hexdigest()
        root = repo_with_records(
            tmp_path, table(row("RSA-9", "4", other, "human authority", "GRANTED"))
        )
        assert find_authorization(root, "4", other) is not None
        assert find_authorization(root, "4", live_digest) is None

    def test_6_authorization_does_not_survive_a_changed_evidence_package(
        self, tmp_path: pathlib.Path, live_digest: str
    ) -> None:
        """Control 6. Editing the report changes the digest, voiding the grant."""
        root = repo_with_records(
            tmp_path, table(row("RSA-9", "4", live_digest, "human authority", "GRANTED"))
        )
        report = root / "docs/acceptance/phase_4_report.json"
        payload = json.loads(report.read_text(encoding="utf-8"))
        payload["objective"] = payload["objective"] + " (tampered)"
        report.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        changed = evidence_package_digest(root, "4")
        assert changed != live_digest
        assert find_authorization(root, "4", changed) is None


class TestControls7To10FailClosed:
    @pytest.mark.parametrize(
        "bad_row",
        [
            "| RSA-1 | | sha256:x | human authority | GRANTED | b |\n",
            "| | 4 | sha256:x | human authority | GRANTED | b |\n",
            "| RSA-1 | 4 | | human authority | GRANTED | b |\n",
            "| RSA-1 | 4 | sha256:x | | GRANTED | b |\n",
        ],
    )
    def test_7_malformed_authorization_fails_closed(
        self, tmp_path: pathlib.Path, bad_row: str
    ) -> None:
        """Control 7. A row missing a required field never grants."""
        root = repo_with_records(tmp_path, table(bad_row))
        parsed = parse_authorizations((root / RECORDS).read_text(encoding="utf-8"))
        assert parsed, "the row disappeared instead of being reported"
        assert all(a.status is AuthorizationStatus.MALFORMED for a in parsed)
        assert find_authorization(root, "4", "sha256:x") is None

    @pytest.mark.parametrize("status", ["APPROVED", "OK", "", "PENDING", "yes"])
    def test_unknown_status_fails_closed(
        self, tmp_path: pathlib.Path, status: str
    ) -> None:
        root = repo_with_records(
            tmp_path,
            table(row("RSA-1", "4", "sha256:x", "human authority", status)),
        )
        assert find_authorization(root, "4", "sha256:x") is None

    def test_revoked_authorization_does_not_grant(
        self, tmp_path: pathlib.Path
    ) -> None:
        root = repo_with_records(
            tmp_path,
            table(row("RSA-1", "4", "sha256:x", "human authority", "REVOKED")),
        )
        assert find_authorization(root, "4", "sha256:x") is None

    @pytest.mark.parametrize(
        "issuer",
        ["implementing_actor", "ai_agent", "workflow", "plugin",
         "computer_use_worker", "deterministic_transformer"],
    )
    def test_8_and_9_a_forbidden_issuer_cannot_authorize(
        self, tmp_path: pathlib.Path, issuer: str
    ) -> None:
        """Controls 8 and 9. The actor cannot authorize its own supersession."""
        root = repo_with_records(
            tmp_path, table(row("RSA-1", "4", "sha256:x", issuer, "GRANTED"))
        )
        assert find_authorization(root, "4", "sha256:x") is None

    def test_forbidden_issuers_come_from_the_authority_map(self) -> None:
        barred = forbidden_issuers(REPO)
        assert "implementing_actor" in barred
        assert "ai_agent" in barred, "not derived from stable_mutation"

    def test_10_no_boolean_or_flag_can_bypass_authorization(self) -> None:
        """Control 10. There is nowhere to pass authorization in."""
        import inspect

        from arkali.acceptance import rescoring_authorization as module

        signature = inspect.signature(module.find_authorization)
        assert list(signature.parameters) == ["repo_root", "phase_id", "digest"]
        source = pathlib.Path(module.__file__ or "").read_text(encoding="utf-8")
        for bypass in ("force", "--rescore", "skip_authorization", "authorized=True"):
            assert bypass not in source

        checker_source = (
            REPO / "backend/arkali/acceptance/checker.py"
        ).read_text(encoding="utf-8")
        for bypass in ("--force", "skip_authorization", "allow_rescore"):
            assert bypass not in checker_source

    def test_an_unreadable_governance_record_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(AuthoritativeSourceError):
            find_authorization(empty, "4", "sha256:x")

    def test_a_missing_evidence_package_fails_closed(
        self, tmp_path: pathlib.Path
    ) -> None:
        empty = tmp_path / "empty2"
        empty.mkdir()
        with pytest.raises(AuthoritativeSourceError):
            evidence_package_digest(empty, "4")


class TestControls11To13HistoryAndRatification:
    def test_11_historical_acceptance_records_remain_preserved(self) -> None:
        """Control 11."""
        defective = REPO / "docs/acceptance/phase_4_report_rev1_defective.json"
        assert defective.is_file(), "the defective revision was deleted"
        payload = json.loads(defective.read_text(encoding="utf-8"))
        assert "ARK-REQ-0111" in payload["ark_req_ids_closed"], (
            "the defective revision was edited; it must record the defect as it was"
        )

    def test_12_a_superseding_verdict_does_not_rewrite_the_old_one(self) -> None:
        """Control 12. Both revisions exist side by side."""
        current = json.loads(
            (REPO / "docs/acceptance/phase_4_report.json").read_text(encoding="utf-8")
        )
        defective = json.loads(
            (REPO / "docs/acceptance/phase_4_report_rev1_defective.json")
            .read_text(encoding="utf-8")
        )
        assert current["objective"] != defective["objective"]
        assert "REVISION 2" in current["objective"]

    def test_13_gov_001_ratification_of_phase_4_remains_valid(
        self, live_digest: str
    ) -> None:
        """Control 13."""
        found = find_authorization(REPO, "4", live_digest)
        assert found is not None and found.is_granted
        assert "GOV-001" in found.basis, (
            "RSA-001 must cite GOV-001 as its basis, not stand alone"
        )
        verdict = PhaseGateChecker(REPO).evaluate(
            _load_live_report(), requested_next_phase="5"
        )
        assert verdict.verdict is Verdict.PHASE_ACCEPTED_BY_MACHINE


def _load_live_report():
    from arkali.acceptance.phase_report import PhaseReport

    payload = json.loads(
        (REPO / "docs/acceptance/phase_4_report.json").read_text(encoding="utf-8")
    )
    return PhaseReport(**payload)


class TestDriftControls:
    def test_revoking_the_live_authorization_changes_the_verdict(
        self, tmp_path: pathlib.Path, live_digest: str
    ) -> None:
        """Governance change alters the verdict with no validator edited."""
        text = (REPO / RECORDS).read_text(encoding="utf-8").replace(
            f"| {live_digest} | human acceptance authority | GRANTED |",
            f"| {live_digest} | human acceptance authority | REVOKED |",
        )
        root = repo_with_records(tmp_path, text)
        assert find_authorization(root, "4", live_digest) is None
        assert find_authorization(REPO, "4", live_digest) is not None

    def test_changing_the_issuer_to_a_barred_actor_changes_the_verdict(
        self, tmp_path: pathlib.Path, live_digest: str
    ) -> None:
        text = (REPO / RECORDS).read_text(encoding="utf-8").replace(
            "| human acceptance authority | GRANTED |",
            "| implementing_actor | GRANTED |",
        )
        root = repo_with_records(tmp_path, text)
        assert find_authorization(root, "4", live_digest) is None


class TestNoAcceptedStateIsMutated:
    def test_evaluation_does_not_modify_governance_artifacts(self) -> None:
        watched = [
            REPO / RECORDS,
            REPO / "docs/build/BUILD_STATE.md",
            REPO / "docs/acceptance/phase_4_report.json",
            REPO / "docs/acceptance/phase_4_report_rev1_defective.json",
        ]
        before = {p: p.read_bytes() for p in watched}
        PhaseGateChecker(REPO).evaluate(_load_live_report(), requested_next_phase="5")
        assert {p: p.read_bytes() for p in watched} == before
