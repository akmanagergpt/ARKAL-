"""Shared harness for the C-19 durable-execution test tiers.

Not a test module. It exists because `module <= 400 logical lines` is a real
architecture budget and ADR-0008 makes decomposition the answer rather than an
exception: the Package 2 evidence is two test modules over one harness,
following the `tests/structural/typescript_reader.py` precedent.

REAL INFRASTRUCTURE ONLY. A real SQLite file migrated by the real Alembic chain,
a real PDP loaded from the authority map, a real PEP.

THE CLOCK IS ADVANCED, NEVER SLEPT ON. `MovableClock` is moved explicitly by the
test, so every liveness and expiry assertion is a comparison and no control can
flake on wall-clock timing.

`Reopener.session()` builds a NEW engine each time and disposes it on exit, so a
value written in one block and read in the next came off the disk.
"""

from __future__ import annotations

import datetime as dt
import pathlib
import shutil

import pytest
import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, select

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.execution.durable.execution import JobExecution
from arkali.execution.durable.job_store import JobSubmission
from arkali.execution.durable.records import DurableJobRecord
from arkali.execution.durable.recovery import JobRecovery
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

START = dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
OWNER = "worker-a"

#: The job type the Package 1/2 fixtures submit under. Package 3 declares it
#: explicitly where pause capability is part of what is being tested; the
#: default is deliberately NOT auto-declared, so a test that needs the
#: capability has to say so and a test that does not exercises the fail-closed
#: path for free.
JOB_TYPE = "arkali.test.noop"

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


class Reopener:
    """Opens the execution service over one file, with a new engine each time."""

    def __init__(
        self, path: pathlib.Path, pep: PolicyEnforcementPoint, clock: MovableClock
    ) -> None:
        self._path = path
        self._pep = pep
        self._clock = clock
        self.opens = 0

    def session(self):  # noqa: ANN201 - a context manager
        self.opens += 1
        engine: Engine = create_persistence_engine(sqlite_url(self._path))
        uow = unit_of_work(create_session_factory(engine))
        outer = self

        class _Scope:
            def __enter__(self) -> tuple[JobExecution, object]:
                session = uow.__enter__()
                return JobExecution(session, outer._pep, outer._clock), session

            def __exit__(self, *exc: object) -> bool:
                try:
                    return bool(uow.__exit__(*exc))
                finally:
                    engine.dispose()

        return _Scope()

    def recovery(self):  # noqa: ANN201 - a context manager
        """The same file, the same new-engine-each-time discipline, but the
        Package 3 service. Separate rather than returning both, so a Package 2
        test cannot accidentally acquire pause or recovery powers.
        """
        self.opens += 1
        engine: Engine = create_persistence_engine(sqlite_url(self._path))
        uow = unit_of_work(create_session_factory(engine))
        outer = self

        class _Scope:
            def __enter__(self) -> tuple[JobRecovery, object]:
                session = uow.__enter__()
                return JobRecovery(session, outer._pep, outer._clock), session

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
    return PolicyEnforcementPoint(pdp, "execution.durable.execution")


@pytest.fixture()
def clock() -> MovableClock:
    return MovableClock()


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "durable.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def reopen(
    database_path: pathlib.Path, pep: PolicyEnforcementPoint, clock: MovableClock
) -> Reopener:
    return Reopener(database_path, pep, clock)


def submission(**overrides: object) -> JobSubmission:
    fields: dict[str, object] = {
        "job_id": "JOB-0001",
        "job_type": "arkali.test.noop",
        "idempotency_key": "key-1",
        "payload": {},
    }
    fields.update(overrides)
    return JobSubmission(**fields)  # type: ignore[arg-type]


def submit(execution: JobExecution, **overrides: object) -> DurableJobRecord:
    return execution.jobs.submit(submission(**overrides))


def set_bound(
    session: object,
    job_id: str,
    *,
    attempts: int,
    timeout: int,
    heartbeat: int | None = None,
) -> None:
    """Record different admission terms, through the mapped row.

    The job row is mutable by design - its lifecycle state follows the machine -
    so this is an ordinary recorded value, not a bypass of any authority.
    """
    record = session.execute(  # type: ignore[attr-defined]
        select(DurableJobRecord).where(DurableJobRecord.job_id == job_id)
    ).scalar_one()
    record.max_attempts = attempts
    record.attempt_timeout_seconds = timeout
    if heartbeat is not None:
        record.heartbeat_timeout_seconds = heartbeat


def declare(recovery: JobRecovery, *, supports_pause: bool, job_type: str = JOB_TYPE):  # noqa: ANN201
    """Declare the fixture job type's pause capability."""
    return recovery.job_types.declare(job_type, supports_pause=supports_pause)


def run(recovery: JobRecovery, owner: str = OWNER, **overrides: object) -> None:
    """Submit a job and put it in RUNNING with an open attempt."""
    recovery.execution.jobs.submit(submission(**overrides))
    job_id = str(overrides.get("job_id", "JOB-0001"))
    recovery.execution.begin_attempt(job_id, owner)


def denying_pep(root: pathlib.Path) -> PolicyEnforcementPoint:
    """A REAL PEP over a REAL PDP whose authority map denies workspace writes.

    Only the governed data is a fixture; both mechanisms are the shipping ones,
    so a refusal here is a real refusal rather than a stand-in object raising.
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
