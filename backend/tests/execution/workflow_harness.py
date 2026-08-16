"""Shared harness for the C-20 workflow-graph persistence test tiers.

Not a test module. `module <= 400 logical lines` is a real architecture budget;
Package 2 evidence is split across test modules over one harness, following the
`tests/execution/durable_harness.py` precedent this mirrors closely.

REAL INFRASTRUCTURE ONLY. A real SQLite file migrated by the real Alembic
chain, a real PDP loaded from the authority map, a real PEP, and the real
`GraphVocabulary` parsed from the live VDC document.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import shutil

import pytest
import yaml
from alembic.config import Config
from sqlalchemy import Engine

from alembic import command
from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.execution.workflow.graph_model import WorkflowEdge, WorkflowGraphDocument, WorkflowNode
from arkali.execution.workflow.graph_store import WorkflowGraphStore
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

START = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.UTC)

PDP_DOCUMENTS = (
    "docs/canonical/AUTHORITY_MAP.yaml",
    "docs/canonical/SECURITY_ARCHITECTURE.md",
    "docs/canonical/ARCHITECTURE.md",
)


class MovableClock:
    def __init__(self, start: dt.datetime = START) -> None:
        self.now = start

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now = self.now + dt.timedelta(seconds=seconds)


class Reopener:
    """Opens a `WorkflowGraphStore` over one file, with a new engine each time.

    A value read in one block and asserted in the next came off the disk, not
    off a session cache - the same discipline `durable_harness.Reopener` uses.
    """

    def __init__(
        self,
        path: pathlib.Path,
        pep: PolicyEnforcementPoint,
        vocabulary: GraphVocabulary,
        clock: MovableClock,
    ) -> None:
        self._path = path
        self._pep = pep
        self._vocabulary = vocabulary
        self._clock = clock
        self.opens = 0

    def session(self):  # noqa: ANN201 - a context manager
        self.opens += 1
        engine: Engine = create_persistence_engine(sqlite_url(self._path))
        uow = unit_of_work(create_session_factory(engine))
        outer = self

        class _Scope:
            def __enter__(self) -> tuple[WorkflowGraphStore, object]:
                session = uow.__enter__()
                return (
                    WorkflowGraphStore(session, outer._pep, outer._vocabulary, outer._clock),
                    session,
                )

            def __exit__(self, *exc: object) -> bool:
                try:
                    return bool(uow.__exit__(*exc))
                finally:
                    engine.dispose()

        return _Scope()


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "execution.workflow.graph_store")


@pytest.fixture(scope="module")
def vocabulary() -> GraphVocabulary:
    return GraphVocabulary.load(REPO)


@pytest.fixture()
def clock() -> MovableClock:
    return MovableClock()


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "workflow.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def reopen(
    database_path: pathlib.Path,
    pep: PolicyEnforcementPoint,
    vocabulary: GraphVocabulary,
    clock: MovableClock,
) -> Reopener:
    return Reopener(database_path, pep, vocabulary, clock)


def small_document(
    vocabulary: GraphVocabulary, workflow_id: str = "wf-1"
) -> WorkflowGraphDocument:
    return WorkflowGraphDocument.build(
        vocabulary,
        workflow_id,
        nodes=[
            WorkflowNode(node_id="n-trigger", kind="trigger", label="Start"),
            WorkflowNode(node_id="n-data", kind="data", label="Transform"),
        ],
        edges=[WorkflowEdge(edge_id="e-1", source_node_id="n-trigger", target_node_id="n-data")],
    )


def denying_pep(root: pathlib.Path) -> PolicyEnforcementPoint:
    """A REAL PEP over a REAL PDP whose authority map denies workspace writes.

    Only the governed data is a fixture; both mechanisms are the shipping
    ones, so a refusal here is a real refusal - the `durable_harness.denying_pep`
    precedent.
    """
    for relative in PDP_DOCUMENTS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    mapping = yaml.safe_load(
        (root / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
    )
    mapping["operation_classes"]["WRITE_WORKSPACE_FILE"] = {
        "default": "DENY", "fixed": "DENY"
    }
    (root / "docs/canonical/AUTHORITY_MAP.yaml").write_text(
        yaml.safe_dump(mapping), encoding="utf-8"
    )
    return PolicyEnforcementPoint(PolicyDecisionPoint.load(root), "denied")
