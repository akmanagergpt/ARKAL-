"""Phase 7 final integration — one durable job's whole life, across restarts.

This is the composed evidence for `ARK-REQ-0003` and `ARK-REQ-0027`, and half of
the evidence for `ARK-REQ-0059` and `ARK-REQ-0061`. It is deliberately ONE
journey rather than a suite of independent scenarios: the question Phase 7 has
to answer is whether the four packages compose into a durable runtime, and four
subsystems that each work alone can still fail to.

REAL EVERYTHING. A real SQLite file migrated by the real Alembic chain, a real
FastAPI application, a real PDP loaded from the authority map, the real
C-14/C-15 evidence authorities. Six separate runtimes across the journey, each
with its own engine, asserted.

WHAT IS NOT CLAIMED. The formal T12 chaos corpus begins at **Phase 31**;
`ARK-REQ-0327` is the durable-restart chaos proof and belongs there. The fault
injection here is real and deterministic, at the tier currently available - the
accepted Phase 4 `ARK-REQ-0121` precedent - and claims nothing beyond it.
"""

from __future__ import annotations

import pathlib

from arkali.evidence.artifact.store import ProvenanceInput
from arkali.evidence.audit.chain import EvidenceInput
from arkali.execution.durable.job_state_machine import DEFINITION
from arkali.execution.durable.records import INITIAL_STATE
from tests.execution.phase_7_harness import (  # noqa: F401 - fixtures
    IDEMPOTENCY_KEY,
    JOB_ID,
    JOB_TYPE,
    OWNER,
    UNPAUSABLE_TYPE,
    MovableClock,
    Runtime,
    clock,
    database,
    enqueue_body,
    pdp,
    runtime,
)

#: Longer than the default 60s heartbeat bound, shorter than the 300s deadline,
#: so recovery is triggered by SILENCE and not by the attempt timing out.
SILENCE = 61


