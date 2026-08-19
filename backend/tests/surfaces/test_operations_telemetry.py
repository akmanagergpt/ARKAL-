"""C-34 composed Operations snapshot (ARK-REQ-0168, ARK-REQ-0170): the whole
real, live telemetry view in one call, itself under a real PDP/PEP decision.
"""

from __future__ import annotations

import pytest

from arkali.control.policy.pep import PolicyEnforcementPoint
from arkali.control.policy.policy_errors import PolicyDenied
from arkali.engineering.localai import host_probe
from arkali.execution.durable.job_store import JobSubmission
from arkali.kernel.contracts.honest_state import HonestState
from arkali.surfaces.operations.telemetry import observe_operations
from tests.surfaces.operations_harness import (  # noqa: F401 - fixtures by import
    OperationsReopener,
    PepReadAuthorization,
    approval_gate,
    clock,
    database_path,
    pdp,
    reopen,
    vocabulary,
)


class TestObserveOperationsComposesAllThreeProbes:
    def test_a_composed_snapshot_carries_real_runtime_hardware_and_storage(
        self, reopen: OperationsReopener, pdp, tmp_path,
    ) -> None:
        auth = PepReadAuthorization(PolicyEnforcementPoint(pdp, "surfaces.operations.telemetry"))
        with reopen.session() as (recovery, executor, engine, _session):
            snapshot = observe_operations(
                pep=auth,
                durable=(recovery.execution.jobs, recovery, executor),
                engine=engine, workspace_path=str(tmp_path), probe_host=host_probe.probe_host,
            )
        assert snapshot.runtime.jobs_active.state is HonestState.PASS
        assert snapshot.hardware.cpu_logical_cores.state is HonestState.PASS
        assert snapshot.storage.database_reachable.state is HonestState.PASS

    def test_two_calls_are_independent_never_cached(
        self, reopen: OperationsReopener, pdp, tmp_path,
    ) -> None:
        auth = PepReadAuthorization(PolicyEnforcementPoint(pdp, "surfaces.operations.telemetry"))
        with reopen.session() as (recovery, executor, engine, session):
            recovery.execution.jobs.submit(
                JobSubmission(job_id="JOB-A", job_type="arkali.test.noop", idempotency_key="k1")
            )
            session.commit()
            before = observe_operations(
                pep=auth, durable=(recovery.execution.jobs, recovery, executor),
                engine=engine, workspace_path=str(tmp_path), probe_host=host_probe.probe_host,
            )
            recovery.execution.jobs.submit(
                JobSubmission(job_id="JOB-B", job_type="arkali.test.noop", idempotency_key="k2")
            )
            session.commit()
            after = observe_operations(
                pep=auth, durable=(recovery.execution.jobs, recovery, executor),
                engine=engine, workspace_path=str(tmp_path), probe_host=host_probe.probe_host,
            )
        assert after.runtime.jobs_queued.value == before.runtime.jobs_queued.value + 1.0


def _denying_read_pep(root) -> PolicyEnforcementPoint:  # noqa: ANN001
    """A REAL PEP over a REAL PDP whose authority map denies READ_FILE.

    Mirrors `tests.execution.durable_harness.denying_pep`'s exact shape
    (copy the canonical documents into an isolated root, then deny one
    operation class in that copy) but targets `READ_FILE` - the class this
    module's own gate actually requests - rather than
    `WRITE_WORKSPACE_FILE`.
    """
    import shutil

    import yaml

    from arkali.control.policy.pdp import PolicyDecisionPoint
    from tests.execution.durable_harness import PDP_DOCUMENTS, REPO

    for relative in PDP_DOCUMENTS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    mapping = yaml.safe_load(
        (root / "docs/canonical/AUTHORITY_MAP.yaml").read_text(encoding="utf-8")
    )
    mapping["operation_classes"]["READ_FILE"] = {"default": "DENY", "fixed": "DENY"}
    (root / "docs/canonical/AUTHORITY_MAP.yaml").write_text(
        yaml.safe_dump(mapping), encoding="utf-8"
    )
    return PolicyEnforcementPoint(PolicyDecisionPoint.load(root), "denied")


class TestTheAggregateViewIsGenuinelyGated:
    def test_a_denying_pep_refuses_the_composed_view_before_reading_anything(
        self, reopen: OperationsReopener, tmp_path,
    ) -> None:
        """NEGATIVE CONTROL: a real PDP loaded from a denying authority map
        refuses `observe_operations` itself - proving the gate call at the
        top of this module's own function is not decorative."""
        auth = PepReadAuthorization(_denying_read_pep(tmp_path / "denied-root"))
        with reopen.session() as (recovery, executor, engine, _session):
            with pytest.raises(PolicyDenied):
                observe_operations(
                    pep=auth, durable=(recovery.execution.jobs, recovery, executor),
                    engine=engine, workspace_path=str(tmp_path),
                    probe_host=host_probe.probe_host,
                )
