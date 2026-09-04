#!/usr/bin/env python3
"""The real `managed_product.change` durable-job consumer (D-030 V1).

Claims AT MOST ONE real, durable `managed_product.change` job (C-19,
`execution.durable`) already queued by `POST /api/projects/{project_id}
/changes`, and drives the whole real pipeline: `engineering.product_
change.modification.prepare_modification` (resolve base revision ->
materialize source -> workspace -> inspect -> real provider call ->
validate+apply changeset -> verify), then — only if verification passed —
a real, live preview of the PROPOSED (not yet promoted) change, reusing
`engineering.candidate.preview._run_preview_over_source` UNCHANGED, the
same subject-generic runtime primitive Turn G's own preview-bridge work
extracted for exactly this reuse. No install/build/health logic is
copied or reimplemented here.

WHY THIS SCRIPT, NOT `engineering.product_change`, COMPOSES THE MODEL
ADAPTER AND THE PREVIEW PRIMITIVE. Both `engineering.localai.adapter.
LocalRuntimeAdapter` and `engineering.candidate.preview._run_preview_
over_source` are unreachable from `engineering.product_change` by direct
import (measured: orchestration depth 5 of a 4 ceiling for the former;
`engineering.candidate` already 4-of-4 depth and 40-of-40 public surface
for the latter) — `engineering.product_change.modification.
ModificationWiring` accepts each only as a structurally-typed
collaborator. Composing the REAL objects happens only here, in a script,
outside the measured architecture graph, the same discipline `scripts/
run_command_center.py`'s own `_preview_bridge_wiring` already
established for `_CandidateLedgerSource`.

WHY "PROMOTE" NEVER TRANSITIONS THIS JOB. `POST /api/projects/{project_id}
/changes/promote` calls `promote_modification` synchronously in-request
(fast: an archive + one content-addressed register + one DB row, no
provider call, ARK-REQ-0027-safe) and leaves a `promoted` checkpoint —
mirroring exactly how `POST /jobs/{id}/cancel` leaves `cancel_requested`
without transitioning anything (`jobs.py`'s own module docstring: an HTTP
handler may record a fact, never move a lifecycle state). This worker is
the only thing that ever calls `transition`, and only after it has itself
observed the `promoted` checkpoint (or a `reject_requested` one) and
actually stopped the live preview and, for a reject, actually removed the
workspace — so SUCCEEDED/CANCELLED here are always real, verified facts,
never a request still in flight.
"""

from __future__ import annotations

import pathlib
import shutil
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.control.registry.project.registry import ProjectRegistry  # noqa: E402
from arkali.engineering.candidate.preview import (  # noqa: E402
    PreviewCancelled,
    PreviewRefused,
    _candidate_dir,
    _run_preview_over_source,
)
from arkali.engineering.candidate.workspace import WorkspaceAuthority  # noqa: E402
from arkali.engineering.localai.ollama_adapter import OllamaAdapter  # noqa: E402
from arkali.engineering.product_change.errors import ProductChangeError  # noqa: E402
from arkali.engineering.product_change.modification import (  # noqa: E402
    CHANGE_JOB_TYPE,
    ModificationWiring,
    prepare_modification,
)
from arkali.evidence.artifact.blob_store import ArtifactBlobStore  # noqa: E402
from arkali.evidence.artifact.store import ArtifactStore  # noqa: E402
from arkali.execution.durable.job_state_machine import (  # noqa: E402
    CANCELLED as JOB_CANCELLED,
    FAILED as JOB_FAILED,
    QUEUED as JOB_QUEUED,
    RUNNING as JOB_RUNNING,
    SUCCEEDED as JOB_SUCCEEDED,
)
from arkali.execution.durable.job_store import JobStore  # noqa: E402
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
    sqlite_url,
)
from arkali.kernel.persistence.migrations import ALEMBIC_INI  # noqa: E402
from arkali.kernel.persistence.session import (  # noqa: E402
    create_session_factory,
    unit_of_work,
)

JOB_TYPE = CHANGE_JOB_TYPE
MODEL_ID = "qwen2.5-coder:14b"
#: Same generous safety net as `run_candidate_preview_worker.py` — a real
#: cancel/promote ends this far sooner in the ordinary case.
MAX_LIFETIME_SECONDS = 1800.0
POLL_INTERVAL_SECONDS = 2.0


class _CandidateSourceAdapter:
    """Satisfies `revision_resolution._CandidateSourceResolver` over the
    real, private `_candidate_dir` this script is free to import (outside
    the measured architecture graph)."""

    def source_dir(self, candidate_id: str) -> pathlib.Path:
        return _candidate_dir(candidate_id)


def _claim_one_job(store: JobStore):  # noqa: ANN202
    candidates = [
        job for job in store.list_by_state((JOB_QUEUED,)) if job.job_type == JOB_TYPE
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda job: job.created_at)
    return candidates[0]


