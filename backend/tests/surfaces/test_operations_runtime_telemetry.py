"""C-34 runtime telemetry (ARK-REQ-0168): real jobs/workflows/stuck detection,
honest NOT_CONFIGURED for providers/agents/workers.

REAL INFRASTRUCTURE ONLY - see `operations_harness.py`.
"""

from __future__ import annotations

from arkali.execution.durable.job_store import JobSubmission
from arkali.kernel.contracts.honest_state import HonestState
from arkali.surfaces.operations.runtime_telemetry import observe_runtime
from tests.surfaces.operations_harness import (  # noqa: F401 - fixtures by import
    OperationsReopener,
    approval_gate,
    clock,
    database_path,
    job_store_of,
    pdp,
    reopen,
    vocabulary,
)

JOB_TYPE = "arkali.test.noop"


def _submit(recovery, job_id: str = "JOB-0001") -> None:
    recovery.execution.jobs.submit(
        JobSubmission(job_id=job_id, job_type=JOB_TYPE, idempotency_key=f"key-{job_id}")
    )


class TestJobAndWorkflowDimensionsAreRealAndLive:
    def test_an_empty_database_reports_zero_active_work(
        self, reopen: OperationsReopener
    ) -> None:
        with reopen.session() as (recovery, executor, _engine, _session):
            snapshot = observe_runtime(job_store_of(recovery), recovery, executor)
        assert snapshot.jobs_active.value == 0.0
        assert snapshot.jobs_queued.value == 0.0
        assert snapshot.jobs_stuck.value == 0.0
        assert snapshot.workflows_active.value == 0.0
        for reading in (snapshot.jobs_active, snapshot.jobs_queued, snapshot.jobs_stuck,
                        snapshot.workflows_active):
            assert reading.state is HonestState.PASS

    def test_a_queued_job_is_counted_as_queued_not_active(
        self, reopen: OperationsReopener
    ) -> None:
        with reopen.session() as (recovery, executor, _engine, session):
            _submit(recovery)
            session.commit()
        with reopen.session() as (recovery, executor, _engine, _session):
            snapshot = observe_runtime(job_store_of(recovery), recovery, executor)
        assert snapshot.jobs_queued.value == 1.0
        assert snapshot.jobs_active.value == 0.0

    def test_a_running_job_is_counted_as_active(self, reopen: OperationsReopener) -> None:
        with reopen.session() as (recovery, executor, _engine, session):
            _submit(recovery)
            recovery.execution.begin_attempt("JOB-0001", "worker-a")
            session.commit()
        with reopen.session() as (recovery, executor, _engine, _session):
            snapshot = observe_runtime(job_store_of(recovery), recovery, executor)
        assert snapshot.jobs_active.value == 1.0
        assert snapshot.jobs_queued.value == 0.0

    def test_a_running_job_past_heartbeat_timeout_is_reported_stuck(
        self, reopen: OperationsReopener, clock,
    ) -> None:
        with reopen.session() as (recovery, executor, _engine, session):
            _submit(recovery)
            recovery.execution.begin_attempt("JOB-0001", "worker-a")
            session.commit()
        clock.advance(61)  # DEFAULT_HEARTBEAT_TIMEOUT_SECONDS is 60
        with reopen.session() as (recovery, executor, _engine, _session):
            snapshot = observe_runtime(job_store_of(recovery), recovery, executor)
        assert snapshot.jobs_stuck.value == 1.0

    def test_a_freshly_heartbeaten_job_is_not_reported_stuck(
        self, reopen: OperationsReopener, clock,
    ) -> None:
        with reopen.session() as (recovery, executor, _engine, session):
            _submit(recovery)
            recovery.execution.begin_attempt("JOB-0001", "worker-a")
            session.commit()
        clock.advance(61)
        with reopen.session() as (recovery, executor, _engine, session):
            recovery.execution.heartbeat("JOB-0001", "worker-a")
            session.commit()
        with reopen.session() as (recovery, executor, _engine, _session):
            snapshot = observe_runtime(job_store_of(recovery), recovery, executor)
        assert snapshot.jobs_stuck.value == 0.0


class TestNoLiveRegistryDimensionsAreHonestlyNotConfigured:
    def test_providers_agents_and_workers_are_not_fabricated(
        self, reopen: OperationsReopener,
    ) -> None:
        with reopen.session() as (recovery, executor, _engine, _session):
            snapshot = observe_runtime(job_store_of(recovery), recovery, executor)
        for reading in (snapshot.providers, snapshot.agents, snapshot.workers):
            assert reading.state is HonestState.NOT_CONFIGURED
            assert reading.value is None
            assert reading.detail
