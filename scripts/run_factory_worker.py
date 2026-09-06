#!/usr/bin/env python3
"""The real `software_factory.production` job consumer.

ARKALI COMMAND CENTER — DEF-009 FLOW A CONVERGENCE AUTHORIZATION, items 4-6.
Human-authorized worker implementation. Claims AT MOST ONE real, durable
`software_factory.production` job (C-19, `execution.durable`) already
queued by the real `/api/factory/goals` intake, and hands it to the exact
same real, canonical generation entry point `scripts/run_staged_generation.py`
already uses unchanged: `generate_staged_model_product`
(`engineering.factory.component_generation`). No generation logic is
copied or reimplemented here — this script's only job is durable-job
lifecycle plumbing around a call it does not alter.

WHY A SEPARATE PROCESS, NOT A THREAD INSIDE THE WEB SERVER. `ARK-REQ-0027`:
"no long AI work in HTTP requests." A staged-generation run takes minutes;
every real run recorded this session took 25-55 real minutes. Exactly the
same reason `run_staged_generation.py` is its own process rather than code
inside `surfaces.command`.

WHY NOT A LOOP. This process claims one job, processes it to a real
terminal outcome (or a real interruption), and exits. D-027 forbids a
second scheduler; running this repeatedly under an operator's own
supervision (cron, a manual re-run, a future real worker-loop authority)
is a deployment decision outside this script's scope, and "maksimum 1
user-triggered generation job... retry storm yok" (this turn's own cost
bound) makes a self-looping worker exactly the wrong shape to build today.

WHAT IS REUSED, UNCHANGED. `JobStore` (C-19, claim via `list_by_state` +
`transition`, checkpoint for real progress), `CandidateLedger` +
`WorkspaceAuthority` (`engineering.candidate`, real candidate identity and
an isolated real workspace), `derive_blueprint` (deterministic — the same
call the real intake already made, re-run here rather than deserialising a
stored blueprint, since identical `goal_text` always yields a
byte-identical blueprint), `generate_staged_model_product`
(`engineering.factory`, the real staged pipeline), `ModelProductEnvelope`
+ `inspect_product_files` (the real final whole-product gate), and
`ArtifactStore` (real, content-addressed evidence, the same `_freeze`
shape `run_staged_generation.py` already uses).

WHAT IS NEW. Only the plumbing that connects a real durable job to that
unchanged call: candidate identity is derived from the real job id
(`factory-<job_id>`, never `golden-work-*` — that naming stays reserved for
the manual verification track) and the durable job's own real lifecycle
state and checkpoints are updated so the Command Center can show real
progress without a second progress-state store.

F-0078 (`PRODUCTION_FACTORY_ATTEMPT_OBSERVABILITY_GAP`). `model_factory`
now wraps its real adapter in `_ObservedModel`, a copy (not an import) of
`run_staged_generation.py`'s own private F-0070 wrapper, freezing every
real attempt's own diagnostic facts through this script's own already-
existing `_freeze()`; a terminal `STAGE_FAILED` payload also now carries
`error.last_raw_output`, matching `run_staged_generation.py`'s own shape.
Diagnostic provenance only — no retry, promotion, fingerprint, checker,
or candidate-source decision is made or altered by this wiring.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from arkali.control.architecture.authority_map import AuthorityMap  # noqa: E402
from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.control.specification.blueprint_engine import derive_blueprint  # noqa: E402
from arkali.engineering.candidate.errors import GoalAlreadyAcceptedError  # noqa: E402
from arkali.engineering.candidate.ledger import (  # noqa: E402
    CandidateLedger,
    FINAL_GATE_FAILED,
    GenerationProvenance,
    GENERATING,
    hash_text,
    INTERRUPTED,
    STAGED_GENERATION_PASS,
    STAGE_FAILED,
)
from arkali.engineering.candidate.workspace import WorkspaceAuthority  # noqa: E402
from arkali.engineering.factory.component_generation import (  # noqa: E402
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_TIMEOUT_SECONDS,
    generate_staged_model_product,
)
from arkali.engineering.factory.errors import ModelGenerationError  # noqa: E402
from arkali.engineering.factory.generation_stages import StageVocabulary  # noqa: E402
from arkali.engineering.factory.model_product_generation import (  # noqa: E402
    GeneratedFile,
    ModelProductEnvelope,
)
from arkali.engineering.factory.product_preflight import (  # noqa: E402
    ProductSemanticPreflightError,
    inspect_product_files,
)
from arkali.engineering.localai.ollama_adapter import OllamaAdapter  # noqa: E402
from arkali.evidence.artifact.blob_store import ArtifactBlobStore  # noqa: E402
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput  # noqa: E402
from arkali.execution.durable.job_state_machine import (  # noqa: E402
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
from factory_acceptance import (  # noqa: E402
    _accept as _run_acceptance,
    _candidate_contract_files,
    _resolve_scenario,
)

JOB_TYPE = "software_factory.production"


def _freeze(
    payload: bytes, task_id: str, context_hash: str,
    evidence: tuple[str, ...], provider_model: str,
) -> str:
    """Byte-for-byte the same evidence shape `run_staged_generation.py`
    already uses — the identical real `ArtifactStore`, never a second one."""
    state = ROOT / "var" / "factory" / "evidence"
    state.mkdir(parents=True, exist_ok=True)
    database = state / "repair-evidence.db"
    if not database.exists():
        cfg = Config(str(ROOT / "backend" / ALEMBIC_INI))
        cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
        cfg.set_main_option("sqlalchemy.url", sqlite_url(database))
        command.upgrade(cfg, "head")
    engine = create_persistence_engine(sqlite_url(database))
    pdp = PolicyDecisionPoint.load(ROOT)
    blobs = ArtifactBlobStore(
        state / "blobs", PolicyEnforcementPoint(pdp, "evidence.artifact.blob_store")
    )
    try:
        with unit_of_work(create_session_factory(engine)) as session:
            return ArtifactStore(session, blobs).register(
                payload,
                ProvenanceInput(
                    producer_agent="engineering.factory",
                    provider_model=provider_model,
                    task_id=task_id,
                    specification_version="phase-30-staged-generation/1.0.0",
                    context_hash=context_hash,
                    evidence=evidence,
                ),
            )
    finally:
        engine.dispose()


class _ObservedModel:
    """F-0078. Byte-for-byte the same wrapper `run_staged_generation.py`'s
    own `_ObservedModel` already is (F-0070) -- copied, not imported,
    matching the pre-existing duplication this script's own `_freeze()`
    already established between these two composition scripts (each
    lives outside the measured architecture graph and owns its own
    composition; neither imports production logic from the other).
    Wraps a real `ModelSource`, delegating `infer` unchanged, and
    additionally freezing each real attempt's own diagnostic facts as a
    real, content-addressed artifact via THIS script's own already-
    existing `_freeze()`/`ArtifactStore` mechanism -- never a second
    authoritative store, and never a substitute for the candidate
    ledger, the terminal stage evidence, or the durable job's own
    checkpoints, none of which this touches. `record_attempt` is a real,
    optional method `component_generation._notify_attempt` discovers
    structurally (`getattr(model, "record_attempt", None)`); every
    caller that does not define it is completely unaffected. A failure
    inside `record_attempt` is caught by `_notify_attempt` itself, never
    here -- this class stays a thin, honest wrapper, not a second place
    that decides what "diagnostic-only, never fatal" means.
    """

    def __init__(self, inner: object, candidate_id: str, provider_model: str) -> None:
        self._inner = inner
        self._candidate_id = candidate_id
        self._provider_model = provider_model

    def infer(self, model_id: str, prompt: str, *, timeout_seconds: float = 30.0):  # noqa: ANN201
        return self._inner.infer(model_id, prompt, timeout_seconds=timeout_seconds)  # type: ignore[attr-defined]

    def record_attempt(
        self, stage_name: str, attempt_number: int, repair_strategy: str,
        prompt: str, raw_output: str, findings: tuple[tuple[str, str, str], ...],
        fingerprint: str | None,
    ) -> None:
        payload = json.dumps({
            "candidate_id": self._candidate_id, "stage": stage_name,
            "attempt_number": attempt_number, "repair_strategy": repair_strategy,
            "prompt": prompt, "raw_output": raw_output,
            "findings": [{"code": c, "path": p, "detail": d} for c, p, d in findings],
            "fingerprint": fingerprint,
        }, sort_keys=True).encode()
        _freeze(
            payload, self._candidate_id,
            f"sha256:{__import__('hashlib').sha256(payload).hexdigest()}",
            ("real staged-generation attempt evidence -- diagnostic provenance only "
             "(F-0070, wired into the real production worker by F-0078)",),
            self._provider_model,
        )


def _claim_one_job(store: JobStore) -> object | None:
    """The oldest real QUEUED `software_factory.production` job, or None.

    `JobStore` has no claim/lease primitive (C-19's own module docstring:
    "NOTHING HERE SCHEDULES"); this script processes exactly one job per
    invocation, so a second worker running concurrently is an operator
    error this turn's cost bound already forbids, not a race this script
    must itself resolve.
    """
    candidates = [
        job for job in store.list_by_state((JOB_QUEUED,)) if job.job_type == JOB_TYPE
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda job: job.created_at)
    return candidates[0]


def _run_production_acceptance(candidate_id: str, workspace_root: pathlib.Path) -> dict[str, object]:
    """Production Factory -> canonical acceptance bridge. Calls the exact
    same generic acceptance engine `scripts/run_golden_acceptance.py`'s own
    CLI already uses (`factory_acceptance._accept`), automatically, once
    this worker's own real generation reaches its own real terminal
    `STAGED_GENERATION_PASS` -- never a second acceptance engine, never a
    job-level state change (`JobStore`'s own `SUCCEEDED` below still means
    exactly "generation completed"; `CandidateLedger` alone owns what
    happens to the candidate next). `workspace_root` is this worker's own
    already-real, already-trusted workspace directory -- no `_candidate()`-
    style identity-string resolution is needed or performed here, since
    this caller never received an untrusted id to resolve in the first
    place. A real, terminal, unaccepted outcome (`ACCEPTANCE_PLAN_
    INCOMPLETE`, `GOLDEN_ACCEPTANCE_FAILED`, ...) is returned exactly as
    `_resolve_scenario`/`_accept` themselves classify it -- this function
    invents no new outcome vocabulary and repairs nothing."""
    contract_files = _candidate_contract_files(workspace_root)
    resolved = _resolve_scenario(candidate_id, contract_files, None)
    if isinstance(resolved, dict):
        return resolved
    scenario, scenario_path = resolved
    return _run_acceptance(candidate_id, workspace_root, scenario, scenario_path)


def main(argv: list[str]) -> int:
    db_path = ROOT / "var" / "command_center.db"
    engine = create_persistence_engine(sqlite_url(db_path))
    pdp = PolicyDecisionPoint.load(ROOT)
    session_factory = create_session_factory(engine)

    with unit_of_work(session_factory) as session:
        pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
        store = JobStore(session, pep)
        job = _claim_one_job(store)
        if job is None:
            print(json.dumps({"outcome": "NO_JOB_QUEUED"}))
            return 0
        job_id = job.job_id
        goal_text = job.payload["goal"]["goal_text"]
        store.transition(job_id, JOB_RUNNING)
        store.checkpoint(job_id, {"phase": "claimed", "goal_text": goal_text})

    engine.dispose()

    candidates_root = ROOT / "var" / "factory" / "candidates"
    ledger = CandidateLedger(candidates_root / "_ledger")
    goal_hash = hash_text(goal_text)
    already_accepted = ledger.accepted_candidate_for_goal(goal_hash)
    candidate_id = f"factory-{job_id}"
    provider_model = "ollama/qwen2.5-coder:14b"
    started = time.monotonic()

    def _checkpoint(detail: dict[str, object]) -> None:
        """Real progress evidence, in the real job's own checkpoint history —
        never a second progress-state store."""
        job_engine = create_persistence_engine(sqlite_url(db_path))
        try:
            with unit_of_work(create_session_factory(job_engine)) as job_session:
                job_pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
                JobStore(job_session, job_pep).checkpoint(job_id, detail)
        finally:
            job_engine.dispose()

    def _finish_job(state: str, detail: dict[str, object]) -> None:
        job_engine = create_persistence_engine(sqlite_url(db_path))
        try:
            with unit_of_work(create_session_factory(job_engine)) as job_session:
                job_pep = PolicyEnforcementPoint(pdp, "execution.durable.job_store")
                job_store = JobStore(job_session, job_pep)
                job_store.checkpoint(job_id, detail)
                job_store.transition(job_id, state)
        finally:
            job_engine.dispose()

    if already_accepted is not None:
        _finish_job(JOB_FAILED, {
            "phase": "refused", "reason": "goal already has an ACCEPTED candidate",
            "accepted_candidate_id": already_accepted,
        })
        print(json.dumps({
            "outcome": "GOAL_ALREADY_ACCEPTED", "accepted_candidate_id": already_accepted,
        }))
        return 1

    blueprint = derive_blueprint(goal_text, AuthorityMap.load(ROOT))
    vocabulary = StageVocabulary.load(ROOT)

    provenance = GenerationProvenance(
        goal_hash=goal_hash, source_commit="", runtime="ollama",
        endpoint="http://127.0.0.1:11434", model="qwen2.5-coder:14b",
        model_parameters={
            "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
            "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
            "per_stage_max_attempts": 4,
        },
        pipeline_version="phase-30-staged-generation/1.0.0",
    )
    ledger.allocate(candidate_id, provenance=provenance)

    empty_snapshot = ROOT / "var" / "factory" / "empty-stable-snapshot"
    workspace = WorkspaceAuthority(candidates_root).allocate(
        workspace_id=candidate_id, task_id=candidate_id,
        agent_id="factory-worker", stable_snapshot=empty_snapshot,
    )
    ledger.record_state(candidate_id, GENERATING, workspace.root)
    _checkpoint({"phase": "generating", "candidate_id": candidate_id})

    def model_factory(_stage_name: str):  # noqa: ANN202
        adapter = OllamaAdapter(json_mode=True, max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS)
        # F-0078: every real attempt's own diagnostic facts are frozen as
        # real, content-addressed evidence -- diagnostic provenance only,
        # never changing what this run reports or how it is classified.
        observed = _ObservedModel(adapter, candidate_id, provider_model)
        return observed, "qwen2.5-coder:14b"

    try:
        result = generate_staged_model_product(
            blueprint, model_factory, workspace, vocabulary=vocabulary,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS, per_stage_max_attempts=4,
        )
    except ModelGenerationError as error:
        elapsed = round(time.monotonic() - started, 1)
        payload = json.dumps({
            "candidate_id": candidate_id, "outcome": "STAGE_FAILED",
            "error": str(error), "elapsed_seconds": elapsed,
            "last_raw_output": getattr(error, "last_raw_output", ""),
        }, sort_keys=True).encode()
        ref = _freeze(
            payload, candidate_id, f"sha256:{__import__('hashlib').sha256(payload).hexdigest()}",
            ("real staged-generation stage failure (Command Center worker)",), provider_model,
        )
        ledger.record_state(
            candidate_id, STAGE_FAILED, workspace.root, detail={"error": str(error)},
        )
        _finish_job(JOB_FAILED, {
            "phase": "stage_failed", "candidate_id": candidate_id, "error": str(error),
            "evidence_ref": ref, "elapsed_seconds": elapsed,
        })
        print(json.dumps({
            "outcome": "STAGE_FAILED", "candidate_id": candidate_id, "error": str(error),
            "evidence_ref": ref, "elapsed_seconds": elapsed,
        }, ensure_ascii=False))
        return 2
    except (KeyboardInterrupt, Exception):
        elapsed = round(time.monotonic() - started, 1)
        ledger.record_state(
            candidate_id, INTERRUPTED, workspace.root,
            detail={"note": "generation ended without reaching a classified outcome"},
        )
        _finish_job(JOB_FAILED, {
            "phase": "interrupted", "candidate_id": candidate_id, "elapsed_seconds": elapsed,
        })
        raise

    assembled = {path: (workspace.root / path).read_text(encoding="utf-8") for path in result.files}
    try:
        ModelProductEnvelope(files=tuple(GeneratedFile(path=p, content=c) for p, c in assembled.items()))
        inspect_product_files(assembled).require_pass()
    except (ValueError, ProductSemanticPreflightError) as error:
        elapsed = round(time.monotonic() - started, 1)
        payload = json.dumps({
            "candidate_id": candidate_id, "outcome": "FINAL_GATE_FAILED",
            "error": str(error), "files": sorted(assembled), "elapsed_seconds": elapsed,
        }, sort_keys=True).encode()
        ref = _freeze(
            payload, candidate_id, f"sha256:{__import__('hashlib').sha256(payload).hexdigest()}",
            ("real assembled candidate failed the final whole-product gate (Command Center worker)",),
            provider_model,
        )
        ledger.record_state(
            candidate_id, FINAL_GATE_FAILED, workspace.root, detail={"error": str(error)},
        )
        _finish_job(JOB_FAILED, {
            "phase": "final_gate_failed", "candidate_id": candidate_id, "error": str(error),
            "evidence_ref": ref, "elapsed_seconds": elapsed,
        })
        print(json.dumps({
            "outcome": "FINAL_GATE_FAILED", "candidate_id": candidate_id, "error": str(error),
            "evidence_ref": ref, "elapsed_seconds": elapsed,
        }, ensure_ascii=False))
        return 3

    elapsed = round(time.monotonic() - started, 1)
    payload = json.dumps({
        "candidate_id": candidate_id, "outcome": "STAGED_GENERATION_PASS",
        "files": sorted(assembled), "attempts_used": result.attempts_used,
        "elapsed_seconds": elapsed,
    }, sort_keys=True).encode()
    ref = _freeze(
        payload, candidate_id, f"sha256:{__import__('hashlib').sha256(payload).hexdigest()}",
        ("real staged generation + final whole-product gate, both PASS (Command Center worker)",),
        provider_model,
    )
    ledger.record_state(candidate_id, STAGED_GENERATION_PASS, workspace.root)

    # Production Factory -> canonical acceptance bridge: the real candidate
    # this job just produced is handed, automatically and in-process, to
    # the SAME generic acceptance engine the manual `run_golden_
    # acceptance.py` CLI already uses. A normal Command Center user never
    # runs a second command for this. Failure here is real, evidenced
    # engineering fact -- reported on the job, never allowed to change
    # JOB_SUCCEEDED below (generation already genuinely succeeded) or to
    # crash this worker.
    try:
        acceptance = _run_production_acceptance(candidate_id, workspace.root)
    except Exception as error:  # noqa: BLE001 -- reported, never allowed to mask a real STAGED_GENERATION_PASS
        acceptance = {"outcome": "ACCEPTANCE_BRIDGE_ERROR", "error": str(error)}

    _finish_job(JOB_SUCCEEDED, {
        "phase": "staged_generation_pass", "candidate_id": candidate_id,
        "evidence_ref": ref, "files": sorted(assembled), "elapsed_seconds": elapsed,
        "acceptance": acceptance,
    })
    print(json.dumps({
        "outcome": "STAGED_GENERATION_PASS", "candidate_id": candidate_id,
        "evidence_ref": ref, "files": sorted(assembled), "elapsed_seconds": elapsed,
        "acceptance": acceptance,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
