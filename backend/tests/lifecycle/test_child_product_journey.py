"""Phase 24 composed journey: the real C-36 "Product Evolution SDK" sequence
against a real, deployed AI-Native Self-Evolving child product.

MS "AI-Native Child Products": "Admin Request -> Impact -> Working Copy ->
Candidate -> Tests -> Approval -> Promotion/Rollback." Every step below runs
against a real isolated filesystem workspace (the real, unmodified Phase 12
`WorkspaceAuthority`), a real SQLite database (via the real Alembic chain),
the real C-14 `ArtifactStore` and C-15 `AuditChain`, and the real scoped
`HUMAN_GATE_3` grant mechanism (`GovernanceState.operation_grant`) - matching
this build's own established discipline for a composed real-authority
journey (`test_phase_23_journey.py`).

Two full evolution cycles are run to real, different outcomes: the first
candidate is refused promotion with no grant, then promoted once a real
scoped grant exists; a second, later candidate is promoted the same way;
the product is then rolled back to the first promoted version, and the
full lineage/evidence history is verified intact throughout - no data
lost, no content fabricated, no candidate promoted without its own real
grant.
"""

from __future__ import annotations

import pathlib
import shutil
from collections.abc import Iterator
from decimal import Decimal

import pytest
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from alembic import command
from arkali.acceptance.governance_state import GovernanceState
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.engineering.candidate.workspace import WorkspaceAuthority
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.evidence.audit.chain import AuditChain, EvidenceInput
from arkali.kernel.contracts.content_address import address_of
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.evolution.campaign_declaration import CampaignBudgets
from arkali.lifecycle.evolution.child_product_campaign import (
    begin_child_product_campaign,
    declare_child_product_campaign,
)
from arkali.lifecycle.evolution.child_product_identity import (
    ChildProductIdentity,
    ChildProductMode,
)
from arkali.lifecycle.evolution.child_product_promotion import (
    GATE_3,
    PROMOTE_CHILD_PRODUCT_OPERATION,
    ChildProductAcceptanceRecord,
    _child_promotion_revision_identity,
    _child_promotion_target_identity,
    authorize_child_product_promotion,
    promote_child_product,
)
from arkali.lifecycle.evolution.child_product_rollback import rollback_child_product
from arkali.lifecycle.evolution.child_product_version import ChildProductVersionLineage
from arkali.lifecycle.evolution.child_product_workspace import (
    allocate_child_product_workspace,
)
from arkali.lifecycle.evolution.errors import ChildProductPromotionNotAuthorizedError

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
RECORDS = "docs/acceptance/HUMAN_GATE_RECORDS.md"
OPERATION_HEADER = (
    "| ID | GATE | OPERATION | TARGET | REVISION | ISSUER | STATUS |\n"
    "|---|---|---|---|---|---|---|\n"
)


def _budgets() -> CampaignBudgets:
    return CampaignBudgets(
        candidate_budget=5, ai_call_budget=20, time_budget_seconds=3600,
        cost_budget=Decimal("10.00"), regression_ceiling=0, no_progress_threshold=3,
    )


@pytest.fixture()
def product() -> ChildProductIdentity:
    return ChildProductIdentity(
        product_id="acme-task-tracker",
        name="Acme Task Tracker",
        mode=ChildProductMode.AI_NATIVE_SELF_EVOLVING,
    )


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "journey24.db"
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
def blob_pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")


@pytest.fixture()
def audit_pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "lifecycle.evolution.child_product_journey")


@pytest.fixture()
def blobs(tmp_path: pathlib.Path, blob_pep: PolicyEnforcementPoint) -> ArtifactBlobStore:
    return ArtifactBlobStore(tmp_path / "blobs", blob_pep)


@pytest.fixture()
def workspace_authority(tmp_path: pathlib.Path) -> WorkspaceAuthority:
    return WorkspaceAuthority(tmp_path / "workspaces")


def _grant_repo(tmp_path: pathlib.Path, records_text: str, *, label: str) -> pathlib.Path:
    """A real, isolated copy of docs/ with only HUMAN_GATE_RECORDS.md
    replaced - the identical fixture discipline
    test_core_promotion_gate_scope.py already established for HUMAN_GATE_2.
    No accepted repository state is touched. `label` gives each call within
    one test its own directory - this journey records several different
    grant states in sequence and each must stay independently inspectable.
    """
    target = tmp_path / f"grant-repo-{label}"
    shutil.copytree(REPO / "docs", target / "docs")
    (target / RECORDS).write_text(records_text, encoding="utf-8")
    return target


