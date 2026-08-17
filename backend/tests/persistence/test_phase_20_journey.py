"""The composed Phase 20 real-authority journey.

Register denominator -> the real declared migration chain carries no known
data-loss risk (ARK-REQ-0337, both as `acceptance.engine`'s independent check
and as the Impact step of a real sequence run) -> the full nine-step
`MigrationSafetySequence` against a real SQLite target with real data,
composing Phase 5's `RecoveryService`/`BackupRestore` machine, Phase 4's real
PDP, and Phase 19's `WorkflowApprovalGate` (ARK-REQ-0151, ARK-REQ-0336) ->
`APPLY_MIGRATION` is gated by HUMAN_GATE_6 exactly on real-or-stable-data
targets, proven against the real authority map (ARK-REQ-0152). No AI provider
is contacted anywhere in this journey.
"""

from __future__ import annotations

import pathlib
from typing import Final

import pytest
from sqlalchemy import Engine

from arkali.acceptance.checker import PhaseGateChecker
from arkali.acceptance.migration_release_check import _evaluate_migration_data_loss_risk
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.control.specification.register_parser import RequirementRegister
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import (
    applied_revision,
    declared_migrations,
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
    STEP_ROLLBACK_POINT,
    STEPS,
    MigrationStepState,
)

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
BACKEND: Final[pathlib.Path] = REPO / "backend"
SEED_REVISION: Final[str] = "0002_project_registry"


class FakeHumanGateSource:
    """Structurally satisfies `HumanGateSource`, never `GovernanceState`."""

    def __init__(self, accepted: frozenset[str] = frozenset()) -> None:
        self._accepted = accepted

    @property
    def accepted_human_gates(self) -> frozenset[str]:
        return self._accepted


def test_step_1_the_real_register_denominator() -> None:
    register = RequirementRegister.load(REPO)
    phase20 = {r.req_id for r in register.for_phase("20")}
    assert phase20 == {
        "ARK-REQ-0151", "ARK-REQ-0152", "ARK-REQ-0336", "ARK-REQ-0337",
    }
    owners = {r.req_id: r.owning_component for r in register.for_phase("20")}
    assert owners["ARK-REQ-0151"] == "lifecycle.recovery"
    assert owners["ARK-REQ-0336"] == "lifecycle.recovery"
    assert owners["ARK-REQ-0152"] == "control.policy"
    assert owners["ARK-REQ-0337"] == "acceptance.engine"
    assert all(r.is_mandatory for r in register.for_phase("20"))


def test_step_2_state_machine_count_stays_twelve() -> None:
    """The nine-step sequence is an orchestration, not a new canonical machine."""
    from arkali.control.architecture.authority_map import AuthorityMap
    authority_map = AuthorityMap.load(REPO)
    assert len(authority_map.state_machine_authorities) == 12


def test_step_3_ark_req_0337_over_the_real_shipping_chain() -> None:
    """`acceptance.engine`'s own independent check, over the real chain.

    Asserts the analysed-revision count explicitly rather than only `passed`:
    a vacuous "no migrations directory yet" PASS (the shape this check
    actually returned before `BACKEND_RELPATH` was added - the outer repo
    root, not the backend root, is what every `acceptance.engine` caller
    holds) would satisfy `passed is True` for the wrong reason.
    """
    chain = declared_migrations(BACKEND)
    passed, summary, _detail = _evaluate_migration_data_loss_risk(REPO)
    assert passed is True, summary
    assert str(len(chain)) in summary, summary
    assert "no migrations directory" not in summary


def test_step_4_the_phase_gate_checker_carries_the_data_loss_risk_check() -> None:
    checker = PhaseGateChecker(REPO)
    result = checker.check_migration_data_loss_risk()
    assert result.state.value == "PASS"
    assert "no migrations directory" not in result.summary


