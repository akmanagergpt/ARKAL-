#!/usr/bin/env python3
"""Serve the Command Center API over a real, migrated SQLite database.

Usage: python scripts/run_command_center.py [--host H] [--port P] [--db PATH]

WHY THIS EXISTS. The T10 browser tier requires a real user journey against a
real backend (VERIFICATION_ARCHITECTURE.md 1.1: no mocks, execution level L2).
`TestClient` speaks ASGI in-process and never opens a socket, so a browser
cannot reach it. This binds the *existing* application to a real port.

WHAT IT IS NOT. It builds no application of its own. `create_app` in
`surfaces.command` is the only Command Center factory, the engine comes from
`kernel.persistence`, the schema comes from the real Alembic chain and the PDP
is loaded from the canonical authority map. Nothing here is substituted, and a
control in `backend/tests/structural/test_browser_journey_integrity.py` fails if
this launcher ever grows a second app, a second engine or an in-memory database.

LOOPBACK ONLY. It binds 127.0.0.1 by default. This is a local-first product and
an evidence harness, not a deployment path.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

ROOT = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "backend"))

import uvicorn  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from arkali.acceptance.findings import Finding, parse_findings  # noqa: E402
from arkali.acceptance.governance_state import OPEN_BLOCKERS, GovernanceState  # noqa: E402
from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.control.policy.workflow_approval import WorkflowApprovalGate  # noqa: E402
from arkali.control.architecture.authority_map import AuthorityMap  # noqa: E402
from arkali.engineering.candidate.campaign_budget import (  # noqa: E402
    CampaignBudget,
    GenerationCampaignLedger,
    list_campaign_ids,
)
from arkali.engineering.candidate.ledger import CandidateLedger  # noqa: E402
from arkali.engineering.factory.production_orchestration import (  # noqa: E402
    ProductionFactory,
    ProductionGoalRequest,
)
from arkali.engineering.localai import host_probe  # noqa: E402
from arkali.engineering.localai.capability_query import (  # noqa: E402
    compose_real_capability_authority,
)
from arkali.engineering.localai.ollama_adapter import OllamaAdapter  # noqa: E402
from arkali.evidence.artifact.blob_store import ArtifactBlobStore  # noqa: E402
from arkali.execution.durable.recovery import JobRecovery  # noqa: E402
from arkali.execution.durable.job_state_machine import QUEUED as _JOB_QUEUED  # noqa: E402
from arkali.execution.durable.job_state_machine import (  # noqa: E402
    CHECKPOINTED, PAUSED, RECOVERABLE, RESUMING, RUNNING,
)
from arkali.execution.durable.job_store import JobStore, JobSubmission  # noqa: E402
from arkali.execution.workflow.executor import WorkflowExecutor  # noqa: E402
from arkali.execution.workflow.graph_model import (  # noqa: E402
    WorkflowEdge,
    WorkflowGraphDocument,
    WorkflowNode,
)
from arkali.execution.workflow.graph_store import WorkflowGraphStore  # noqa: E402
from arkali.execution.workflow.graph_vocabulary import GraphVocabulary  # noqa: E402
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
    sqlite_url,
)
from arkali.kernel.persistence.migrations import ALEMBIC_INI  # noqa: E402
from arkali.kernel.persistence.session import (  # noqa: E402
    create_session_factory,
    unit_of_work,
)
from arkali.surfaces.command.app import _CommandExtensions, create_app  # noqa: E402
from arkali.surfaces.command.factory_history import (  # noqa: E402
    FactoryCampaignAttempt,
    FactoryCampaignSummary,
    FactoryCandidateSummary,
)
from arkali.surfaces.command.product_change_bridge import (  # noqa: E402
    _ChangeNotAuthorizedError,
    _ChangeStaleBaseError,
    _ChangeVerificationFailedError,
    _ProductChangeWiring,
)
from arkali.surfaces.command.product_preview_resolution import (  # noqa: E402
    _PreviewBridgeWiring,
)
from arkali.surfaces.command.providers import (  # noqa: E402
    ProvidersSnapshotSource,
    _build_providers_router,
    _ProvidersSnapshotResponse,
)
from arkali.surfaces.command.code_intelligence import (  # noqa: E402
    CodeIntelligenceSnapshotSource,
    _build_code_intelligence_router,
    _observe_code_intelligence,
)
from arkali.surfaces.command.diagnostics import (  # noqa: E402
    DiagnosticsSnapshotSource,
    _build_diagnostics_router,
    _DiagnosticsFinding,
    _DiagnosticsSnapshotResponse,
)
from arkali.surfaces.operations.ai_review_bundle import observe_architecture  # noqa: E402
from arkali.surfaces.operations.contracts import DimensionReading  # noqa: E402
from arkali.control.registry.project.registry import ProjectRegistry  # noqa: E402
from arkali.engineering.product_change.change_plan import ChangePlan  # noqa: E402
from arkali.engineering.product_change.errors import (  # noqa: E402
    PromotionNotAuthorizedError,
    StaleBaseRevisionError,
    VerificationFailedError,
)
from arkali.engineering.product_change.modification import PreparedModification  # noqa: E402
from arkali.engineering.product_change.promotion import promote_modification  # noqa: E402
from arkali.engineering.product_change.verification import VerificationResult  # noqa: E402
from arkali.evidence.artifact.store import ArtifactStore  # noqa: E402


class _DurableFactorySink:
    def __init__(self, store: JobStore) -> None:
        self._store = store

    def enqueue(self, request_id: str, payload: dict[str, object]) -> str:
        record = self._store.submit(JobSubmission(
            job_id=request_id,
            job_type="software_factory.production",
            idempotency_key=request_id,
            payload=payload,
        ))
        return record.job_id


_FACTORY_WORKER_SCRIPT = pathlib.Path(__file__).resolve().with_name("run_factory_worker.py")
_FACTORY_WORKER_DB = ROOT / "var" / "command_center.db"  # run_factory_worker.py's own fixed path


def _spawn_factory_worker_once() -> None:
    """DEF-009 composition wiring: run the existing, unmodified one-shot
    `run_factory_worker.py` consumer as a detached background subprocess.

    This makes no admission or priority decision among competing jobs - it
    is a pure 1:1 dispatch triggered by the exact request that created the
    work, never a perpetual poll. D-027 forbids a second *scheduler*; this
    is the same "manual re-run" deployment pattern the worker's own module
    docstring already names as in-scope, just automated. No worker logic is
    copied here - only `python scripts/run_factory_worker.py` is invoked,
    unchanged, exactly as an operator would from a terminal.
    """
    log_dir = ROOT / "var" / "factory" / "worker_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"worker-{time.time_ns()}.log"
    with log_path.open("wb") as log_file:
        subprocess.Popen(
            [sys.executable, str(_FACTORY_WORKER_SCRIPT)],
            cwd=str(ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )


def _should_auto_spawn_worker(
    can_auto_spawn: bool, durable_job_id: str | None, fresh_lifecycle_state: str | None
) -> bool:
    """Pure decision extracted for direct unit-testing.

    `submit_goal` always reports `QUEUED` for any call reaching the enqueue
    branch, including an idempotent rediscovery of an already-RUNNING or
    terminal job. Only a fresh read of the job's own real lifecycle state
    (`fresh_lifecycle_state`) tells a genuinely new, still-unclaimed job
    apart from that; spawning on the stale report would start a second,
    redundant worker racing the first.
    """
    return (
        can_auto_spawn
        and durable_job_id is not None
        and fresh_lifecycle_state == _JOB_QUEUED
    )


#: `ARK-REQ-0048`'s own owning phase (register-verified in tests) - the
#: Capability Graph's activation gate every real caller must answer the
#: identical way.
_CAPABILITY_ACTIVATION_PHASE = "9B"


def _current_capability_phase(repo_root: pathlib.Path) -> str:
    """`GovernanceState` (`acceptance.engine`) is asked here, not inside
    `capability_query.py`: that module lives in `engineering.localai`, a
    lower architecture layer, and importing `acceptance.engine` from it
    extended the repository's longest dependency chain past
    `max_orchestration_depth` (proven by trying it, not assumed). This
    script is outside the measured architecture graph, exactly like every
    `host_probe`/`compose_real_capability_authority` composition below.
    Shared by every real caller of `compose_real_capability_authority` in
    this script, so "has phase 9B been reached" is answered once, the same
    way, rather than re-derived per composition.
    """
    governance = GovernanceState.load(repo_root)
    return (
        _CAPABILITY_ACTIVATION_PHASE
        if governance.phase(_CAPABILITY_ACTIVATION_PHASE).is_accepted
        else str(governance.current_work_phase())
    )


def _providers_wiring(repo_root: pathlib.Path) -> ProvidersSnapshotSource:
    """Sağlayıcılar ve Modeller composition-root wiring - the identical
    probe-once-not-per-request shape `_factory_submitter` below already
    establishes for Factory routing, composed independently here so this
    route's own lifecycle never depends on Factory's. Host facts
    (accelerator presence) are probed fresh on every call instead, the
    identical choice `_operations_wiring` already makes for
    `host_probe.probe_host`.
    """
    authority = compose_real_capability_authority(
        repo_root, OllamaAdapter(), _current_capability_phase(repo_root),
    )

    def snapshot() -> _ProvidersSnapshotResponse:
        model_id = authority.default_capability_id
        if model_id is None:
            local_runtime = DimensionReading.not_configured(
                "local_runtime", "yerel bir AI modeli şu anda kullanılamıyor",
            )
            configured_model = DimensionReading.not_configured(
                "configured_model", "hiçbir model yapılandırılmamış",
            )
        else:
            local_runtime = DimensionReading.real(
                "local_runtime", 1.0, f"yerel model kullanılabilir: {model_id}",
            )
            configured_model = DimensionReading.real(
                "configured_model", 1.0, f"yapılandırılmış model: {model_id}",
            )
        host = host_probe.probe_host()
        accelerator = (
            DimensionReading.real("accelerator", 1.0, host.accelerator_detail)
            if host.accelerator_present
            else DimensionReading.not_configured("accelerator", host.accelerator_detail)
        )
        return _ProvidersSnapshotResponse(
            local_runtime=local_runtime,
            configured_model=configured_model,
            accelerator=accelerator,
        )

    return snapshot


def _code_intelligence_wiring(repo_root: pathlib.Path) -> CodeIntelligenceSnapshotSource:
    """Kod Zekâsı composition-root wiring - each real call re-derives the
    snapshot fresh from `backend/arkali`'s own real source, the identical
    "re-derived on every call, never cached" discipline the existing
    `/api/operations/architecture` route already established for the same
    underlying `observe_architecture` call.
    """
    backend_arkali_root = repo_root / "backend" / "arkali"

    def snapshot():  # noqa: ANN202
        return _observe_code_intelligence(backend_arkali_root, repo_root)

    return snapshot


#: The same job-type/checkpoint-phase names `_providers_wiring` above and
#: `scripts/task_packet.py::_operational_snapshot` both already use.
_PRODUCT_CHANGE_JOB_TYPE = "managed_product.change"
_READY_FOR_REVIEW_PHASE = "ready_for_review"
_DIAGNOSTICS_ACTIVE_JOB_STATES = (
    _JOB_QUEUED, RUNNING, CHECKPOINTED, PAUSED, RESUMING, RECOVERABLE,
)
_DIAGNOSTICS_SEVERITY_RANK = {"BLOCKER": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
_DIAGNOSTICS_MAX_TOP_FINDINGS = 5
_DIAGNOSTICS_MAX_DETAIL_CHARS = 200


def _diagnostics_operational_hint(
    stopping_count: int, session: Session, pep: PolicyEnforcementPoint,
) -> str:
    """The identical five-value vocabulary and priority order `scripts/
    task_packet.py::_live_next_action_hint` already established, derived
    fresh here from the real `JobStore` rather than shared code across the
    `scripts/`<->`backend/arkali` boundary (`diagnostics.py`'s own module
    docstring names exactly why that boundary is one-directional)."""
    if stopping_count > 0:
        return "resolve_open_finding"
    try:
        store = JobStore(session, pep)
        active = store.list_by_state(_DIAGNOSTICS_ACTIVE_JOB_STATES)
    except Exception:
        return "live_state_unavailable"
    for job in active:
        if job.job_type != _PRODUCT_CHANGE_JOB_TYPE:
            continue
        checkpoints = store.checkpoints(job.job_id)
        phase = checkpoints[-1].payload.get("phase") if checkpoints else None
        if phase == _READY_FOR_REVIEW_PHASE:
            return "review_pending_product_change"
    return "pending_operational_job" if active else "no_pending_operational_work"


def _diagnostics_finding_rank(finding: Finding) -> tuple[int, str]:
    return (
        _DIAGNOSTICS_SEVERITY_RANK.get(finding.severity.upper(), len(_DIAGNOSTICS_SEVERITY_RANK)),
        finding.identifier,
    )


def _diagnostics_top_findings(all_findings: tuple[Finding, ...]) -> tuple[_DiagnosticsFinding, ...]:
    open_findings = sorted(
        (f for f in all_findings if f.is_open), key=_diagnostics_finding_rank,
    )
    return tuple(
        _DiagnosticsFinding(
            identifier=f.identifier, severity=f.severity, status=f.status.value,
            detail=" ".join(f.detail.split())[:_DIAGNOSTICS_MAX_DETAIL_CHARS],
        )
        for f in open_findings[:_DIAGNOSTICS_MAX_TOP_FINDINGS]
    )


def _diagnostics_wiring(
    pdp: PolicyDecisionPoint, repo_root: pathlib.Path,
) -> DiagnosticsSnapshotSource:
    """Tanılama composition-root wiring - the identical reason `operations.
    py`'s own module docstring already documents for `PolicyEnforcementPoint`
    / `host_probe`: this script sits outside the measured architecture
    graph, so composing real `GovernanceState`/`findings.parse_findings`
    (already at `acceptance.engine`'s own orchestration-depth ceiling) and
    a real `JobStore`-backed `PolicyEnforcementPoint` (already at `control.
    policy.pep`'s own fan-in ceiling) here adds no edge the architecture
    budget would ever see.
    """
    def snapshot(session: Session) -> _DiagnosticsSnapshotResponse:
        governance = GovernanceState.load(repo_root)
        stopping = governance.open_stopping_findings
        all_findings = parse_findings((repo_root / OPEN_BLOCKERS).read_text(encoding="utf-8"))
        architecture = observe_architecture(repo_root)
        pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
        hint = _diagnostics_operational_hint(len(stopping), session, pep)
        healthy = len(stopping) == 0 and not architecture.violations
        return _DiagnosticsSnapshotResponse(
            overall_status="HEALTHY" if healthy else "ATTENTION_NEEDED",
            open_stopping_count=len(stopping),
            top_findings=_diagnostics_top_findings(all_findings),
            architecture=architecture,
            operational_hint=hint,
            generated_at=dt.datetime.now(dt.UTC),
        )

    return snapshot


def _factory_submitter(
    pdp: PolicyDecisionPoint, repo_root: pathlib.Path, database: pathlib.Path
) -> Callable[..., Any]:
    """DEF-009 FLOW A CONVERGENCE AUTHORIZATION, item 3: `ProductionFactory`
    is composed with a real `capability_query` for the first time, derived
    once here (not per request) by probing the real local Ollama runtime -
    a bounded, read-only probe, the same kind every `LocalRuntimeAdapter`
    caller already performs. Nothing about which model wins is decided by
    this launcher or by the UI: `compose_real_capability_authority` derives
    it entirely from what the real runtime and the real, hardware-aware
    suitability verdict report right now. A request that already names a
    `capability_id` is never overridden; only an absent one is defaulted,
    and only to a capability this same probe found genuinely configured -
    if none is, the default stays `None` and routing honestly escalates.
    """
    authority = compose_real_capability_authority(
        repo_root, OllamaAdapter(), _current_capability_phase(repo_root),
    )
    factory = ProductionFactory(AuthorityMap.load(repo_root), authority.query)
    # `run_factory_worker.py` opens its own fixed `var/command_center.db` by
    # design (its own module docstring: no logic here may be copied into
    # it). Auto-dispatch is only correct when this Command Center is
    # actually serving that same database; a custom `--db` honestly falls
    # back to the pre-existing manual-launch path rather than spawning a
    # worker that would read/write a different database than the one that
    # just queued the job.
    can_auto_spawn = database.resolve() == _FACTORY_WORKER_DB.resolve()

    def submit(session: Session, body: Any) -> Any:
        pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
        fields = body.model_dump()
        if fields.get("capability_id") is None:
            fields["capability_id"] = authority.default_capability_id
        request = ProductionGoalRequest(**fields)
        store = JobStore(session, pep)
        result = factory.submit_goal(request, _DurableFactorySink(store))
        durable_job_id = getattr(result, "durable_job_id", None)
        record = store.get(durable_job_id) if durable_job_id is not None else None
        fresh_state = record.lifecycle_state if record is not None else None
        if _should_auto_spawn_worker(can_auto_spawn, durable_job_id, fresh_state):
            _spawn_factory_worker_once()
        return result

    return submit


def _factory_guide(repo_root: pathlib.Path) -> Callable[..., Any]:
    """One bounded local Qwen-backed discovery turn; never enqueues generation."""
    from arkali.engineering.localai.intake_conversation import (
        IntakeMessage, continue_intake_conversation,
    )

    adapter = OllamaAdapter(json_mode=True, max_output_tokens=1200)
    authority = compose_real_capability_authority(
        repo_root, adapter, _current_capability_phase(repo_root),
    )
    model_id = authority.default_model_id

    def guide(body: Any) -> dict[str, Any]:
        if model_id is None:
            raise RuntimeError("no configured local model is available for guided intake")
        guidance = continue_intake_conversation(
            adapter, model_id,
            tuple(IntakeMessage(**message.model_dump()) for message in body.messages),
        )
        return {**guidance.model_dump(mode="json"), "model_id": model_id}

    return guide


def _workflow_wiring(
    pdp: PolicyDecisionPoint, repo_root: pathlib.Path
) -> tuple[Callable[..., Any], Callable[..., Any], Callable[..., Any]]:
    """The C-20 composition-root wiring, built once over the real vocabulary
    and approval gate. This script lives outside `backend/arkali/` and outside
    the measured architecture graph, so composing `execution.workflow`'s real
    objects here - exactly as the backend integration tests already do - adds
    no edge the architecture budget would ever see. See `workflow.py`'s module
    docstring for why `surfaces.command` itself may not import them directly.
    """
    vocabulary = GraphVocabulary.load(repo_root)
    approval_gate = WorkflowApprovalGate.load(repo_root)

    def document_builder(
        workflow_id: str, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> WorkflowGraphDocument:
        return WorkflowGraphDocument.build(
            vocabulary,
            workflow_id,
            nodes=[WorkflowNode(**n) for n in nodes],
            edges=[WorkflowEdge(**e) for e in edges],
        )

    def graph_store_factory(session: Session) -> WorkflowGraphStore:
        pep = PolicyEnforcementPoint(pdp, "execution.workflow.graph_store")
        return WorkflowGraphStore(session, pep, vocabulary)

    def executor_factory(session: Session) -> WorkflowExecutor:
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return document_builder, graph_store_factory, executor_factory


def _operations_wiring(
    pdp: PolicyDecisionPoint, repo_root: pathlib.Path
) -> tuple[Callable[..., Any], Callable[..., Any], PolicyDecisionPoint, Callable[..., Any]]:
    """The C-34 composition-root wiring (Phase 25) - the identical shape and
    the identical reason `_workflow_wiring` above already established: this
    script sits outside the measured architecture graph, so constructing
    real `JobRecovery`/`WorkflowExecutor` instances (which need a real
    `PolicyEnforcementPoint`) and importing the real
    `engineering.localai.host_probe.probe_host` here adds no edge the
    architecture budget would ever see. See `operations.py`'s own module
    docstring for why `surfaces.command` itself may not do either directly.
    """
    vocabulary = GraphVocabulary.load(repo_root)
    approval_gate = WorkflowApprovalGate.load(repo_root)

    def job_recovery_factory(session: Session) -> JobRecovery:
        pep = PolicyEnforcementPoint(pdp, "execution.durable.execution")
        return JobRecovery(session, pep)

    def executor_factory(session: Session) -> WorkflowExecutor:
        return WorkflowExecutor(session, pdp, vocabulary, approval_gate)

    return job_recovery_factory, executor_factory, pdp, host_probe.probe_host


def _factory_candidate_history(repo_root: pathlib.Path) -> Callable[[], tuple[FactoryCandidateSummary, ...]]:
    """Real, unmodified `engineering.candidate.ledger.CandidateLedger`,
    composed here (outside the measured architecture graph) exactly as
    `factory_history.py`'s own module docstring requires."""
    ledger = CandidateLedger(repo_root / "var" / "factory" / "candidates" / "_ledger")

    def read() -> tuple[FactoryCandidateSummary, ...]:
        return tuple(
            FactoryCandidateSummary(
                candidate_id=candidate_id,
                state=ledger.classify(candidate_id),
                recorded_at=str((ledger.latest(candidate_id) or {}).get("recorded_at", "")),
            )
            for candidate_id in ledger.all_candidate_ids()
        )

    return read


def _factory_campaign_history(repo_root: pathlib.Path) -> Callable[[], tuple[FactoryCampaignSummary, ...]]:
    """Real, unmodified `engineering.candidate.campaign_budget` ledgers,
    composed here for the identical reason `_factory_candidate_history`
    above is."""
    campaigns_root = repo_root / "var" / "factory" / "campaigns"

    def read() -> tuple[FactoryCampaignSummary, ...]:
        summaries = []
        for campaign_id in list_campaign_ids(campaigns_root):
            campaign = GenerationCampaignLedger.load_or_create(
                campaigns_root, campaign_id, CampaignBudget(),
            )
            summaries.append(FactoryCampaignSummary(
                campaign_id=campaign_id,
                max_new_candidates=campaign.budget.max_new_candidates,
                max_total_seconds=campaign.budget.max_total_seconds,
                max_same_fingerprint_repeats=campaign.budget.max_same_fingerprint_repeats,
                consumed_candidates=campaign.consumed_candidates,
                consumed_seconds=campaign.consumed_seconds,
                status=campaign.status(),
                attempts=tuple(
                    FactoryCampaignAttempt(
                        candidate_id=str(a["candidate_id"]),
                        outcome=str(a["outcome"]),
                        failure_class=a.get("failure_class"),  # type: ignore[arg-type]
                        fingerprint=a.get("fingerprint"),  # type: ignore[arg-type]
                        elapsed_seconds=float(a["elapsed_seconds"]),  # type: ignore[arg-type]
                        recorded_at=str(a["recorded_at"]),
                    )
                    for a in campaign.attempts()
                ),
            ))
        return tuple(summaries)

    return read


def _preview_bridge_wiring(repo_root: pathlib.Path) -> _PreviewBridgeWiring:
    """Real, unmodified `evidence.artifact` + `engineering.candidate.ledger.
    CandidateLedger`, composed here (outside the measured architecture
    graph, exactly as `_factory_candidate_history` above already is) for
    the Product Detail -> preview bridge (D-029's own follow-on).

    A SECOND real database, `var/factory/evidence/repair-evidence.db` --
    the same file `product_registration.py`'s own callers
    (`register_managed_product.py`, `run_golden_acceptance.py`) already
    write provenance artifacts into, never a new one -- migrated and
    engined exactly as `migrate`/`engine` above are for `command_center.
    db`. `session_scope`'s own two-line shape is duplicated rather than
    shared for the same reason `app.py`'s own `session_scope` closure is
    private to `create_app`: each real database gets its own real
    generator, and sharing one would blur which engine a given request's
    session actually belongs to.
    """
    evidence_db = repo_root / "var" / "factory" / "evidence" / "repair-evidence.db"
    evidence_db.parent.mkdir(parents=True, exist_ok=True)
    config = Config(str(ROOT / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(evidence_db))
    command.upgrade(config, "head")
    evidence_engine = create_persistence_engine(sqlite_url(evidence_db))
    evidence_factory = create_session_factory(evidence_engine)

    def artifact_session_scope() -> Any:
        with unit_of_work(evidence_factory) as session:
            yield session

    pdp = PolicyDecisionPoint.load(repo_root)
    blobs = ArtifactBlobStore(
        repo_root / "var" / "factory" / "evidence" / "blobs",
        PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"),
    )
    ledger = CandidateLedger(repo_root / "var" / "factory" / "candidates" / "_ledger")
    return _PreviewBridgeWiring(
        artifact_session_scope=artifact_session_scope, artifact_blobs=blobs, ledger=ledger,
    )


def _product_change_wiring(repo_root: pathlib.Path, command_center_db: pathlib.Path) -> _ProductChangeWiring:
    """The real "Kabul Et" promote verb (D-030 V1), composed here -- outside
    the measured architecture graph -- exactly as `_preview_bridge_wiring`
    above is for its own bridge. Reconstructs a real `PreparedModification`
    from the change job's own `ready_for_review` checkpoint (never
    fabricated: `plan` is re-read from the already-registered artifact,
    `verification` from the worker's own real recorded verdict) and calls
    the real, unmodified `promote_modification`, translating its typed
    refusals into the three local error classes `surfaces.command` may
    map without importing `engineering.product_change` itself.
    """
    evidence_db = repo_root / "var" / "factory" / "evidence" / "repair-evidence.db"
    pdp = PolicyDecisionPoint.load(repo_root)
    blobs = ArtifactBlobStore(
        repo_root / "var" / "factory" / "evidence" / "blobs",
        PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store"),
    )
    governance = GovernanceState.load(repo_root)

    class _RealChangePromoter:
        def promote(self, project_id: str, ready: dict[str, Any]) -> dict[str, Any]:
            evidence_engine = create_persistence_engine(sqlite_url(evidence_db))
            registry_engine = create_persistence_engine(sqlite_url(command_center_db))
            try:
                with unit_of_work(create_session_factory(evidence_engine)) as evidence_session:
                    artifacts = ArtifactStore(evidence_session, blobs)
                    plan_ref = str(ready["plan_ref"])
                    prepared = PreparedModification(
                        workspace=_StubWorkspace(pathlib.Path(str(ready["workspace_root"]))),
                        product_root=pathlib.Path(str(ready["workspace_root"])) / "snapshot",
                        base_revision_id=str(ready["base_revision_id"]),
                        plan=ChangePlan.model_validate_json(artifacts.content_of(plan_ref)),
                        plan_ref=plan_ref, changeset_ref=str(ready["changeset_ref"]),
                        verification=VerificationResult(
                            passed=bool(ready["verification_passed"]), checked_paths=[],
                            failures=list(ready.get("verification_failures", [])),
                        ),
                    )
                    with unit_of_work(create_session_factory(registry_engine)) as registry_session:
                        try:
                            revision = promote_modification(
                                project_id, prepared, registry=ProjectRegistry(registry_session),
                                artifacts=artifacts, human_gates=governance,
                                issuer_identity="command-center",
                            )
                        except VerificationFailedError as error:
                            raise _ChangeVerificationFailedError(str(error)) from error
                        except StaleBaseRevisionError as error:
                            raise _ChangeStaleBaseError(str(error)) from error
                        except PromotionNotAuthorizedError as error:
                            raise _ChangeNotAuthorizedError(str(error)) from error
                        return {
                            "revision_id": revision.revision_id,
                            "provenance_ref": revision.provenance_ref,
                        }
            finally:
                evidence_engine.dispose()
                registry_engine.dispose()

    return _ProductChangeWiring(promoter=_RealChangePromoter())


class _StubWorkspace:
    """Satisfies `PreparedModification.workspace`'s own real need (`.root`
    only -- `promote_modification` never reads it) without holding a real
    `CandidateWorkspace`; the worker process that allocated one has
    already exited by the time a human clicks "Kabul Et"."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root


def migrate(database: pathlib.Path) -> None:
    """Bring the database to head with the real migration chain."""
    config = Config(str(ROOT / "backend" / ALEMBIC_INI))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", sqlite_url(database))
    command.upgrade(config, "head")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--db",
        default=str(ROOT / "var" / "command_center.db"),
        help="path to the SQLite file; created and migrated if absent",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help=(
            "delete the database and its WAL sidecars before migrating. The T10 "
            "journey asserts that what it created is still there after a reload "
            "and in a new browser context; if a previous run's rows survived, "
            "those assertions could pass without the claim being earned. Only "
            "this process may do the deletion, because only it holds the handle."
        ),
    )
    parser.add_argument(
        "--shutdown-sentinel",
        default=None,
        help=(
            "optional fixed desktop-lifecycle sentinel; when its owning desktop "
            "process removes it, uvicorn completes a graceful shutdown"
        ),
    )
    args = parser.parse_args(argv[1:])

    database = pathlib.Path(args.db).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    if args.fresh:
        for suffix in ("", "-wal", "-shm", "-journal"):
            pathlib.Path(f"{database}{suffix}").unlink(missing_ok=True)
    migrate(database)

    engine = create_persistence_engine(sqlite_url(database))
    pdp = PolicyDecisionPoint.load(ROOT)
    app = create_app(
        engine, pdp, workflow_wiring=_workflow_wiring(pdp, ROOT),
        extensions=_CommandExtensions(
            operations_wiring=_operations_wiring(pdp, ROOT),
            operations_repo_root=ROOT,
            factory_submitter=_factory_submitter(pdp, ROOT, database),
            factory_guide=_factory_guide(ROOT),
            factory_candidate_history=_factory_candidate_history(ROOT),
            factory_campaign_history=_factory_campaign_history(ROOT),
            preview_bridge=_preview_bridge_wiring(ROOT),
            product_change=_product_change_wiring(ROOT, database),
            providers_wiring=_providers_wiring(ROOT),
            code_intelligence_wiring=_code_intelligence_wiring(ROOT),
            diagnostics_wiring=_diagnostics_wiring(pdp, ROOT),
        ),
    )
    print(f"command center on http://{args.host}:{args.port} over {database}")
    config = uvicorn.Config(app, host=args.host, port=args.port, log_level="warning")
    server = uvicorn.Server(config)
    if args.shutdown_sentinel is not None:
        sentinel = pathlib.Path(args.shutdown_sentinel).resolve()
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("ARKALI desktop backend owner\n", encoding="utf-8")

        def watch_desktop_owner() -> None:
            while sentinel.exists() and not server.should_exit:
                time.sleep(0.1)
            if not sentinel.exists():
                server.should_exit = True

        threading.Thread(
            target=watch_desktop_owner,
            name="arkali-desktop-shutdown",
            daemon=True,
        ).start()
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