def _write_candidate(
    authority: WorkspaceAuthority, product: ChildProductIdentity, *,
    campaign_id: str, seed: pathlib.Path, content: bytes,
) -> str:
    """Real filesystem: allocate an isolated working copy, write the real
    candidate content into it, return the content's own real address."""
    handle = allocate_child_product_workspace(
        authority, product, campaign_id=campaign_id, stable_snapshot=seed,
    )
    handle.write("product.py", content)
    assert (handle.root / "snapshot").exists()
    return address_of(content)


def _register_evidence(
    session: Session, blobs: ArtifactBlobStore, audit_pep: PolicyEnforcementPoint,
    *, payload: bytes, task_id: str, requirement_id: str, contract_id: str,
) -> str:
    """Real C-14 artifact + real C-15 evidence row - the composition-root
    registration Package 2/5's own docstrings describe, exercised for real
    here for the first time."""
    artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
    artifact_id = artifacts.register(
        payload,
        ProvenanceInput(
            producer_agent="lifecycle.evolution.child_product_journey",
            provider_model="none", task_id=task_id,
            specification_version=contract_id, context_hash=address_of(payload),
        ),
    )
    chain = AuditChain(session, audit_pep, REPO)
    record = chain.append(
        EvidenceInput(
            requirement_id=requirement_id, artifact_id=artifact_id,
            producer="lifecycle.evolution.child_product_journey", result="PASS",
            contract_id=contract_id, test_id=task_id,
        )
    )
    return record.record_hash


