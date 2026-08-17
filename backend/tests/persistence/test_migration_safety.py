"""Migration safety sequence evidence (ARK-REQ-0151, ARK-REQ-0336, ARK-REQ-0152).

The composed nine-step sequence, proven against a real SQLite target with a
real PDP, a real `WorkflowApprovalGate` and the real `RecoveryService`/
`BackupRestore` machine from Phase 5. `human_gates` is a plain object
satisfying `HumanGateSource` structurally, never `acceptance.engine`
imported - proving the `Protocol` composition works without that edge.
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import (
    applied_revision,
    head_revision,
    run_upgrade,
)
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.lifecycle.recovery.backup_service import RecoveryService
from arkali.lifecycle.recovery.migration_safety import (
    MigrationSafetyRequest,
    MigrationSafetySequence,
)
from arkali.lifecycle.recovery.migration_safety_types import (
    STEP_APPLY,
    STEP_IMPACT,
    STEPS,
    MigrationStepState,
)

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

APPROVED = "APPROVED"
REJECTED = "REJECTED"
AUTOMATED_ACTOR = "workflow"
HUMAN_ACTOR = "human_reviewer"
#: The starting revision every fixture engine carries real data at, so the
#: safety sequence has an actual forward migration (to head) to prove data
#: through, not an empty file with no prior schema at all.
SEED_REVISION = "0002_project_registry"


class FakeHumanGateSource:
    """Structurally satisfies `HumanGateSource`. Not `GovernanceState`."""

    def __init__(self, accepted: frozenset[str] = frozenset()) -> None:
        self._accepted = accepted

    @property
    def accepted_human_gates(self) -> frozenset[str]:
        return self._accepted


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "lifecycle.recovery.migration_safety")


@pytest.fixture()
def approval_gate() -> WorkflowApprovalGate:
    return WorkflowApprovalGate.load(REPO)


@pytest.fixture()
def recovery(pep: PolicyEnforcementPoint) -> RecoveryService:
    return RecoveryService(pep)


@pytest.fixture()
def sequence(
    pep: PolicyEnforcementPoint, approval_gate: WorkflowApprovalGate,
    recovery: RecoveryService,
) -> MigrationSafetySequence:
    return MigrationSafetySequence(pep, approval_gate, recovery, BACKEND)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "target.db"


@pytest.fixture()
def engine(database_path: pathlib.Path) -> Iterator[Engine]:
    run_upgrade(sqlite_url(database_path), BACKEND, SEED_REVISION)
    built = create_persistence_engine(sqlite_url(database_path))
    with unit_of_work(create_session_factory(built)) as session:
        ProjectRegistry(session).create_project("prj-a", "State A")
    yield built
    built.dispose()


def project_a_present(engine: Engine) -> bool:
    with unit_of_work(create_session_factory(engine)) as session:
        return ProjectRegistry(session).get("prj-a") is not None


def default_request(
    engine: Engine, database_path: pathlib.Path, workspace: pathlib.Path,
    *, targets_real_or_stable_data: bool = False,
    human_gates: FakeHumanGateSource | None = None,
    human_decision: str = APPROVED, human_actor: str = HUMAN_ACTOR,
) -> MigrationSafetyRequest:
    target = head_revision(BACKEND)
    return MigrationSafetyRequest(
        engine=engine, database_url=sqlite_url(database_path),
        workspace=workspace, backup_id="ms-1",
        application_tests=project_a_present,
        post_migration_verifier=project_a_present,
        human_gates=human_gates or FakeHumanGateSource(),
        human_actor=human_actor, human_decision=human_decision,
        human_approval_revision_hash=target,
        target_revision="head",
        targets_real_or_stable_data=targets_real_or_stable_data,
    )


class TestTheFullSequenceOnDevData:
    """A dev/test target with an ordinary local human confirmation applies
    cleanly all the way through Rollback Point - no HUMAN_GATE_6 recording
    is needed because `targets_real_or_stable_data` is False."""

    def test_every_step_passes_in_canonical_order(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(engine, database_path, tmp_path / "ws")
        result = sequence.run(request)
        assert [s.step for s in result.steps] == list(STEPS)
        assert all(s.state is MigrationStepState.PASS for s in result.steps), result.render()
        assert result.applied is True
        assert result.blocked is False
        assert result.failed is False
        assert result.rollback_point_backup_id == "ms-1"

    def test_the_real_target_actually_reaches_head(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(engine, database_path, tmp_path / "ws")
        sequence.run(request)
        assert applied_revision(engine) == head_revision(BACKEND)
        assert project_a_present(engine) is True

    def test_the_real_target_starts_at_the_seed_revision_not_head(
        self, engine: Engine,
    ) -> None:
        """The fixture engine carries real data at an earlier revision before
        the sequence runs, so the "reaches head" assertions above are evidence
        of a genuine forward migration, not a target already there."""
        assert applied_revision(engine) == SEED_REVISION
        assert SEED_REVISION != head_revision(BACKEND)


class TestKnownDataLossRiskBlocksTheWholeSequence:
    """ARK-REQ-0151 / VDC "Known data-loss risk blocks release": a destructive
    pending migration stops the sequence at Impact, and nothing after it runs."""

    def test_a_synthetic_destructive_chain_stops_at_impact(
        self, tmp_path: pathlib.Path, pep: PolicyEnforcementPoint,
        approval_gate: WorkflowApprovalGate, recovery: RecoveryService,
        engine: Engine, database_path: pathlib.Path,
    ) -> None:
        fake_backend = tmp_path / "fake_backend"
        versions = fake_backend / "alembic" / "versions"
        versions.mkdir(parents=True)
        (fake_backend / "alembic.ini").write_text(
            "[alembic]\nscript_location = alembic\n", encoding="utf-8"
        )
        (versions / "0001_root.py").write_text(
            'revision = "0001_root"\ndown_revision = None\n'
            'direction = "FORWARD"\n'
            "def upgrade() -> None:\n    op.drop_table('widget')\n"
            "def downgrade() -> None:\n    pass\n",
            encoding="utf-8",
        )
        sequence = MigrationSafetySequence(pep, approval_gate, recovery, fake_backend)
        request = default_request(engine, database_path, tmp_path / "ws")
        result = sequence.run(request)
        impact = next(s for s in result.steps if s.step == STEP_IMPACT)
        assert impact.state is MigrationStepState.FAIL
        assert "drop_table" in impact.detail
        remaining = [s for s in result.steps if s.step != STEP_IMPACT]
        assert all(s.state is MigrationStepState.BLOCKED for s in remaining)
        assert result.applied is False
        assert applied_revision(engine) == SEED_REVISION


class TestApplyIsGatedByPolicyAndApproval:
    def test_an_automated_actor_can_never_authorise_apply(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(
            engine, database_path, tmp_path / "ws", human_actor=AUTOMATED_ACTOR
        )
        result = sequence.run(request)
        apply_result = next(s for s in result.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.BLOCKED
        assert result.applied is False
        assert applied_revision(engine) == SEED_REVISION

    def test_a_rejected_decision_can_never_authorise_apply(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(
            engine, database_path, tmp_path / "ws", human_decision=REJECTED
        )
        result = sequence.run(request)
        apply_result = next(s for s in result.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.BLOCKED
        assert applied_revision(engine) == SEED_REVISION

    def test_an_approval_bound_to_a_different_revision_never_authorises(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(engine, database_path, tmp_path / "ws")
        stale = MigrationSafetyRequest(
            engine=request.engine, database_url=request.database_url,
            workspace=request.workspace, backup_id=request.backup_id,
            application_tests=request.application_tests,
            post_migration_verifier=request.post_migration_verifier,
            human_gates=request.human_gates, human_actor=request.human_actor,
            human_decision=request.human_decision,
            human_approval_revision_hash="0001_persistence_base_schema",
            target_revision="head",
        )
        result = sequence.run(stale)
        apply_result = next(s for s in result.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.BLOCKED
        assert applied_revision(engine) == SEED_REVISION


class TestHumanGate6OnRealOrStableData:
    """ARK-REQ-0152: real-or-stable-data APPLY additionally needs a recorded
    HUMAN_GATE_6, read only through `HumanGateSource` - never inferred."""

    def test_targeting_real_data_without_a_recorded_gate_blocks_apply(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(
            engine, database_path, tmp_path / "ws", targets_real_or_stable_data=True,
            human_gates=FakeHumanGateSource(frozenset()),
        )
        result = sequence.run(request)
        apply_result = next(s for s in result.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.BLOCKED
        assert "HUMAN_GATE_6" in apply_result.summary
        assert applied_revision(engine) == SEED_REVISION

    def test_targeting_real_data_with_the_gate_recorded_permits_apply(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(
            engine, database_path, tmp_path / "ws", targets_real_or_stable_data=True,
            human_gates=FakeHumanGateSource(frozenset({"HUMAN_GATE_6"})),
        )
        result = sequence.run(request)
        apply_result = next(s for s in result.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.PASS
        assert applied_revision(engine) == head_revision(BACKEND)

    def test_dev_data_needs_no_recorded_gate_at_all(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(
            engine, database_path, tmp_path / "ws", targets_real_or_stable_data=False,
            human_gates=FakeHumanGateSource(frozenset()),
        )
        result = sequence.run(request)
        apply_result = next(s for s in result.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.PASS


class TestApplicationTestsCanStopTheSequence:
    def test_a_failing_application_test_blocks_before_apply(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        request = default_request(engine, database_path, tmp_path / "ws")
        failing = MigrationSafetyRequest(
            engine=request.engine, database_url=request.database_url,
            workspace=request.workspace, backup_id=request.backup_id,
            application_tests=lambda _engine: False,
            post_migration_verifier=request.post_migration_verifier,
            human_gates=request.human_gates, human_actor=request.human_actor,
            human_decision=request.human_decision,
            human_approval_revision_hash=request.human_approval_revision_hash,
        )
        result = sequence.run(failing)
        assert result.applied is False
        assert applied_revision(engine) == SEED_REVISION
        apply_result = next(s for s in result.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.BLOCKED