class TestTheWholeDurableJourney:
    """Steps 1-19 of the Phase 7 integration obligation, in one narrative."""

    def test_a_job_survives_enqueue_execution_restart_and_recovery(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        # 1-2. A fresh runtime, and the job type declared with pause support.
        with runtime.durable() as (recovery, _execution, _session):
            recovery.job_types.declare(JOB_TYPE, supports_pause=True)

        # 3-5. Enqueue through the REAL HTTP API. The request returns a durable
        # reference, and the work has demonstrably not begun: the job is in the
        # state the canonical machine declares initial, with no attempt at all.
        with runtime.app() as client:
            accepted = client.post("/api/jobs", json=enqueue_body())
            assert accepted.status_code == 202
            reference = accepted.json()
            assert reference["job_id"] == JOB_ID
            assert reference["lifecycle_state"] == INITIAL_STATE

        with runtime.durable() as (_recovery, execution, _session):
            assert execution.attempt_count(JOB_ID) == 0, (
                "the HTTP request executed the job"
            )
            assert execution.jobs.require(JOB_ID).lifecycle_state == INITIAL_STATE

        # 6-8. Execution begins through the canonical durable service, records
        # ownership and a heartbeat, and persists a checkpoint.
        with runtime.durable() as (_recovery, execution, _session):
            attempt = execution.begin_attempt(JOB_ID, OWNER)
            assert attempt.attempt == 1 and attempt.owner == OWNER
            clock.advance(30)
            execution.heartbeat(JOB_ID, OWNER)
            execution.jobs.checkpoint(JOB_ID, {"stage": "first", "progress": 40})
            assert execution.jobs.require(JOB_ID).lifecycle_state == "RUNNING"

        # 9. A legal lifecycle operation: pause and resume, both through the
        # canonical machine, on a type whose registry row permits it.
        with runtime.durable() as (recovery, execution, _session):
            assert recovery.pause(JOB_ID).lifecycle_state == "PAUSED"
            assert recovery.resume(JOB_ID).lifecycle_state == "RUNNING"
            assert execution.attempt_count(JOB_ID) == 1, (
                "pause/resume consumed an attempt; suspension is not failure"
            )

        # 10-13. Everything above is disposed. A completely fresh runtime
        # resolves the same job and finds every durable fact intact.
        restarts_before = runtime.restarts
        with runtime.app() as client:
            resolved = client.get(f"/api/jobs/{JOB_ID}")
            assert resolved.status_code == 200
            assert resolved.json()["job_id"] == reference["job_id"]
            assert resolved.json()["created_at"] == reference["created_at"], (
                "the durable reference changed across a restart"
            )
            # Idempotency is the persisted one: a repeat resolves, never creates.
            repeat = client.post("/api/jobs", json=enqueue_body())
            assert repeat.status_code == 202
            assert repeat.json()["job_id"] == JOB_ID

        with runtime.durable() as (_recovery, execution, _session):
            job = execution.jobs.require(JOB_ID)
            assert job.idempotency_key == IDEMPOTENCY_KEY
            assert execution.attempt_count(JOB_ID) == 1
            checkpoints = execution.jobs.checkpoints(JOB_ID)
            assert [c.sequence for c in checkpoints] == [1]
            assert checkpoints[0].payload == {"stage": "first", "progress": 40}
            open_attempt = execution.current_attempt(JOB_ID)
            assert open_attempt is not None and open_attempt.owner == OWNER

        # 14-16. Time passes with no heartbeat: the execution is presumed lost.
        # Recovery travels the only route the canonical relation declares.
        clock.advance(SILENCE)
        with runtime.durable() as (recovery, execution, _session):
            assert recovery.heartbeat_stale(JOB_ID) is True
            assert execution.timed_out(JOB_ID) is False, (
                "the deadline has not passed; only the heartbeat has gone quiet"
            )
            assert recovery.recover_lost_executions() == (JOB_ID,)
            assert execution.jobs.require(JOB_ID).lifecycle_state == "RESUMING"
            closed = execution.attempts(JOB_ID)[0]
            assert closed.outcome == "RECOVERABLE" and closed.is_open is False

        # 17-19. Identity is unchanged, nothing was duplicated, and the job is
        # picked up again and completed through the canonical machine.
        with runtime.durable() as (_recovery, execution, _session):
            job = execution.jobs.require(JOB_ID)
            assert job.job_id == JOB_ID
            assert job.idempotency_key == IDEMPOTENCY_KEY
            assert execution.attempt_count(JOB_ID) == 1
            second = execution.begin_attempt(JOB_ID, "worker-b")
            assert second.attempt == 2
            execution.jobs.checkpoint(JOB_ID, {"stage": "second"})
            execution.complete_attempt(JOB_ID, "worker-b")

        with runtime.durable() as (_recovery, execution, _session):
            job = execution.jobs.require(JOB_ID)
            assert job.lifecycle_state == "SUCCEEDED"
            assert "SUCCEEDED" in DEFINITION.terminal
            assert [a.attempt for a in execution.attempts(JOB_ID)] == [1, 2]
            assert [
                c.sequence for c in execution.jobs.checkpoints(JOB_ID)
            ] == [1, 2]

        assert runtime.restarts > restarts_before + 1, (
            "the journey did not actually cross a runtime boundary"
        )
        assert runtime.restarts >= 6, (
            f"only {runtime.restarts} runtimes used; the journey is not a "
            "restart journey"
        )

    def test_the_journey_creates_exactly_one_logical_job(
        self, runtime: Runtime, clock: MovableClock
    ) -> None:
        """Silent duplication is the other way a durable job can be lost."""
        from arkali.execution.durable.records import DurableJobRecord

        with runtime.durable() as (recovery, _execution, _session):
            recovery.job_types.declare(JOB_TYPE, supports_pause=True)
        for _repeat in range(3):
            with runtime.app() as client:
                client.post("/api/jobs", json=enqueue_body())
        with runtime.durable() as (_recovery, execution, session):
            execution.begin_attempt(JOB_ID, OWNER)
        clock.advance(SILENCE)
        for _sweep in range(3):
            with runtime.durable() as (recovery, _execution, _session):
                recovery.recover_lost_executions()
        with runtime.durable() as (_recovery, execution, session):
            rows = session.query(DurableJobRecord).all()  # type: ignore[attr-defined]
            assert len(rows) == 1, f"{len(rows)} durable jobs exist; expected 1"
            assert execution.attempt_count(JOB_ID) == 1, (
                "a repeated sweep consumed extra attempts"
            )


class TestStep20EvidenceAndProvenance:
    """Step 20: Phase 7 evidence recorded through the Phase 6 authorities.

    No second evidence mechanism is created. Artifact identity comes from
    `evidence.artifact` and the chain write from `evidence.audit`, exactly as
    Phase 6 accepted them, and the requirement linkage is a real register id.
    """

    def test_phase_7_evidence_is_recorded_through_c14_and_c15(
        self, runtime: Runtime
    ) -> None:
        payload = b"phase-7 durable runtime evidence: enqueue, execute, recover"
        with runtime.evidence() as (artifacts, chain, _session):
            artifact_id = artifacts.register(
                payload,
                ProvenanceInput(
                    producer_agent="phase-7-package-5",
                    provider_model="none",
                    task_id="phase-7-final-integration",
                    specification_version="C-19",
                    context_hash="phase-7-journey",
                    tests=("tests/execution/test_phase_7_journey.py",),
                    evidence=("ARK-REQ-0027", "ARK-REQ-0059"),
                ),
            )
            record = chain.append(
                EvidenceInput(
                    requirement_id="ARK-REQ-0027",
                    artifact_id=artifact_id,
                    producer="phase-7-package-5",
                    result="PASS",
                    contract_id="C-19",
                    test_id="test_a_job_survives_enqueue_execution_restart_and_recovery",
                )
            )
            head = record.record_hash

        # A fresh runtime: the evidence is durable and still verifies. The
        # chain recomputes its digests rather than reading a stored flag, so
        # asserting `faults` is empty is the real assertion.
        with runtime.evidence() as (artifacts, chain, _session):
            assert artifacts.verify(artifact_id) is True
            stored = chain.require(head)
            assert stored.requirement_id == "ARK-REQ-0027"
            assert stored.artifact_id == artifact_id
            verification = chain.verify()
            assert verification.verified is True
            assert verification.faults == ()
            assert verification.head == head

    def test_the_evidence_names_a_real_register_requirement(
        self, runtime: Runtime
    ) -> None:
        """NEGATIVE CONTROL: no orphan evidence.

        C-15 refuses a requirement id the register does not declare, so an
        evidence record cannot be written against an invented obligation.
        """
        import pytest

        with runtime.evidence() as (artifacts, chain, _session):
            artifact_id = artifacts.register(
                b"orphan probe",
                ProvenanceInput(
                    producer_agent="phase-7-package-5",
                    provider_model="none",
                    task_id="orphan-probe",
                    specification_version="C-19",
                    context_hash="orphan",
                ),
            )
            with pytest.raises(Exception) as refusal:
                chain.append(
                    EvidenceInput(
                        requirement_id="ARK-REQ-9999",
                        artifact_id=artifact_id,
                        producer="phase-7-package-5",
                        result="PASS",
                    )
                )
            assert "ARK-REQ-9999" in str(refusal.value)

    def test_historical_evidence_stays_immutable(self, runtime: Runtime) -> None:
        """Supersession appends; it never edits what was already recorded."""
        with runtime.evidence() as (artifacts, chain, _session):
            artifact_id = artifacts.register(
                b"supersession probe",
                ProvenanceInput(
                    producer_agent="phase-7-package-5",
                    provider_model="none",
                    task_id="supersession",
                    specification_version="C-19",
                    context_hash="supersede",
                ),
            )
            first = chain.append(
                EvidenceInput(
                    requirement_id="ARK-REQ-0059",
                    artifact_id=artifact_id,
                    producer="phase-7-package-5",
                    result="PASS",
                )
            )
            original_hash = first.record_hash
            chain.append(
                EvidenceInput(
                    requirement_id="ARK-REQ-0059",
                    artifact_id=artifact_id,
                    producer="phase-7-package-5",
                    result="PASS",
                    supersedes=original_hash,
                )
            )
        with runtime.evidence() as (_artifacts, chain, _session):
            preserved = chain.require(original_hash)
            assert preserved.record_hash == original_hash
            verification = chain.verify()
            assert verification.verified is True and verification.faults == ()
            assert verification.length == 2, (
                "supersession replaced the predecessor instead of appending"
            )
