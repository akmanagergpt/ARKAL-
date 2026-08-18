"""CORE_PROMOTION/HUMAN_GATE_2 inherits the already-proven scoped-grant
negative controls end to end (ARK-REQ-0138, ARK-REQ-0359's self-approval
half). Mirrors `test_human_gate_authorization.py`'s own fixture pattern -
a temporary copy of the real `docs/` tree with only `HUMAN_GATE_RECORDS.md`
replaced. No accepted repository state is touched.
"""

from __future__ import annotations

import pathlib
import shutil

import pytest

from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.rescoring_authorization import forbidden_issuers
from arkali.lifecycle.evolution.core_upgrade_orchestrator import (
    CORE_PROMOTION_OPERATION,
    GATE_2,
    authorize_promotion,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
RECORDS = "docs/acceptance/HUMAN_GATE_RECORDS.md"
OPERATION_HEADER = (
    "| ID | GATE | OPERATION | TARGET | REVISION | ISSUER | STATUS |\n"
    "|---|---|---|---|---|---|---|\n"
)
MANIFEST_REF = "sha256:" + "c" * 64
REVISION_ID = "sha256:" + "d" * 64


def operation_row(
    identifier: str, gate: str, operation: str, target: str, revision: str,
    issuer: str, status: str,
) -> str:
    return f"| {identifier} | {gate} | {operation} | {target} | {revision} | {issuer} | {status} |\n"


def repo_with_records(tmp_path: pathlib.Path, records_text: str) -> pathlib.Path:
    target = tmp_path / "repo"
    shutil.copytree(REPO / "docs", target / "docs")
    (target / RECORDS).write_text(records_text, encoding="utf-8")
    return target


@pytest.fixture()
def real_issuer() -> str:
    return "human operator"


@pytest.fixture()
def barred_issuer() -> str:
    """A real, canonically-declared prohibited actor - never hard-coded
    (the self-approval boundary: an automated actor listed here can never
    grant its own core-promotion gate)."""
    barred = forbidden_issuers(REPO)
    assert barred, "AUTHORITY_MAP.yaml declares no prohibited actors; fixture has no subject"
    return next(iter(barred))


class TestCorePromotionGrantScope:
    def test_no_grant_at_all_is_refused(self, tmp_path: pathlib.Path) -> None:
        repo = repo_with_records(tmp_path, OPERATION_HEADER)
        state = GovernanceState.load(repo)
        context = authorize_promotion(
            state, candidate_manifest_ref=MANIFEST_REF, target_revision_id=REVISION_ID,
        )
        assert context == {"human_gate_2_recorded": False}

    def test_an_exact_real_grant_is_honoured(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "PC-1", GATE_2, CORE_PROMOTION_OPERATION, MANIFEST_REF, REVISION_ID,
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_promotion(
            state, candidate_manifest_ref=MANIFEST_REF, target_revision_id=REVISION_ID,
        )
        assert context == {"human_gate_2_recorded": True}

    def test_a_barred_actor_cannot_manufacture_its_own_core_promotion_grant(
        self, tmp_path: pathlib.Path, barred_issuer: str
    ) -> None:
        """The self-approval boundary (ARK-REQ-0359): a prohibited automated
        actor issuing itself a `GRANTED` row for its own candidate does not
        authorize the promotion - the same barred-issuer check every other
        scoped gate already uses, composed here rather than reimplemented."""
        text = OPERATION_HEADER + operation_row(
            "PC-2", GATE_2, CORE_PROMOTION_OPERATION, MANIFEST_REF, REVISION_ID,
            barred_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_promotion(
            state, candidate_manifest_ref=MANIFEST_REF, target_revision_id=REVISION_ID,
        )
        assert context == {"human_gate_2_recorded": False}

    def test_a_grant_for_a_different_candidate_manifest_does_not_leak(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "PC-3", GATE_2, CORE_PROMOTION_OPERATION, MANIFEST_REF, REVISION_ID,
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_promotion(
            state, candidate_manifest_ref="sha256:" + "e" * 64,
            target_revision_id=REVISION_ID,
        )
        assert context == {"human_gate_2_recorded": False}

    def test_a_grant_for_a_different_gate_does_not_satisfy_gate_2(
        self, tmp_path: pathlib.Path, real_issuer: str
    ) -> None:
        text = OPERATION_HEADER + operation_row(
            "PC-4", "HUMAN_GATE_4", CORE_PROMOTION_OPERATION, MANIFEST_REF, REVISION_ID,
            real_issuer, "GRANTED",
        )
        repo = repo_with_records(tmp_path, text)
        state = GovernanceState.load(repo)
        context = authorize_promotion(
            state, candidate_manifest_ref=MANIFEST_REF, target_revision_id=REVISION_ID,
        )
        assert context == {"human_gate_2_recorded": False}