class TestComposedChildProductEvolutionJourney:
    def test_the_full_two_cycle_journey(
        self,
        product: ChildProductIdentity,
        engine: Engine,
        workspace_authority: WorkspaceAuthority,
        blobs: ArtifactBlobStore,
        audit_pep: PolicyEnforcementPoint,
        tmp_path: pathlib.Path,
    ) -> None:
        session_factory = create_session_factory(engine)
        seed = tmp_path / "seed"
        seed.mkdir()

        # ---- Cycle 1: Admin Request -> Impact -> Working Copy -> Candidate
        declaration_1 = declare_child_product_campaign(
            product, objective="add recurring tasks",
            baseline_metrics={"feature_count": 4.0},
            budgets=_budgets(),
        )
        campaign_instance_1 = begin_child_product_campaign(declaration_1)
        assert campaign_instance_1.state == "RUNNING"

        candidate_1_ref = _write_candidate(
            workspace_authority, product, campaign_id=declaration_1.campaign_id,
            seed=seed, content=b"def add_recurring_task(): ...\n",
        )
        acceptance_1 = ChildProductAcceptanceRecord(
            candidate_ref=candidate_1_ref, command="pytest generated-suite -k recurring",
            exit_code=0,
        )

        # ---- Tests/Acceptance passed. Promotion requested with NO grant: refused.
        no_grant_repo = _grant_repo(tmp_path, OPERATION_HEADER, label="none")
        no_grant_state = GovernanceState.load(no_grant_repo)
        lineage = ChildProductVersionLineage(product_ref=product.product_ref)
        with pytest.raises(ChildProductPromotionNotAuthorizedError):
            promote_child_product(
                no_grant_state, product, lineage, candidate_ref=candidate_1_ref,
                campaign_id=declaration_1.campaign_id, acceptance=acceptance_1,
            )
        assert lineage.versions == ()  # untouched by the refusal

        # ---- A real scoped HUMAN_GATE_3 grant is recorded for this exact candidate.
        context_probe = authorize_child_product_promotion(
            no_grant_state, product, lineage, candidate_ref=candidate_1_ref,
        )
        assert context_probe == {"human_gate_3_recorded": False}

        # Derive the real target/revision identity the same way the
        # promotion path itself will, so the grant names the exact subject.
        target_id = _child_promotion_target_identity(product, candidate_1_ref)
        revision_id = _child_promotion_revision_identity(None, candidate_1_ref)
        grant_text = OPERATION_HEADER + (
            f"| PC-J1 | {GATE_3} | {PROMOTE_CHILD_PRODUCT_OPERATION} | "
            f"{target_id} | {revision_id} | human operator | GRANTED |\n"
        )
        granted_repo = _grant_repo(tmp_path, grant_text, label="v1")
        granted_state = GovernanceState.load(granted_repo)

        promoted_lineage = promote_child_product(
            granted_state, product, lineage, candidate_ref=candidate_1_ref,
            campaign_id=declaration_1.campaign_id, acceptance=acceptance_1,
        )
        assert promoted_lineage.current is not None
        assert promoted_lineage.current.content_ref == candidate_1_ref
        first_promoted_ref = promoted_lineage.current.version_ref

        # ---- Real evidence: the promotion is registered as a real C-14/C-15 record.
        with unit_of_work(session_factory) as session:
            record_hash_1 = _register_evidence(
                session, blobs, audit_pep,
                payload=promoted_lineage.rendering(), task_id=product.product_id,
                requirement_id="ARK-REQ-0132", contract_id="C-36",
            )
        assert record_hash_1

        # ---- Cycle 2: a second, later evolution request on the now-promoted product.
        declaration_2 = declare_child_product_campaign(
            product, objective="add task search",
            baseline_metrics={"feature_count": 5.0}, budgets=_budgets(),
        )
        begin_child_product_campaign(declaration_2)
        candidate_2_ref = _write_candidate(
            workspace_authority, product, campaign_id=declaration_2.campaign_id,
            seed=seed, content=b"def add_recurring_task(): ...\ndef search(): ...\n",
        )
        acceptance_2 = ChildProductAcceptanceRecord(
            candidate_ref=candidate_2_ref, command="pytest generated-suite -k search",
            exit_code=0,
        )
        target_2 = _child_promotion_target_identity(product, candidate_2_ref)
        revision_2 = _child_promotion_revision_identity(first_promoted_ref, candidate_2_ref)
        grant_2_text = OPERATION_HEADER + (
            f"| PC-J2 | {GATE_3} | {PROMOTE_CHILD_PRODUCT_OPERATION} | "
            f"{target_2} | {revision_2} | human operator | GRANTED |\n"
        )
        granted_repo_2 = _grant_repo(tmp_path, grant_2_text, label="v2")
        granted_state_2 = GovernanceState.load(granted_repo_2)

        twice_promoted = promote_child_product(
            granted_state_2, product, promoted_lineage, candidate_ref=candidate_2_ref,
            campaign_id=declaration_2.campaign_id, acceptance=acceptance_2,
        )
        assert twice_promoted.current is not None
        assert twice_promoted.current.content_ref == candidate_2_ref
        assert len(twice_promoted.versions) == 2

        # ---- The v1 grant does not authorize the v2 promotion (no leak).
        stale_state = GovernanceState.load(granted_repo)  # only the v1 grant
        with pytest.raises(ChildProductPromotionNotAuthorizedError):
            promote_child_product(
                stale_state, product, promoted_lineage, candidate_ref=candidate_2_ref,
                campaign_id=declaration_2.campaign_id, acceptance=acceptance_2,
            )

        # ---- Rollback: something in v2 broke search; restore v1. No fresh
        # HUMAN_GATE_3 needed - v1's own content was already approved once.
        rolled_back, receipt = rollback_child_product(
            twice_promoted, product, target_version_ref=first_promoted_ref,
            reason="v2 search regressed recurring-task listing",
        )
        assert rolled_back.current is not None
        assert rolled_back.current.content_ref == candidate_1_ref  # restored, not new
        assert rolled_back.current.is_rollback is True
        assert receipt.restored_content_ref == candidate_1_ref
        assert receipt.reason == "v2 search regressed recurring-task listing"

        with unit_of_work(session_factory) as session:
            record_hash_2 = _register_evidence(
                session, blobs, audit_pep,
                payload=receipt.rendering(), task_id=product.product_id,
                requirement_id="ARK-REQ-0358", contract_id="C-36",
            )
        assert record_hash_2 != record_hash_1

        # ---- Full history/evidence verification: nothing was lost.
        assert len(rolled_back.versions) == 3
        assert rolled_back.versions[0].content_ref == candidate_1_ref
        assert rolled_back.versions[1].content_ref == candidate_2_ref
        assert rolled_back.versions[2].content_ref == candidate_1_ref
        with unit_of_work(session_factory) as session:
            chain = AuditChain(session, audit_pep, REPO)
            recorded = chain.records()
        assert len(recorded) == 2
        assert {r.record_hash for r in recorded} == {record_hash_1, record_hash_2}
