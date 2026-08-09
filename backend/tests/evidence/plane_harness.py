"""Shared harness for the Phase 6 Evidence Plane integration tiers.

Not a test module. It exists because `module <= 400 logical lines` is a real
architecture budget and ADR-0008 makes decomposition the answer to a budget
rather than an exception: the journey evidence and the provenance / graph
readiness evidence are two modules over one harness, following the
`tests/structural/typescript_reader.py` precedent.

REAL INFRASTRUCTURE ONLY. A real SQLite file migrated by the real Alembic
chain, a real PDP loaded from the authority map, a real content-addressed blob
store on disk. `VERIFICATION_ARCHITECTURE.md` section 1.1 forbids substituting
any of them at this tier, and nothing here does.

`Reopener.session()` builds a NEW engine each time and disposes it on exit, so
a value written in one block and read in the next came off the disk rather than
out of an identity map.
"""

from __future__ import annotations

import datetime as dt
import pathlib
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.specification.register_parser import RequirementRegister
from arkali.evidence.artifact.blob_store import ArtifactBlobStore
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput
from arkali.evidence.audit.chain import AuditChain
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"

#: The phase whose denominator this evidence is filed against. The ids are read
#: from the register at call time, never listed here.
PHASE = "6"


class Plane:
    """One open session onto the plane: both stores over the same database.

    Deliberately not a shared service. `ArtifactStore` and `AuditChain` stay two
    objects with two authorities; this only saves the tests from rebuilding both
    at every step. Nothing here mediates between them, and neither is reachable
    through the other.
    """

    def __init__(self, session: object, blobs: ArtifactBlobStore,
                 pep: PolicyEnforcementPoint) -> None:
        self.session = session
        self.artifacts = ArtifactStore(session, blobs)  # type: ignore[arg-type]
        self.evidence = AuditChain(session, pep, REPO)  # type: ignore[arg-type]


class Reopener:
    """Opens the plane over a fixed database file and blob root.

    `opens` records how many engines a journey really used, so a test can assert
    that its stages were genuinely separate rather than one long session.
    """

    def __init__(self, path: pathlib.Path, root: pathlib.Path,
                 pep: PolicyEnforcementPoint) -> None:
        self._path = path
        self._blobs = ArtifactBlobStore(root, pep)
        self._pep = pep
        self.opens = 0

    @contextmanager
    def session(self) -> Iterator[Plane]:
        self.opens += 1
        engine: Engine = create_persistence_engine(sqlite_url(self._path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                yield Plane(session, self._blobs, self._pep)
        finally:
            engine.dispose()


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def pep(pdp: PolicyDecisionPoint) -> PolicyEnforcementPoint:
    return PolicyEnforcementPoint(pdp, "evidence.plane.integration")


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "evidence_plane.db"
    config = Config(str(BACKEND / ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


@pytest.fixture()
def blob_root(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "blobs"


@pytest.fixture()
def plane(
    database_path: pathlib.Path, blob_root: pathlib.Path, pep: PolicyEnforcementPoint
) -> Reopener:
    return Reopener(database_path, blob_root, pep)


def as_utc(moment: dt.datetime) -> dt.datetime:
    """The same instant, tz-aware. SQLite returns naive values for UTC columns."""
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def phase_requirements() -> tuple[str, ...]:
    """The Phase 6 denominator, read from the sole denominator at call time."""
    return tuple(r.req_id for r in RequirementRegister.load(REPO).for_phase(PHASE))


def register_ids() -> frozenset[str]:
    return frozenset(RequirementRegister.load(REPO).all_ids())


def critical_provenance(**overrides: object) -> ProvenanceInput:
    """Provenance carrying every item `VDC section Provenance` names.

    "Critical generated/release artifacts record hash, producer/task,
    provider/model, spec version, context hash, parents, normalization, tests
    and evidence." The hash is not passed - it is derived from the bytes, which
    is the point - and the rest are supplied here.
    """
    fields: dict[str, object] = {
        "producer_agent": "arkali.phase6.package3",
        "provider_model": "none/deterministic",
        "task_id": "ARK-TASK-P6-P3",
        "specification_version": "MS-2.0/C-14-1.0.0",
        "context_hash": "sha256-of-the-compiled-context",
        "normalization": "utf-8/lf",
        "tests": ("tests/evidence/test_evidence_plane_integration.py",),
        "evidence": ("phase_6_traceability.json",),
        "parents": (),
    }
    fields.update(overrides)
    return ProvenanceInput(**fields)  # type: ignore[arg-type]