def main() -> int:
    db_path = ROOT / "var" / "command_center.db"
    evidence_db = ROOT / "var" / "factory" / "evidence" / "repair-evidence.db"
    evidence_db.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(ROOT / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(evidence_db))
    command.upgrade(config, "head")

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
            project_id = job.payload.get("project_id")
            request_text = job.payload.get("request_text")
            _store(session).transition(job_id, JOB_RUNNING)
    finally:
        engine.dispose()

    if not isinstance(project_id, str) or not project_id or not isinstance(request_text, str) or not request_text:
        _finish(db_path, pdp, job_id, JOB_FAILED, {
            "phase": "refused", "reason": "job payload carries no project_id/request_text",
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

    def _checkpoints() -> list:
        state_engine = create_persistence_engine(sqlite_url(db_path))
        try:
            with unit_of_work(create_session_factory(state_engine)) as state_session:
                return list(_store(state_session).checkpoints(job_id))
        finally:
            state_engine.dispose()

    def _reject_requested() -> bool:
        #: The SAME `cancel_requested` checkpoint `POST /jobs/{id}/cancel`
        #: already leaves — reused unchanged, exposed to the frontend under
        #: the domain-specific `POST /projects/{id}/changes/{id}/reject`
        #: route instead, which leaves the identical checkpoint.
        return any(row.payload.get("phase") == "cancel_requested" for row in _checkpoints())

    def _promoted() -> bool:
        return any(row.payload.get("phase") == "promoted" for row in _checkpoints())

    evidence_engine = create_persistence_engine(sqlite_url(evidence_db))
    try:
        with unit_of_work(create_session_factory(evidence_engine)) as evidence_session:
            artifacts = ArtifactStore(
                evidence_session,
                ArtifactBlobStore(
                    ROOT / "var" / "factory" / "evidence" / "blobs",
                    PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"),
                ),
            )
            registry_engine = create_persistence_engine(sqlite_url(db_path))
            try:
                with unit_of_work(create_session_factory(registry_engine)) as registry_session:
                    wiring = ModificationWiring(
                        artifacts=artifacts,
                        candidate_source_resolver=_CandidateSourceAdapter(),
                        workspace_allocator=WorkspaceAuthority(ROOT / "var" / "factory" / "changes"),
                        model=OllamaAdapter(json_mode=False, max_output_tokens=4096),
                        model_id=MODEL_ID,
                    )
                    prepared = prepare_modification(
                        project_id, request_text,
                        registry=ProjectRegistry(registry_session), wiring=wiring,
                        on_phase=_checkpoint,
                    )
            finally:
                registry_engine.dispose()
    except ProductChangeError as error:
        _finish(db_path, pdp, job_id, JOB_FAILED, {"phase": "refused", "reason": str(error)})
        print(f'{{"outcome": "REFUSED", "reason": {str(error)!r}}}')
        return 1
    except Exception as error:  # a real crash during prepare
        _finish(db_path, pdp, job_id, JOB_FAILED, {"phase": "crashed", "reason": str(error)})
        raise

    if not prepared.verification.passed:
        shutil.rmtree(prepared.workspace.root, ignore_errors=True)
        _finish(db_path, pdp, job_id, JOB_FAILED, {
            "phase": "verification_failed", "failures": prepared.verification.failures,
        })
        print('{"outcome": "VERIFICATION_FAILED"}')
        return 1

    identity = f"change-{project_id}"
    try:
        with _run_preview_over_source(
            identity, prepared.product_root,
            on_phase=lambda phase, detail: _checkpoint(phase, detail),
            should_cancel=_reject_requested,
        ) as info:
            _checkpoint("ready_for_review", {
                "workspace_root": str(prepared.workspace.root),
                "base_revision_id": prepared.base_revision_id,
                "plan_ref": prepared.plan_ref,
                "changeset_ref": prepared.changeset_ref,
                "verification_passed": prepared.verification.passed,
                "verification_failures": prepared.verification.failures,
                "frontend_url": info["frontend_url"],
                "backend_url": info["backend_url"],
            })
            print(f'{{"outcome": "READY_FOR_REVIEW", "frontend_url": {info["frontend_url"]!r}}}')
            deadline = time.monotonic() + MAX_LIFETIME_SECONDS
            stop_reason = "max_lifetime_reached"
            while time.monotonic() < deadline:
                if _promoted():
                    stop_reason = "promoted"
                    break
                if _reject_requested():
                    stop_reason = "rejected"
                    break
                time.sleep(POLL_INTERVAL_SECONDS)
    except PreviewCancelled:
        stop_reason = "rejected"
    except PreviewRefused as error:
        shutil.rmtree(prepared.workspace.root, ignore_errors=True)
        _finish(db_path, pdp, job_id, JOB_FAILED, {"phase": "refused", "reason": str(error)})
        print(f'{{"outcome": "REFUSED", "reason": {str(error)!r}}}')
        return 1
    except Exception as error:  # a real crash while previewing
        shutil.rmtree(prepared.workspace.root, ignore_errors=True)
        _finish(db_path, pdp, job_id, JOB_FAILED, {"phase": "crashed", "reason": str(error)})
        raise

    # The preview's own `finally` (unchanged, imported) has already stopped
    # both processes and removed the *preview* workspace by the time we get
    # here. `prepared.workspace` (the change workspace `product_root` lives
    # under) is separate: a promoted change's real bytes are already safely
    # archived into `ArtifactStore` by `promote_modification` (the
    # registered artifact, not this on-disk copy, is truth), and a rejected
    # one is simply discarded — either way this on-disk copy is now safe to
    # remove.
    shutil.rmtree(prepared.workspace.root, ignore_errors=True)

    if stop_reason == "promoted":
        _finish(db_path, pdp, job_id, JOB_SUCCEEDED, {"phase": "promoted"})
        print('{"outcome": "PROMOTED"}')
        return 0
    _finish(db_path, pdp, job_id, JOB_CANCELLED, {
        "phase": "rejected" if stop_reason == "rejected" else "auto_stopped",
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
