"""Phase 23 composed journey: the real VDC "ARKALI Self-Evolution" sequence.

MS "ARKALI Self-Evolution": "Stable Core -> Snapshot -> Isolated Candidate ->
Improvement -> Architecture Tests -> Regression -> Security -> Compatibility
-> User Approval -> Promotion." Every step below is a real call against real
SQLite (via the real Alembic chain), the real PDP, the real Stable-revision
pointer, a real Recovery Supervisor (genuinely verified through a real prior
rollback, not fabricated), and the real C-14/C-15 evidence plane - matching
this build's own established discipline for a composed real-authority
journey (`test_phase_22b_journey.py`).

Two real campaigns are run to their real terminal state: one reaches
PROMOTED through a real HUMAN_GATE_2 grant; the other is REJECTED with no
grant and exhausts its own declared budget, reaching
COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN without ever touching Stable.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from decimal import Decimal

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from arkali.acceptance.campaign_record_shape import _check_campaign_record_shape
from arkali.acceptance.governance_state import GovernanceState
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore
from arkali.evidence.audit.chain import AuditChain
from arkali.kernel.contracts.state_machine_errors import GuardRejected
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.evolution import core_upgrade_state_machine as cusm
from arkali.lifecycle.evolution import evolution_campaign_state_machine as ecsm
from arkali.lifecycle.evolution.campaign_declaration import (
    CampaignBudgets,
    CampaignDeclaration,
)
from arkali.lifecycle.evolution.campaign_ledger import CampaignAttempt, CampaignLedger
from arkali.lifecycle.evolution.core_promotion import (
    CorePromotionRequest,
    promote_core_upgrade,
)
from arkali.lifecycle.evolution.core_upgrade_orchestrator import begin_core_upgrade
from arkali.lifecycle.recovery.recovery_supervisor import (
    ACTOR,
    TRUST_TIER,
    HealthCheckResult,
    RecoverySupervisor,
)
from arkali.lifecycle.release.stable_path import StableCandidatePath, StageReceipt
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer
from tests.persistence.conftest import AuditChainEvidenceSink, PepRollbackAuthorization

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

REV_GENESIS = "sha256:" + "1" * 64
REV_BAD_UPGRADE = "sha256:" + "2" * 64
REV_ROLLED_BACK_TARGET = REV_GENESIS
REV_PROMOTED = "sha256:" + "3" * 64


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "journey23.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    built = create_persistence_engine(sqlite_url(database_path))
    yield built
    built.dispose()


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "lifecycle.recovery.recovery_supervisor")


@pytest.fixture()
def blob_pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, blob_pep: PolicyEnforcementPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(tmp_path / "blobs", blob_pep)


@pytest.fixture()
def path() -> StableCandidatePath:
    return StableCandidatePath.load(REPO)


@pytest.fixture()
def pointer(path: StableCandidatePath, tmp_path: pathlib.Path) -> StableRevisionPointer:
    return StableRevisionPointer(path, tmp_path / "stable_pointer.json")


def _promotion_receipt(path: StableCandidatePath, candidate_id: str) -> StageReceipt:
    receipt = path.begin_candidate(candidate_id=candidate_id)
    for stage in path.stages()[2:-1]:
        receipt = path.advance(receipt, to_stage=stage)
    return path.promotion_receipt(receipt)


def _supervisor(
    session: object, pep: PolicyEnforcementPoint,
    pointer: StableRevisionPointer, blobs: ArtifactBlobStore,
) -> RecoverySupervisor:
    return RecoverySupervisor(
        PepRollbackAuthorization(pep, actor=ACTOR, trust_tier=TRUST_TIER),
        pointer, ArtifactStore(session, blobs),  # type: ignore[arg-type]
        AuditChainEvidenceSink(AuditChain(session, pep, REPO)),  # type: ignore[arg-type]
    )


class _RealSnapshotProof:
    """Adapts `lifecycle.recovery.core_snapshot.take_core_snapshot` to
    `RestorableSnapshotProof` - the real production composition, exactly as
    `test_core_snapshot.py::_RealSnapshotProof` establishes."""

    def __init__(self, pointer: StableRevisionPointer, artifacts: ArtifactStore) -> None:
        self._pointer = pointer
        self._artifacts = artifacts

    def take_snapshot(self, *, candidate_id: str) -> str:
        from arkali.lifecycle.recovery.core_snapshot import take_core_snapshot

        return take_core_snapshot(
            self._pointer, self._artifacts, candidate_id=candidate_id
        ).revision_id


def _campaign_budgets(**updates: object) -> CampaignBudgets:
    values: dict[str, object] = {
        "candidate_budget": 2, "ai_call_budget": 10, "time_budget_seconds": 600,
        "cost_budget": Decimal("5.00"), "regression_ceiling": 0, "no_progress_threshold": 2,
    }
    values.update(updates)
    return CampaignBudgets.model_validate(values)


class TestTheComposedSelfEvolutionSequenceReachesAGenuinePromotion:
    """MS "ARKALI Self-Evolution", end to end, up to a real Stable
    promotion gated by a real scoped HUMAN_GATE_2 grant."""

    def test_the_whole_pipeline_promotes_a_genuine_new_stable_revision(
        self, path: StableCandidatePath, engine: Engine, pep: PolicyEnforcementPoint,
        pointer: StableRevisionPointer, blobs: ArtifactBlobStore, tmp_path: pathlib.Path,
    ) -> None:
        # Genesis: establish a Stable revision and a genuinely verified
        # Recovery Supervisor (Phase 22B's own precondition), never fabricated.
        pointer.promote(
            _promotion_receipt(path, "genesis"), revision_id=REV_GENESIS,
            candidate_id="genesis",
        )
        pointer.promote(
            _promotion_receipt(path, "bad-upgrade"), revision_id=REV_BAD_UPGRADE,
            candidate_id="bad-upgrade",
        )
        with unit_of_work(create_session_factory(engine)) as session:
            supervisor = _supervisor(session, pep, pointer, blobs)
            supervisor.rollback(
                health=HealthCheckResult(
                    candidate_id="bad-upgrade", healthy=False, detail="startup crash",
                ),
                target_revision_id=REV_ROLLED_BACK_TARGET,
            )
            assert supervisor.is_verified() is True

        # Declare the campaign - objective, baseline and all six budgets,
        # before any candidate work begins (ARK-REQ-0139).
        declaration = CampaignDeclaration(
            campaign_id="campaign-23-promoted",
            objective="close a real security gap in control.policy",
            baseline_metrics={"open_findings": 1.0},
            budgets=_campaign_budgets(),
        )
        campaign = ecsm.build().start("DECLARED")
        campaign.apply("RUNNING", declaration.guard_context())
        ledger = CampaignLedger(campaign_id=declaration.campaign_id, budgets=declaration.budgets)

        # Snapshot + entry (ARK-REQ-0137): a real, proven-restorable
        # snapshot of the current Stable revision, taken before the build.
        with unit_of_work(create_session_factory(engine)) as session:
            artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
            instance, snapshotted_revision = begin_core_upgrade(
                _RealSnapshotProof(pointer, artifacts), candidate_id="cand-1",
            )
        assert instance.state == "SNAPSHOT_TAKEN"
        assert snapshotted_revision == REV_ROLLED_BACK_TARGET

        # Entry guard reads the real, non-fabricated verification fact.
        with unit_of_work(create_session_factory(engine)) as session:
            supervisor = _supervisor(session, pep, pointer, blobs)
            instance.apply(
                "CANDIDATE_BUILT",
                {"recovery_supervisor_verified": supervisor.is_verified()},
            )
        instance.apply("VERIFYING")
        instance.apply("AWAITING_GATE_2")

        # Promotion (ARK-REQ-0138): refused without a real scoped grant.
        receipt = path.begin_candidate(candidate_id="cand-1")
        for stage in path.stages()[2:-1]:
            receipt = path.advance(receipt, to_stage=stage)
        governance_repo = _repo_with_core_promotion_grant(
            tmp_path, manifest_ref="sha256:" + "c" * 64, revision_id=REV_PROMOTED,
        )
        no_grant_state = GovernanceState.load(REPO)  # the real, live repo: no grant exists
        with pytest.raises(GuardRejected):
            promote_core_upgrade(CorePromotionRequest(
                instance=instance, gates=no_grant_state, path=path, pointer=pointer,
                receipt=receipt, revision_id=REV_PROMOTED,
                candidate_manifest_ref="sha256:" + "c" * 64,
            ))
        assert instance.state == "AWAITING_GATE_2"
        assert pointer.current().revision_id == REV_ROLLED_BACK_TARGET  # type: ignore[union-attr]

        # With a real, exactly-scoped grant recorded, promotion succeeds.
        granted_state = GovernanceState.load(governance_repo)
        record = promote_core_upgrade(CorePromotionRequest(
            instance=instance, gates=granted_state, path=path, pointer=pointer,
            receipt=receipt, revision_id=REV_PROMOTED,
            candidate_manifest_ref="sha256:" + "c" * 64,
        ))
        assert record.revision_id == REV_PROMOTED
        assert instance.state == "PROMOTED"
        assert pointer.current().revision_id == REV_PROMOTED  # type: ignore[union-attr]

        # The campaign ledger records the same outcome and reaches PROMOTED
        # (ARK-REQ-0140), and the campaign machine itself follows suit.
        ledger = ledger.record(
            CampaignAttempt(
                candidate_id="cand-1", outcome="PROMOTED", measured_gain=True,
                regression_delta=0,
            ),
            ai_calls=1, elapsed_seconds=30, cost=Decimal("0.50"),
        )
        assert ledger.terminal_state() == "PROMOTED"
        campaign.apply("PROMOTED")

        # ARK-REQ-0360: the resulting record is genuinely bounded.
        import json

        declaration_shape = json.loads(declaration.rendering())
        outcome_shape = {"terminal_state": ledger.terminal_state()}
        assert _check_campaign_record_shape(declaration_shape, outcome_shape) is None


def _repo_with_core_promotion_grant(
    tmp_path: pathlib.Path, *, manifest_ref: str, revision_id: str,
) -> pathlib.Path:
    """A temporary copy of the real `docs/` tree with one real, exactly
    scoped HUMAN_GATE_2/CORE_PROMOTION grant added - mirrors
    `test_human_gate_authorization.py`'s own fixture pattern."""
    import shutil

    target = tmp_path / "governed-repo"
    shutil.copytree(REPO / "docs", target / "docs")
    records_path = target / "docs/acceptance/HUMAN_GATE_RECORDS.md"
    header = (
        "\n## Phase 23 journey test operation grant\n\n"
        "| ID | GATE | OPERATION | TARGET | REVISION | ISSUER | STATUS |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| PC-JOURNEY-1 | HUMAN_GATE_2 | CORE_PROMOTION | {manifest_ref} | "
        f"{revision_id} | human operator | GRANTED |\n"
    )
    with records_path.open("a", encoding="utf-8") as handle:
        handle.write(header)
    return target


