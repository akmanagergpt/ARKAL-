"""Shared harness for the Phase 7 final integration and fault-injection evidence.

Not a test module. It exists because `module <= 400 logical lines` is a real
architecture budget and ADR-0008 makes decomposition the answer rather than an
exception, following the `durable_harness.py` and `plane_harness.py` precedents.

ONE DATABASE, EVERY AUTHORITY. The C-19 tables, the C-12 tables and the
C-14/C-15 evidence tables all live in the same Alembic chain, so one real SQLite
file carries the whole journey. Nothing is substituted: the substitution policy
in `VERIFICATION_ARCHITECTURE.md` makes a tier from T5 upward that substitutes a
database NOT_CONFIGURED, never PASS.

A RUNTIME IS BUILT AND DESTROYED, NOT REUSED. `Runtime` constructs a new engine,
a new session factory and a new FastAPI application every time, and disposes the
engine on exit. A value written in one runtime and read in the next came off the
disk, and a restart is a real restart rather than a rolled-back transaction.

THE CLOCK IS ADVANCED, NEVER SLEPT ON, so every liveness and expiry assertion is
a comparison and no evidence can flake on wall-clock timing.

NOTHING HERE ADDS A PRODUCTION IMPORT EDGE. `max_orchestration_depth` is at 4 of
4 after Package 4, so Phase 7's final evidence is assembled in the test tier and
introduces no new runtime context hop.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import shutil
from collections.abc import Iterator

import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore
from arkali.evidence.audit.chain import AuditChain
from arkali.execution.durable.execution import JobExecution
from arkali.execution.durable.recovery import JobRecovery
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work
from arkali.surfaces.command.app import create_app

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

START = dt.datetime(2026, 5, 6, 7, 8, 9, tzinfo=dt.timezone.utc)
OWNER = "worker-phase7"
JOB_ID = "JOB-P7-1"
JOB_TYPE = "arkali.phase7.pausable"
UNPAUSABLE_TYPE = "arkali.phase7.unpausable"
IDEMPOTENCY_KEY = "phase7-key-1"

#: Canonical documents a real PDP needs in order to load at all.
PDP_DOCUMENTS = (
    "docs/canonical/AUTHORITY_MAP.yaml",
    "docs/canonical/SECURITY_ARCHITECTURE.md",
    "docs/canonical/ARCHITECTURE.md",
)


class MovableClock:
    """A clock the test moves explicitly. Nothing here waits for real time."""

    def __init__(self, start: dt.datetime = START) -> None:
        self.now = start

    def __call__(self) -> dt.datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now = self.now + dt.timedelta(seconds=seconds)


class Runtime:
    """One application lifetime over a fixed database file and blob root.

    Every entry builds a NEW engine and a NEW application; every exit disposes
    the engine. `restarts` counts how many genuinely separate runtimes a journey
    used, so an assertion can prove the evidence really crossed a boundary.
    """

    def __init__(
        self,
        database: pathlib.Path,
        blobs: pathlib.Path,
        pdp: PolicyDecisionPoint,
        clock: MovableClock,
    ) -> None:
        self._database = database
        self._blobs = blobs
        self._pdp = pdp
        self._clock = clock
        self.restarts = 0

    def app(self):  # noqa: ANN201 - a context manager
        """A real FastAPI application over a real engine."""
        self.restarts += 1
        engine: Engine = create_persistence_engine(sqlite_url(self._database))
        built: FastAPI = create_app(engine, self._pdp, self._clock)

        class _Scope:
            def __enter__(self) -> TestClient:
                self._client = TestClient(built)
                return self._client.__enter__()

            def __exit__(self, *exc: object) -> bool:
                try:
                    return bool(self._client.__exit__(*exc))
                finally:
                    engine.dispose()

        return _Scope()

    def durable(self):  # noqa: ANN201 - a context manager
        """The canonical durable services over a fresh engine."""
        self.restarts += 1
        engine: Engine = create_persistence_engine(sqlite_url(self._database))
        uow = unit_of_work(create_session_factory(engine))
        outer = self

        class _Scope:
            def __enter__(self) -> tuple[JobRecovery, JobExecution, object]:
                session = uow.__enter__()
                pep = PolicyEnforcementPoint(outer._pdp, "phase7.durable")
                recovery = JobRecovery(session, pep, outer._clock)
                return recovery, recovery.execution, session

            def __exit__(self, *exc: object) -> bool:
                try:
                    return bool(uow.__exit__(*exc))
                finally:
                    engine.dispose()

        return _Scope()

    def evidence(self):  # noqa: ANN201 - a context manager
        """The Phase 6 C-14/C-15 authorities over a fresh engine.

        Two separate services, exactly as `plane_harness.py` keeps them: this
        is a convenience for the test, never a merged authority.
        """
        self.restarts += 1
        engine: Engine = create_persistence_engine(sqlite_url(self._database))
        uow = unit_of_work(create_session_factory(engine))
        outer = self

        class _Scope:
            def __enter__(self) -> tuple[ArtifactStore, AuditChain, object]:
                session = uow.__enter__()
                pep = PolicyEnforcementPoint(outer._pdp, "phase7.evidence")
                blobs = ArtifactBlobStore(outer._blobs, pep)
                return (
                    ArtifactStore(session, blobs),
                    AuditChain(session, pep, REPO),
                    session,
                )

            def __exit__(self, *exc: object) -> bool:
                try:
                    return bool(uow.__exit__(*exc))
                finally:
                    engine.dispose()

        return _Scope()


def as_utc(moment: dt.datetime) -> dt.datetime:
    """Compare INSTANTS, not representations.

    SQLite has no timezone type, so a column read back off the disk is naive
    while the same value still in the session is aware. `execution.durable`
    already normalises before every internal comparison, and the transport
    boundary does the same since F-0038; a test that compares the raw
    attributes would be asserting the rendering rather than the instant.
    """
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def alembic_config(database: pathlib.Path) -> Config:
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database))
    return config


def enqueue_body(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "job_id": JOB_ID,
        "job_type": JOB_TYPE,
        "idempotency_key": IDEMPOTENCY_KEY,
        "payload": {"instruction": "opaque to every layer that carries it"},
    }
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def clock() -> MovableClock:
    return MovableClock()


@pytest.fixture()
def database(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "phase7.db"
    command.upgrade(alembic_config(path), "head")
    return path


@pytest.fixture()
def runtime(
    database: pathlib.Path,
    tmp_path: pathlib.Path,
    pdp: PolicyDecisionPoint,
    clock: MovableClock,
) -> Iterator[Runtime]:
    yield Runtime(database, tmp_path / "blobs", pdp, clock)


def denying_pdp(root: pathlib.Path, operation: str) -> PolicyDecisionPoint:
    """A REAL PDP over a REAL authority map with one class fixed to DENY.

    Only the governed data is a fixture; the mechanism is the shipping one, so a
    refusal here is a real refusal rather than a stand-in object raising.
    """
    for relative in PDP_DOCUMENTS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    mapping = yaml.safe_load(
        (root / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
    )
    mapping["operation_classes"][operation] = {"default": "DENY", "fixed": "DENY"}
    (root / "docs/canonical/AUTHORITY_MAP.yaml").write_text(
        yaml.safe_dump(mapping), encoding="utf-8"
    )
    return PolicyDecisionPoint.load(root)
