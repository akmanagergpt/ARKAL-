"""DEF-009 composition wiring: `scripts/run_command_center.py` auto-spawns
the existing, unmodified `run_factory_worker.py` consumer once per genuinely
new `software_factory.production` job, without building a second scheduler.

WHAT THIS PROVES. `_should_auto_spawn_worker` is the pure decision `submit()`
consults; `TestSubmitClosureSpawnsRealWorkerOnce` proves the closure wired
into `_CommandExtensions.factory_submitter` actually calls it correctly
against a REAL `JobStore`/`_DurableFactorySink` - only the outer
`ProductionFactory`/capability composition is stubbed, since that
orchestration is not what this file is about and stubbing it avoids a live
Ollama dependency in a fast structural test. `run_factory_worker.py` itself
is never imported, run, or duplicated here - `_spawn_factory_worker_once` is
replaced with a counting fake so no real subprocess is ever launched by this
suite.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config

from arkali.control.policy.pdp import PolicyDecisionPoint
from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.execution.durable.job_state_machine import QUEUED, RUNNING
from arkali.kernel.persistence.engine import create_persistence_engine, sqlite_url
from arkali.kernel.persistence.migrations import ALEMBIC_INI
from arkali.kernel.persistence.session import create_session_factory, unit_of_work

REPO = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "run_command_center.py"


def _module():  # noqa: ANN202
    spec = importlib.util.spec_from_file_location("run_command_center", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod():  # noqa: ANN201
    return _module()


@pytest.fixture(scope="module")
def pdp() -> PolicyDecisionPoint:
    return PolicyDecisionPoint.load(REPO)


@pytest.fixture()
def database_path(tmp_path: pathlib.Path) -> pathlib.Path:
    path = tmp_path / "autospawn.db"
    config = Config(str(REPO / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(path))
    command.upgrade(config, "head")
    return path


class _FakeAuthority:
    default_capability_id = None

    @staticmethod
    def query(*_args: object, **_kwargs: object) -> None:  # pragma: no cover
        raise AssertionError("this fixture never resolves a capability")


class _FakeProductionFactory:
    """Stands in for the real `ProductionFactory`: forwards straight to the
    real sink so the real `JobStore`/`_DurableFactorySink` path under test
    runs unmodified, without needing a live capability/model composition."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def submit_goal(self, request: object, sink: object) -> SimpleNamespace:
        job_id = sink.enqueue(
            request.request_id,
            {"goal": {"goal_text": request.goal_text}},
        )
        return SimpleNamespace(state="queued", durable_job_id=job_id)


def _goal_body(request_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        model_dump=lambda: {
            "request_id": request_id,
            "goal_text": "build a real thing",
            "capability_id": None,
        }
    )


@pytest.fixture()
def patched_factory(
    monkeypatch: pytest.MonkeyPatch, mod, database_path: pathlib.Path  # noqa: ANN001
) -> list[int]:
    """Stubs the heavy capability/model composition and replaces the real
    subprocess spawn with a counting fake; returns that counter.

    `_FACTORY_WORKER_DB` is pinned to this test's own tmp database, so the
    "is this the default database" comparison `_factory_submitter` makes
    exercises real equality logic without ever touching the real
    `var/command_center.db` from a test.
    """
    monkeypatch.setattr(mod, "compose_real_capability_authority", lambda *a, **k: _FakeAuthority())
    monkeypatch.setattr(mod, "ProductionFactory", _FakeProductionFactory)
    monkeypatch.setattr(mod, "_FACTORY_WORKER_DB", database_path)
    spawns: list[int] = []
    monkeypatch.setattr(mod, "_spawn_factory_worker_once", lambda: spawns.append(1))
    return spawns


class TestShouldAutoSpawnWorkerPredicate:
    def test_a_fresh_queued_job_on_the_default_database_spawns(self, mod) -> None:  # noqa: ANN001
        assert mod._should_auto_spawn_worker(True, "job-1", QUEUED) is True

    def test_a_missing_durable_job_id_never_spawns(self, mod) -> None:  # noqa: ANN001
        assert mod._should_auto_spawn_worker(True, None, QUEUED) is False

    def test_an_already_claimed_job_never_spawns_again(self, mod) -> None:  # noqa: ANN001
        assert mod._should_auto_spawn_worker(True, "job-1", RUNNING) is False

    def test_a_non_default_database_never_spawns_even_when_queued(self, mod) -> None:  # noqa: ANN001
        assert mod._should_auto_spawn_worker(False, "job-1", QUEUED) is False


class TestSubmitClosureSpawnsRealWorkerOnce:
    def test_a_genuinely_new_goal_spawns_exactly_once(
        self, mod, pdp: PolicyDecisionPoint, database_path: pathlib.Path, patched_factory: list[int]
    ) -> None:
        submit = mod._factory_submitter(pdp, REPO, database_path)
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                result = submit(session, _goal_body("req-autospawn-1"))
        finally:
            engine.dispose()

        assert result.durable_job_id is not None
        assert patched_factory == [1]

    def test_an_idempotent_resubmission_of_an_already_claimed_job_does_not_respawn(
        self, mod, pdp: PolicyDecisionPoint, database_path: pathlib.Path, patched_factory: list[int]
    ) -> None:
        submit = mod._factory_submitter(pdp, REPO, database_path)
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                first = submit(session, _goal_body("req-autospawn-2"))
            assert patched_factory == [1]

            # Simulate the real worker having already claimed the job
            # (exactly what happens between a real submission and a real
            # page refresh / duplicate POST of the same idempotency key).
            with unit_of_work(create_session_factory(engine)) as session:
                pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
                mod.JobStore(session, pep).transition(first.durable_job_id, RUNNING)

            with unit_of_work(create_session_factory(engine)) as session:
                second = submit(session, _goal_body("req-autospawn-2"))
        finally:
            engine.dispose()

        assert second.durable_job_id == first.durable_job_id
        assert patched_factory == [1]  # still exactly one spawn, not two

    def test_a_non_default_database_path_never_spawns(
        self, mod, pdp: PolicyDecisionPoint, database_path: pathlib.Path, patched_factory: list[int]
    ) -> None:
        submit = mod._factory_submitter(pdp, REPO, database_path.with_name("other.db"))
        engine = create_persistence_engine(sqlite_url(database_path))
        try:
            with unit_of_work(create_session_factory(engine)) as session:
                result = submit(session, _goal_body("req-autospawn-3"))
        finally:
            engine.dispose()

        assert result.durable_job_id is not None
        assert patched_factory == []
