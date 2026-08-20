#!/usr/bin/env python3
"""Serve the Command Center API over a real, migrated SQLite database.

Usage: python scripts/run_command_center.py [--host H] [--port P] [--db PATH]

WHY THIS EXISTS. The T10 browser tier requires a real user journey against a
real backend (VERIFICATION_ARCHITECTURE.md 1.1: no mocks, execution level L2).
`TestClient` speaks ASGI in-process and never opens a socket, so a browser
cannot reach it. This binds the *existing* application to a real port.

WHAT IT IS NOT. It builds no application of its own. `create_app` in
`surfaces.command` is the only Command Center factory, the engine comes from
`kernel.persistence`, the schema comes from the real Alembic chain and the PDP
is loaded from the canonical authority map. Nothing here is substituted, and a
control in `backend/tests/structural/test_browser_journey_integrity.py` fails if
this launcher ever grows a second app, a second engine or an in-memory database.

LOOPBACK ONLY. It binds 127.0.0.1 by default. This is a local-first product and
an evidence harness, not a deployment path.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

ROOT = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.control.policy.workflow_approval import WorkflowApprovalGate  # noqa: E402
from arkali.engineering.localai import host_probe  # noqa: E402
from arkali.execution.durable.recovery import JobRecovery  # noqa: E402
from arkali.execution.workflow.executor import WorkflowExecutor  # noqa: E402
from arkali.execution.workflow.graph_model import (  # noqa: E402
    WorkflowEdge,
    WorkflowGraphDocument,
    WorkflowNode,
)
from arkali.execution.workflow.graph_store import WorkflowGraphStore  # noqa: E402
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary  # noqa: E402
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
    sqlite_url,
)
from arkali.kernel.persistence.migrations import ALEMBIC_INI  # noqa: E402
from arkali.surfaces.command.app import create_app  # noqa: E402


def _workflow_wiring(
    pdp: PolicyDecisionPoint, repo_root: pathlib.Path
) -> tuple[Callable[..., Any], Callable[..., Any], Callable[..., Any]]:
    """The C-20 composition-root wiring, built once over the real vocabulary
    and approval gate. This script lives outside `backend/arkali/` and outside
    the measured architecture graph, so composing `execution.workflow`'s real
    objects here - exactly as the backend integration tests already do - adds
    no edge the architecture budget would ever see. See `workflow.py`'s module
    docstring for why `surfaces.command` itself may not import them directly.
    """
    vocabulary = GraphVocabulary.load(repo_root)
    approval_gate = WorkflowApprovalGate.load(repo_root)

    def document_builder(
        workflow_id: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> WorkflowGraphDocument:
        return WorkflowGraphDocument.build(
            vocabulary,
            workflow_id,
            nodes=[WorkflowNode(**n) for n in nodes],
            edges=[WorkflowEdge(**e) for e in edges],
        )

    def graph_store_factory(session: Session) -> WorkflowGraphStore:
        pep = PolicyEnforcementPoint(pdp, "execution.workflow.graph_store")
        return WorkflowGraphStore(session, pep, vocabulary)

    def executor_factory(session: Session) -> WorkflowExecutor:
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return document_builder, graph_store_factory, executor_factory


def _operations_wiring(
    pdp: PolicyDecisionPoint, repo_root: pathlib.Path
) -> tuple[Callable[..., Any], Callable[..., Any], PolicyDecisionPoint, Callable[..., Any]]:
    """The C-34 composition-root wiring (Phase 25) - the identical shape and
    the identical reason `_workflow_wiring` above already established: this
    script sits outside the measured architecture graph, so constructing
    real `JobRecovery`/`WorkflowExecutor` instances (which need a real
    `PolicyEnforcementPoint`) and importing the real
    `engineering.localai.host_probe.probe_host` here adds no edge the
    architecture budget would ever see. See `operations.py`'s own module
    docstring for why `surfaces.command` itself may not do either directly.
    """
    vocabulary = GraphVocabulary.load(repo_root)
    approval_gate = WorkflowApprovalGate.load(repo_root)

    def job_recovery_factory(session: Session) -> JobRecovery:
        pep = PolicyEnforcementPoint(pdp, "execution.durable.execution")
        return JobRecovery(session, pep)

    def executor_factory(session: Session) -> WorkflowExecutor:
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return job_recovery_factory, executor_factory, pdp, host_probe.probe_host


def migrate(database: pathlib.Path) -> None:
    """Bring the database to head with the real migration chain."""
    config = Config(str(ROOT / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database))
    command.upgrade(config, "head")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--db",
        default=str(ROOT / "var" / "command_center.db"),
        help="path to the SQLite file; created and migrated if absent",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help=(
            "delete the database and its WAL sidecars before migrating. The T10 "
            "journey asserts that what it created is still there after a reload "
            "and in a new browser context; if a previous run's rows survived, "
            "those assertions could pass without the claim being earned. Only "
            "this process may do the deletion, because only it holds the handle."
        ),
    )
    parser.add_argument(
        "--shutdown-sentinel",
        default=None,
        help=(
            "optional fixed desktop-lifecycle sentinel; when its owning desktop "
            "process removes it, uvicorn completes a graceful shutdown"
        ),
    )
    args = parser.parse_args(argv[1:])

    database = pathlib.Path(args.db).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh:
        for suffix in ("", "-wal", "-shm", "-journal"):
            pathlib.Path(f"{database}{suffix}").unlink(missing_ok=True)
    migrate(database)

    engine = create_persistence_engine(sqlite_url(database))
    pdp = PolicyDecisionPoint.load(ROOT)
    app = create_app(
        engine, pdp, workflow_wiring=_workflow_wiring(pdp, ROOT),
        operations_wiring=_operations_wiring(pdp, ROOT), operations_repo_root=ROOT,
    )
    print(f"command center on http://{args.host}:{args.port} over {database}")
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    if args.shutdown_sentinel is not None:
        sentinel = pathlib.Path(args.shutdown_sentinel).resolve()
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("ARKALI desktop backend owner\n", encoding="utf-8")

        def watch_desktop_owner() -> None:
            while sentinel.exists() and not server.should_exit:
                time.sleep(0.1)
            if not sentinel.exists():
                server.should_exit = True

        threading.Thread(
            target=watch_desktop_owner,
            name="arkali-desktop-shutdown",
            daemon=True,
        ).start()
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
