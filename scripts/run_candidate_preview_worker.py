#!/usr/bin/env python3
"""The real `candidate.preview` durable-job consumer for Command Center's
"Uygulamayı Aç" flow.

Claims AT MOST ONE real, durable `candidate.preview` job (C-19,
`execution.durable`) already queued by `POST /api/candidates/{candidate_id}
/preview`, and hands it to
the exact same real, canonical preview entry point
`scripts/run_candidate_preview.py` uses:
`engineering.candidate.preview.run_preview`. No install/start/health/stop
logic is copied or reimplemented here — this script's only job is durable-
job lifecycle plumbing (claim, checkpoint, watch for a cancel request,
report the terminal outcome) around a call it does not alter. The exact
same shape `scripts/run_factory_worker.py` already established for
`software_factory.production` jobs.

WHY A SEPARATE PROCESS, NOT A THREAD INSIDE THE WEB SERVER. Same reason as
the factory worker: `ARK-REQ-0027` — "no long AI work in HTTP requests" —
and a real preview's install+build phase alone measured 60-90+ real
seconds this session, well past what a request should ever hold open.

WHY NOT A LOOP. This process claims one job, serves it until it is
CANCELLED (by a real `POST /jobs/{id}/cancel` call — Command Center's
"Durdur") or reaches its own generous bounded ceiling, then exits. Exactly
`run_factory_worker.py`'s own "why not a loop" reasoning: a second
scheduler is not being built this turn, and an operator's own supervision
(manual re-run, a future real worker-loop authority) is a deployment
decision outside this script's scope.

WHY A CHECKPOINT, NOT A STATE TRANSITION, IS THE STOP SIGNAL. `POST
/jobs/{id}/cancel` never transitions the job itself (`transition` is one
of `surfaces.command.jobs`'s own structurally forbidden calls — an HTTP
handler may record a fact, never move a lifecycle state); it only leaves
a real `{"phase": "cancel_requested"}` checkpoint. This worker is the
only thing that ever calls `transition` for this job, and only after
`run_preview`'s own `finally` (unchanged, imported, not reimplemented)
has already stopped both processes and removed the workspace — so
CANCELLED is a real, verified "this is actually stopped now", never a
request still in flight. There is no PID file, no `RuntimeRegistry`, no
second truth store anywhere in this: `_cancel_requested` reads the same
`JobStore` checkpoints the Command Center itself reads.
"""

from __future__ import annotations

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.engineering.candidate.preview import (  # noqa: E402
    PreviewCancelled,
    PreviewRefused,
    run_preview,
)
from arkali.execution.durable.job_state_machine import (  # noqa: E402
    CANCELLED as JOB_CANCELLED,
    FAILED as JOB_FAILED,
    QUEUED as JOB_QUEUED,
    RUNNING as JOB_RUNNING,
)
from arkali.execution.durable.job_store import JobStore  # noqa: E402
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
    sqlite_url,
)
from arkali.kernel.persistence.session import (  # noqa: E402
    create_session_factory,
    unit_of_work,
)

JOB_TYPE = "candidate.preview"
#: A generous safety net, not a target: a preview left open in a browser
#: tab nobody closed must still end on its own eventually rather than
#: running forever. "Durdur" (a real cancel) always ends it far sooner.
MAX_LIFETIME_SECONDS = 1800.0
POLL_INTERVAL_SECONDS = 2.0


def _claim_one_job(store: JobStore):  # noqa: ANN202
    """The oldest real QUEUED `candidate.preview` job, or None. `JobStore`
    has no claim/lease primitive by design (its own module docstring:
    "NOTHING HERE SCHEDULES"); this script processes exactly one job per
    invocation, the same bound `run_factory_worker.py` already accepted."""
    candidates = [
        job for job in store.list_by_state((JOB_QUEUED,)) if job.job_type == JOB_TYPE
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda job: job.created_at)
    return candidates[0]


