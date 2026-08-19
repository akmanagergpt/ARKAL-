"""Shared harness for the C-34 Operations telemetry test tiers (Phase 25).

Not a test module. REAL INFRASTRUCTURE ONLY: a real SQLite file migrated by
the real Alembic chain, a real PDP loaded from the authority map, real
`JobStore`/`JobRecovery`/`WorkflowExecutor` instances sharing one session -
the same discipline `tests/execution/durable_harness.py` and
`tests/execution/executor_harness.py` already established, combined because
Package 1's composed telemetry reads across both contexts in one call.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_contract import PolicyRequest
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.execution.durable.job_store import JobStore
from arkali.execution.durable.recovery import JobRecovery
from arkali.execution.workflow.executor import WorkflowExecutor
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

START = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)


class MovableClock:
    """A clock the test moves explicitly. Nothing here waits for real time."""

    def __init__(self, start: dt.datetime = START) -> None:
        self.now = start

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now = self.now + dt.timedelta(seconds=seconds)


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def vocabulary() -> GraphVocabulary:
    return GraphVocabulary.load(REPO)


@pytest.fixture()
def approval_gate() -> WorkflowApprovalGate:
    return WorkflowApprovalGate.load(REPO)


@pytest.fixture()
def clock() -> MovableClock:
    return MovableClock()


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "operations.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


class OperationsReopener:
    """Opens JobRecovery + WorkflowExecutor together, one shared engine/session
    per `with` block, a fresh engine each time - the same discipline
    `durable_harness.Reopener`/`executor_harness.ExecutorReopener` established.
    """

    def __init__(
        self,
        path: pathlib.Path,
        pdp: PolicyDecisionPoint,
        vocabulary: GraphVocabulary,
        approval_gate: WorkflowApprovalGate,
        clock: MovableClock,
    ) -> None:
        self._path = path
        self._pdp = pdp
        self._vocabulary = vocabulary
        self._approval_gate = approval_gate
        self._clock = clock

    def session(self):  # noqa: ANN201 - a context manager
        engine: Engine = create_persistence_engine(sqlite_url(self._path))
        uow = unit_of_work(create_session_factory(engine))
        outer = self

        class _Scope:
            def __enter__(self) -> tuple[JobRecovery, WorkflowExecutor, Engine, object]:
                session = uow.__enter__()
                pep = PolicyEnforcementPoint(outer._pdp, "execution.durable.execution")
                recovery = JobRecovery(session, pep, outer._clock)
                executor = WorkflowExecutor(
                    session, outer._pdp, outer._vocabulary, outer._approval_gate,
                    outer._clock,
                )
                return recovery, executor, engine, session

            def __exit__(self, *exc: object) -> bool:
                try:
                    return bool(uow.__exit__(*exc))
                finally:
                    engine.dispose()

        return _Scope()


@pytest.fixture()
def reopen(
    database_path: pathlib.Path,
    pdp: PolicyDecisionPoint,
    vocabulary: GraphVocabulary,
    approval_gate: WorkflowApprovalGate,
    clock: MovableClock,
) -> OperationsReopener:
    return OperationsReopener(database_path, pdp, vocabulary, approval_gate, clock)


def job_store_of(recovery: JobRecovery) -> JobStore:
    return recovery.execution.jobs


class PepReadAuthorization:
    """The real composition-root adapter for `telemetry.ReadAuthorization`.

    Constructs a real `PolicyRequest` and calls a real `PolicyEnforcementPoint`
    - the concrete implementation `surfaces.operations.telemetry` itself
    deliberately does not import (see that module's own docstring). Until
    Package 8 wires a real `surfaces.command` route to this function, this
    test-side adapter is the only place this Protocol is fulfilled - the
    same "no production caller yet" shape Phase 22B's own
    `RollbackAuthorization` adapter recorded honestly.
    """

    def __init__(self, pep: PolicyEnforcementPoint, *, trust_tier: str = "TRUST-0") -> None:
        self._pep = pep
        self._trust_tier = trust_tier

    def require_auto(self, *, actor: str) -> None:
        self._pep.require_auto(
            PolicyRequest(operation_class="READ_FILE", trust_tier=self._trust_tier, actor=actor)
        )