class TestTheComposedMigrationSafetyJourney:
    """Each `test_condition_*` proves one VDC "Migration safety" bullet
    against the real composed `MigrationSafetySequence`."""

    @pytest.fixture()
    def pdp(self) -> PolicyDecisionPoint:
        return PolicyDecisionPoint.load(REPO)

    @pytest.fixture()
    def pep(self, pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
        return PolicyEnforcementPoint(pdp, "test.phase_20_journey")

    @pytest.fixture()
    def approval_gate(self) -> WorkflowApprovalGate:
        return WorkflowApprovalGate.load(REPO)

    @pytest.fixture()
    def sequence(
        self, pep: PolicyEnforcementPoint, approval_gate: WorkflowApprovalGate,
    ) -> MigrationSafetySequence:
        return MigrationSafetySequence(pep, approval_gate, RecoveryService(pep), BACKEND)

    @pytest.fixture()
    def database_path(self, tmp_path: pathlib.Path) -> pathlib.Path:
        return tmp_path / "journey.db"

    @pytest.fixture()
    def engine(self, database_path: pathlib.Path):
        run_upgrade(sqlite_url(database_path), BACKEND, SEED_REVISION)
        built = create_persistence_engine(sqlite_url(database_path))
        with unit_of_work(create_session_factory(built)) as session:
            ProjectRegistry(session).create_project("journey-project", "Real Data")
        yield built
        built.dispose()

    @staticmethod
    def _project_present(engine: Engine) -> bool:
        with unit_of_work(create_session_factory(engine)) as session:
            return ProjectRegistry(session).get("journey-project") is not None

    def _request(
        self, engine: Engine, database_path: pathlib.Path, workspace: pathlib.Path,
        *, targets_real_or_stable_data: bool = False,
        human_gates: FakeHumanGateSource | None = None,
    ) -> MigrationSafetyRequest:
        target = head_revision(BACKEND)
        return MigrationSafetyRequest(
            engine=engine, database_url=sqlite_url(database_path),
            workspace=workspace, backup_id="journey-1",
            application_tests=self._project_present,
            post_migration_verifier=self._project_present,
            human_gates=human_gates or FakeHumanGateSource(),
            human_actor="human_reviewer", human_decision="APPROVED",
            human_approval_revision_hash=target,
            targets_real_or_stable_data=targets_real_or_stable_data,
        )

    def test_condition_1_all_nine_steps_run_in_canonical_order(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        result = sequence.run(self._request(engine, database_path, tmp_path / "ws"))
        assert [s.step for s in result.steps] == list(STEPS)
        assert all(s.state is MigrationStepState.PASS for s in result.steps), result.render()

    def test_condition_2_real_data_survives_the_forward_migration(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        assert applied_revision(engine) == SEED_REVISION
        sequence.run(self._request(engine, database_path, tmp_path / "ws"))
        assert applied_revision(engine) == head_revision(BACKEND)
        assert self._project_present(engine) is True

    def test_condition_3_apply_to_real_or_stable_data_needs_human_gate_6(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        blocked = sequence.run(self._request(
            engine, database_path, tmp_path / "ws",
            targets_real_or_stable_data=True, human_gates=FakeHumanGateSource(),
        ))
        apply_result = next(s for s in blocked.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.BLOCKED
        assert "HUMAN_GATE_6" in apply_result.summary
        assert applied_revision(engine) == SEED_REVISION

    def test_condition_4_a_recorded_human_gate_6_permits_real_data_apply(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        result = sequence.run(self._request(
            engine, database_path, tmp_path / "ws",
            targets_real_or_stable_data=True,
            human_gates=FakeHumanGateSource(frozenset({"HUMAN_GATE_6"})),
        ))
        apply_result = next(s for s in result.steps if s.step == STEP_APPLY)
        assert apply_result.state is MigrationStepState.PASS
        assert applied_revision(engine) == head_revision(BACKEND)

    def test_condition_5_the_rollback_point_is_proven_by_a_real_restore(
        self, sequence: MigrationSafetySequence, engine: Engine,
        database_path: pathlib.Path, tmp_path: pathlib.Path,
    ) -> None:
        result = sequence.run(self._request(engine, database_path, tmp_path / "ws"))
        rollback = next(s for s in result.steps if s.step == STEP_ROLLBACK_POINT)
        assert rollback.state is MigrationStepState.PASS
        assert result.rollback_point_backup_id == "journey-1"