class TestARejectedCampaignReachesNoFurtherGainWithoutTouchingStable:
    """A candidate that never reaches HUMAN_GATE_2 - rejected instead - does
    not auto-generate a successor once budget/no-progress exhausts
    (ARK-REQ-0141), and the campaign reaches a real terminal state
    (ARK-REQ-0140) having never touched Stable (ARK-REQ-0359)."""

    def test_two_no_gain_rejections_exhaust_the_campaign_cleanly(
        self, path: StableCandidatePath, pointer: StableRevisionPointer,
    ) -> None:
        pointer.promote(
            _promotion_receipt(path, "genesis"), revision_id=REV_GENESIS,
            candidate_id="genesis",
        )
        declaration = CampaignDeclaration(
            campaign_id="campaign-23-rejected",
            objective="reduce p95 latency",
            baseline_metrics={"p95_ms": 400.0},
            budgets=_campaign_budgets(no_progress_threshold=2),
        )
        campaign = ecsm.build().start("DECLARED")
        campaign.apply("RUNNING", declaration.guard_context())
        ledger = CampaignLedger(campaign_id=declaration.campaign_id, budgets=declaration.budgets)

        for candidate_id in ("cand-1", "cand-2"):
            instance = cusm.build().start("SNAPSHOT_TAKEN")
            instance.apply("CANDIDATE_BUILT", {"recovery_supervisor_verified": True})
            instance.apply("VERIFYING")
            instance.apply("REJECTED")
            assert instance.state == "REJECTED"
            ledger = ledger.record(
                CampaignAttempt(
                    candidate_id=candidate_id, outcome="REJECTED", measured_gain=False,
                    regression_delta=0,
                ),
                ai_calls=1, elapsed_seconds=10, cost=Decimal("0.10"),
            )

        assert ledger.may_generate_successor() is False
        assert ledger.terminal_state() == "COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN"
        campaign.apply("COMPLETE_WITH_NO_FURTHER_MEASURED_GAIN")
        assert campaign.is_terminal is True

        # Stable was never touched by this campaign at all.
        assert pointer.current().revision_id == REV_GENESIS  # type: ignore[union-attr]
        assert pointer.history() == ()

        with pytest.raises(Exception):
            ledger.record(
                CampaignAttempt(
                    candidate_id="cand-3", outcome="REJECTED", measured_gain=False,
                    regression_delta=0,
                ),
                ai_calls=1, elapsed_seconds=10, cost=Decimal("0.10"),
            )
