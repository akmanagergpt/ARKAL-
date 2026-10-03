"""Bounded read helper for rediscovering the active Factory production job."""
from __future__ import annotations

from arkali.execution.durable import job_state_machine
from arkali.execution.durable.job_store import JobStore
from arkali.execution.durable.records import DurableJobRecord


def _find_current_factory_job(store: JobStore) -> DurableJobRecord | None:
    active = (
        record for record in store.list_by_state(
            (job_state_machine.QUEUED, job_state_machine.RUNNING)
        )
        if record.job_type == "software_factory.production"
    )
    return max(active, key=lambda record: record.created_at, default=None)