def main() -> int:
    db_path = ROOT / "var" / "command_center.db"
    pdp = PolicyDecisionPoint.load(ROOT)

    def _store(session) -> JobStore:  # noqa: ANN001
        return JobStore(session, PolicyEnforcementPoint(pdp, "execution.durable.job_store"))

    engine = create_persistence_engine(sqlite_url(db_path))
    try:
        with unit_of_work(create_session_factory(engine)) as session:
            job = _claim_one_job(_store(session))
            if job is None:
                print('{"outcome": "NO_JOB_QUEUED"}')
                return 0
            job_id = job.job_id
            candidate_id = job.payload.get("candidate_id")
            _store(session).transition(job_id, JOB_RUNNING)
    finally:
        engine.dispose()

    if not isinstance(candidate_id, str) or not candidate_id:
        _finish(db_path, pdp, job_id, JOB_FAILED, {
            "phase": "refused", "reason": "job payload carries no candidate_id",
        })
        print('{"outcome": "INVALID_PAYLOAD"}')
        return 1

    def _checkpoint(phase: str, detail: dict[str, object]) -> None:
        checkpoint_engine = create_persistence_engine(sqlite_url(db_path))
        try:
            with unit_of_work(create_session_factory(checkpoint_engine)) as checkpoint_session:
                _store(checkpoint_session).checkpoint(job_id, {"phase": phase, **detail})
        finally:
            checkpoint_engine.dispose()

    def _cancel_requested() -> bool:
        """Whether Command Center's real "Durdur" (`POST /jobs/{id}/cancel`)
        has left its `cancel_requested` checkpoint yet. The route that
        handles that click never transitions the job itself (`transition`
        is forbidden from any HTTP handler in this surface) — this worker
        is the only thing that ever does, and only by actually observing
        this real, durable fact."""
        state_engine = create_persistence_engine(sqlite_url(db_path))
        try:
            with unit_of_work(create_session_factory(state_engine)) as state_session:
                rows = _store(state_session).checkpoints(job_id)
        finally:
            state_engine.dispose()
        return any(row.payload.get("phase") == "cancel_requested" for row in rows)

    try:
        with run_preview(
            candidate_id, on_phase=_checkpoint, should_cancel=_cancel_requested,
        ) as info:
            print(f'{{"outcome": "READY", "candidate_id": {candidate_id!r}, '
                  f'"frontend_url": {info["frontend_url"]!r}}}')
            deadline = time.monotonic() + MAX_LIFETIME_SECONDS
            stop_reason = "max_lifetime_reached"
            while time.monotonic() < deadline:
                if _cancel_requested():
                    stop_reason = "cancelled"
                    break
                time.sleep(POLL_INTERVAL_SECONDS)
    except PreviewCancelled:
        # A real "Durdur" arrived while still inside install/build --
        # `_run`'s own cooperative poll already stopped that subprocess and
        # `run_preview`'s `finally` already cleaned up on the way out here.
        _finish(db_path, pdp, job_id, JOB_CANCELLED, {
            "phase": "cancelled_during_setup", "reason": "cancelled",
        })
        print('{"outcome": "STOPPED", "reason": "cancelled_during_setup"}')
        return 0
    except PreviewRefused as error:
        _finish(db_path, pdp, job_id, JOB_FAILED, {"phase": "refused", "reason": str(error)})
        print(f'{{"outcome": "REFUSED", "reason": {str(error)!r}}}')
        return 1
    except Exception as error:  # a real crash during install/start
        _finish(db_path, pdp, job_id, JOB_FAILED, {"phase": "crashed", "reason": str(error)})
        raise

    # Either way, cleanup (process stop, workspace removal) already happened
    # in `run_preview`'s own `finally` as the `with` block exited above --
    # this worker is the only thing that ever transitions the job, and it
    # does so only now, after that cleanup is real and complete.
    _finish(db_path, pdp, job_id, JOB_CANCELLED, {
        "phase": "auto_stopped" if stop_reason == "max_lifetime_reached" else "stopped",
        "reason": stop_reason,
    })
    print(f'{{"outcome": "STOPPED", "reason": {stop_reason!r}}}')
    return 0


def _finish(db_path: pathlib.Path, pdp, job_id: str, state: str, detail: dict[str, object]) -> None:  # noqa: ANN001
    finish_engine = create_persistence_engine(sqlite_url(db_path))
    try:
        with unit_of_work(create_session_factory(finish_engine)) as session:
            store = JobStore(session, PolicyEnforcementPoint(pdp, "execution.durable.job_store"))
            store.checkpoint(job_id, detail)
            store.transition(job_id, state)
    finally:
        finish_engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
