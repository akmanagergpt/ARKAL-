"""Shared harness for the C-20 workflow executor test tiers (Phase 17 Package 5).

Not a test module - the `module <= 400 logical lines` budget only scopes
`backend/arkali/`, but splitting evidence across focused test modules over one
harness is still the established idiom (`durable_harness.py`,
`workflow_harness.py`).

REAL INFRASTRUCTURE ONLY. A real SQLite file migrated by the real Alembic
chain, a real PDP loaded from the authority map, a real `GraphVocabulary` and
`WorkflowApprovalGate`, and a real `WorkflowExecutor` composing real
`execution.durable` job infrastructure.
"""

from __future__ import annotations

import datetime as dt
import pathlib

import pytest
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.workflow_approval import WorkflowApprovalGate
from arkali.execution.workflow.executor import WorkflowExecutor
from arkali.execution.workflow.graph_model import (
    SemverBump,
    WorkflowEdge,
    WorkflowGraphDocument,
    WorkflowNode,
)
from arkali.execution.workflow.graph_store import WorkflowGraphStore
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

START = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC)


class MovableClock:
    def __init__(self, start: dt.datetime = START) -> None:
        self.now = start

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now = self.now + dt.timedelta(seconds=seconds)


class ExecutorReopener:
    """Opens a `WorkflowExecutor` (and a `WorkflowGraphStore` to publish
    through) over one file, with a new engine each time."""

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
        self.opens = 0

    def session(self):  # noqa: ANN201 - a context manager
        self.opens += 1
        engine: Engine = create_persistence_engine(sqlite_url(self._path))
        uow = unit_of_work(create_session_factory(engine))
        outer = self

        class _Scope:
            def __enter__(self) -> tuple[WorkflowExecutor, WorkflowGraphStore, object]:
                session = uow.__enter__()
                executor = WorkflowExecutor(
                    session, outer._pdp, outer._vocabulary, outer._approval_gate, outer._clock
                )
                store = WorkflowGraphStore(
                    session,
                    PolicyEnforcementPoint(outer._pdp, "execution.workflow.graph_store"),
                    outer._vocabulary,
                    outer._clock,
                )
                return executor, store, session

            def __exit__(self, *exc: object) -> bool:
                try:
                    return bool(uow.__exit__(*exc))
                finally:
                    engine.dispose()

        return _Scope()


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture(scope="module")
def vocabulary() -> GraphVocabulary:
    return GraphVocabulary.load(REPO)


@pytest.fixture(scope="module")
def approval_gate() -> WorkflowApprovalGate:
    return WorkflowApprovalGate.load(REPO)


@pytest.fixture()
def clock() -> MovableClock:
    return MovableClock()


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "executor.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def reopen(
    database_path: pathlib.Path,
    pdp: PolicyDecisionPoint,
    vocabulary: GraphVocabulary,
    approval_gate: WorkflowApprovalGate,
    clock: MovableClock,
) -> ExecutorReopener:
    return ExecutorReopener(database_path, pdp, vocabulary, approval_gate, clock)


def node(
    node_id: str, kind: str, *, construct: str | None = None,
    parameters: dict[str, object] | None = None,
) -> WorkflowNode:
    return WorkflowNode(
        node_id=node_id, kind=kind, control_construct=construct,
        label=node_id, parameters=parameters or {},
    )


def edge(edge_id: str, source: str, target: str, condition: str | None = None) -> WorkflowEdge:
    return WorkflowEdge(
        edge_id=edge_id, source_node_id=source, target_node_id=target, condition=condition
    )


def build_document(
    vocabulary: GraphVocabulary,
    workflow_id: str,
    nodes: list[WorkflowNode],
    edges: list[WorkflowEdge],
) -> WorkflowGraphDocument:
    return WorkflowGraphDocument.build(vocabulary, workflow_id, nodes=nodes, edges=edges)


def publish(store: WorkflowGraphStore, document: WorkflowGraphDocument) -> None:
    store.publish(document, semver_bump=SemverBump.PATCH)
