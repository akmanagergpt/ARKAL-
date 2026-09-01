#!/usr/bin/env python3
"""One isolated, budgeted Golden Repair run against a real ACCEPTED Golden
Product parent (ARK-REQ-0089/0092/0093/0094/0095/0187/0188/0333/0334).

Loads the real, versioned canonical corpus instance (golden/repair/golden_
repair_corpus.json), injects it into an isolated repair child derived from
`--source-candidate-id` (never the parent itself -- `run_isolated_golden_
repair` refuses anything but a real ACCEPTED, integrity-intact parent before
any workspace is even allocated), runs the bounded per-defect convergence
loop against a real local model, and freezes real ArtifactStore evidence of
the outcome either way. Names no candidate, resource, field, or route of its
own anywhere in this file -- every domain fact comes from the parent
candidate's own real generated files.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.engineering.candidate.errors import CandidateIntegrityError  # noqa: E402
from arkali.engineering.candidate.ledger import (  # noqa: E402
    ACCEPTED,
    CandidateLedger,
    FINAL_GATE_FAILED,
    GenerationProvenance,
    GOLDEN_REPAIR_PASS,
    GOLDEN_REPAIR_RUNNING,
    file_manifest,
    hash_text,
)
from arkali.engineering.candidate.workspace import WorkspaceAuthority  # noqa: E402
from arkali.engineering.factory.product_preflight import inspect_product_files  # noqa: E402
from arkali.engineering.localai.ollama_adapter import OllamaAdapter  # noqa: E402
from arkali.engineering.repair.contracts import RepairBudget, RepairFingerprint  # noqa: E402
from arkali.engineering.repair.golden_corpus import (  # noqa: E402
    RepairCorpusEntry,
    corpus_hash,
    changed_protected_paths,
    load_corpus_instance,
)
from arkali.engineering.repair.golden_corpus_injectors import apply_corpus  # noqa: E402
from arkali.engineering.repair.golden_repair_runner import (  # noqa: E402
    AttemptRepair,
    RepairRunResult,
    run_corpus_repair,
)
from arkali.engineering.repair.product_root_cause import (  # noqa: E402
    analyze_python_product_failure,
)
from arkali.evidence.artifact.blob_store import ArtifactBlobStore  # noqa: E402
from arkali.evidence.artifact.store import ArtifactStore, ProvenanceInput  # noqa: E402
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
    sqlite_url,
)
from arkali.kernel.persistence.migrations import ALEMBIC_INI  # noqa: E402
from arkali.kernel.persistence.session import (  # noqa: E402
    create_session_factory,
    unit_of_work,
)

CANDIDATES = ROOT / "var" / "factory" / "candidates"
DEFAULT_CORPUS = ROOT / "golden" / "repair" / "golden_repair_corpus.json"

#: Referenced by name from each corpus entry's own `budget_profile` field
#: (corpus definition §1: "reference to declared budget set for the run") --
#: one shared RepairBudget per run, matching `run_corpus_repair`'s own single
#: `budget: RepairBudget` parameter; never a per-entry numeric budget, since
#: the canonical schema declares budget_profile as a run-level reference,
#: not a per-defect ceiling.
BUDGET_PROFILES: dict[str, RepairBudget] = {
    "golden-repair-standard-v1": RepairBudget(
        attempts=6, ai_calls=6, elapsed_seconds=3600,
        cost=Decimal(0), touched_files=64, regression_delta=0,
    ),
}


def _source_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _freeze(
    payload: bytes, task_id: str, context_hash: str,
    evidence: tuple[str, ...], provider_model: str, *, parents: tuple[str, ...] = (),
) -> str:
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
                    producer_agent="engineering.repair",
                    provider_model=provider_model,
                    task_id=task_id,
                    specification_version="C-26/1.0.0",
                    context_hash=context_hash,
                    evidence=evidence,
                    parents=parents,
                ),
            )
    finally:
        engine.dispose()


def _real_test_failure_text(files: dict[str, str]) -> str:
    """Real, captured subprocess output -- never a hardcoded string. Runs
    the candidate's own real `tests/` suite against ARKALI's own interpreter
    (no fresh venv: this is a repair-strategy SIGNAL for the model, not the
    regression-validation verdict itself -- that stays run_golden_
    acceptance.py's job alone, per approved scope item H) and returns
    whatever it genuinely printed, pass or fail."""
    with tempfile.TemporaryDirectory(prefix="golden-repair-probe-") as raw:
        scratch = pathlib.Path(raw)
        for relative, text in files.items():
            path = scratch / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", "tests", "-q"],
                cwd=scratch, capture_output=True, text=True, timeout=120,
            )
            return (result.stdout + result.stderr).strip()[-4000:]
        except (OSError, subprocess.TimeoutExpired) as error:
            return f"probe run could not complete: {error}"


def _make_attempt_repair(model: str, output_tokens: int, timeout_seconds: float):
    """A real, dependency-injected `AttemptRepair`: one bounded local-model
    call per attempt, grounded in this specific entry's own real detector
    output and a real captured test-probe failure -- no candidate-specific
    text, no fabricated failure string."""
    adapter = OllamaAdapter(json_mode=True, max_output_tokens=output_tokens)

    def attempt_repair(
        entry: RepairCorpusEntry, current: dict[str, str],
    ) -> tuple[dict[str, str] | None, RepairFingerprint]:
        backend_path = "backend/app.py"
        backend_source = current.get(backend_path, "")
        test_path = next((p for p in sorted(current) if p.startswith("tests/")), "tests/")
        test_source = current.get(test_path, "")
        probe_failure = _real_test_failure_text(current)
        cause = analyze_python_product_failure(
            backend_path, backend_source, test_source, probe_failure or entry.title,
        )
        prompt = json.dumps({
            "role": "bounded golden-repair worker",
            "instruction": (
                "Return one JSON object only: {\"files\": {\"relative/posix/path\": "
                "\"complete file text\"}}. Fix ONLY the defect described below. Do "
                "not weaken, delete, or rewrite anything under tests/ or config/. "
                "Change only the files genuinely required."
            ),
            "defect_class": entry.defect_class,
            "defect_title": entry.title,
            "defect_rationale": entry.rationale,
            "injection_target": entry.injection_target,
            "root_cause_evidence": cause.model_dump(mode="json"),
            "real_test_probe_output": probe_failure,
            "current_files": current,
        }, ensure_ascii=False)
        outcome = adapter.infer(model, prompt, timeout_seconds=timeout_seconds)
        if outcome.state.value != "PASS":
            fingerprint = RepairFingerprint(
                failure_signature=cause.failure_signature,
                root_cause_class="+".join(cause.root_cause_classes),
                files=(backend_path,),
                strategy=f"model_repair_{entry.defect_class}",
                provider_model=f"ollama/{model}",
                outcome=f"rejected: {outcome.state.value}: {outcome.detail}",
            )
            return None, fingerprint
        try:
            proposed = json.loads(outcome.output)["files"]
        except (ValueError, KeyError, TypeError) as error:
            fingerprint = RepairFingerprint(
                failure_signature=cause.failure_signature,
                root_cause_class="+".join(cause.root_cause_classes),
                files=(backend_path,),
                strategy=f"model_repair_{entry.defect_class}",
                provider_model=f"ollama/{model}",
                outcome=f"rejected: malformed response: {error}",
            )
            return None, fingerprint
        changed = {**current, **proposed}
        fingerprint = RepairFingerprint(
            failure_signature=cause.failure_signature,
            root_cause_class="+".join(cause.root_cause_classes),
            files=tuple(sorted(proposed)) or (backend_path,),
            strategy=f"model_repair_{entry.defect_class}",
            provider_model=f"ollama/{model}",
            outcome="candidate-fix-proposed",
        )
        return changed, fingerprint

    return attempt_repair


def _read_files(root: pathlib.Path) -> dict[str, str]:
    """Every real file under `root` as `{relative_posix_path: text}` --
    mirrors `ledger.file_manifest`'s own walk (sorted, no `snapshot/`
    special-casing needed here since callers pass `workspace.snapshot`
    itself, never a workspace root that still contains one).

    Reads with `newline=""` deliberately: the default universal-newline
    mode silently rewrites a file's own real `\\r\\n` to `\\n`, which would
    make `workspace.write`'s later raw-bytes write disagree with the
    parent's own recorded manifest for a file the corpus never targeted
    at all -- a false "changed" verdict `changed_protected_paths` (or a
    real reviewer) would have no honest explanation for."""
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_text(encoding="utf-8", newline="")
    return files


@dataclass(frozen=True)
class GoldenRepairRequest:
    """Bundles one repair run's own identity/corpus/budget/strategy
    arguments -- kept as one object (rather than `run_isolated_golden_
    repair` taking each as its own parameter) to stay within AUTHORITY_MAP.
    yaml's `max_parameters_per_public_function` budget."""

    parent_id: str
    child_id: str
    entries: tuple[RepairCorpusEntry, ...]
    budget: RepairBudget
    attempt_repair: AttemptRepair
    provenance: GenerationProvenance


@dataclass(frozen=True)
class GoldenRepairOutcome:
    """Everything the CLI's own evidence recording below needs to describe
    the real outcome of one isolated repair run -- never a second authority
    for facts `CandidateLedger`/`RepairBudgetLedger` already own."""

    child_id: str
    workspace_root: pathlib.Path
    state: str
    repair_result: RepairRunResult
    protected_path_violations: tuple[str, ...]
    gate_passed: bool
    gate_findings: tuple[str, ...]


def run_isolated_golden_repair(
    ledger: CandidateLedger,
    candidates_root: pathlib.Path,
    request: GoldenRepairRequest,
    *,
    inspect_gate,
) -> GoldenRepairOutcome:
    """The real Golden Repair lifecycle, end to end, against a real
    `CandidateLedger` and `WorkspaceAuthority` -- no second candidate,
    workspace, or acceptance authority (approved scope A/B/F/G). Lives in
    this script, not a gated library module, for the architectural reason
    `golden_repair_runner.py`'s own module docstring documents.

    A. PARENT ELIGIBILITY/INTEGRITY, checked before anything is allocated
    or written: `request.parent_id`'s latest recorded state must be exactly
    `ACCEPTED` (refused via the same `CandidateIntegrityError` `begin_
    acceptance` already raises for an ineligible state -- no new error
    class), and its live content must still match the manifest recorded
    at that ACCEPTED state (`ledger.verify_integrity`). The parent is
    NEVER written to by this function -- no `record_state` call below
    ever names `request.parent_id`.

    B. ISOLATED REPAIR CHILD: `WorkspaceAuthority.allocate` with the
    parent's own real root as `stable_snapshot` -- the identical isolation
    mechanism `run_staged_generation.py` already uses, copying the parent
    into `workspace.snapshot` (read-only reference) while the repair
    child's own real product is written to `workspace.root` -- a
    completely separate identity and tree from the parent's own.

    F. AUTOMATIC ESCALATED: `run_corpus_repair` (already real, bounded,
    dependency-injected) is the only source of an ESCALATED-bound entry;
    nothing here ever accepts an operator-supplied escalation flag.

    G. NO-TEST-WEAKENING: the child's own final manifest is compared
    against the parent's ACCEPTED manifest under `changed_protected_paths`
    before `GOLDEN_REPAIR_PASS` may ever be recorded -- any protected-path
    change routes to `FINAL_GATE_FAILED` instead, the same terminal state
    a real whole-product gate failure already uses.
    """
    parent_id, child_id = request.parent_id, request.child_id
    parent_root = candidates_root / parent_id
    parent_latest = ledger.latest(parent_id)
    if parent_latest is None or str(parent_latest["state"]) != ACCEPTED:
        state_name = "never allocated" if parent_latest is None else parent_latest["state"]
        raise CandidateIntegrityError(
            f"CANDIDATE_INTEGRITY_FAILED: {parent_id!r} is not repair-eligible "
            f"(latest recorded state: {state_name!r}; Golden Repair only ever "
            f"starts from a real {ACCEPTED!r} parent)"
        )
    ledger.verify_integrity(parent_id, parent_root)

    workspace = WorkspaceAuthority(candidates_root).allocate(
        workspace_id=child_id, task_id=child_id, agent_id="golden-repair",
        stable_snapshot=parent_root,
    )
    ledger.allocate(child_id, provenance=request.provenance)
    ledger.record_state(child_id, GOLDEN_REPAIR_RUNNING, workspace.root)

    parent_files = _read_files(workspace.snapshot)
    broken = apply_corpus(parent_files, request.entries)
    repair_result = run_corpus_repair(
        request.entries, broken, request.budget, request.attempt_repair, candidate_id=child_id,
    )
    for relative, text in repair_result.files.items():
        workspace.write(relative, text.encode("utf-8"))

    child_manifest = file_manifest(workspace.root)
    violations = changed_protected_paths(parent_latest["manifest"], child_manifest)

    gate_report = inspect_gate(repair_result.files)
    gate_passed = bool(getattr(gate_report, "passed", gate_report))
    gate_findings = tuple(
        f"{item.code}:{item.path}:{item.detail}" for item in getattr(gate_report, "findings", ())
    )

    if violations or not gate_passed:
        ledger.record_state(
            child_id, FINAL_GATE_FAILED, workspace.root,
            detail={"protected_path_violations": violations, "gate_findings": gate_findings},
        )
        return GoldenRepairOutcome(
            child_id=child_id, workspace_root=workspace.root, state=FINAL_GATE_FAILED,
            repair_result=repair_result, protected_path_violations=violations,
            gate_passed=gate_passed, gate_findings=gate_findings,
        )

    ledger.record_state(child_id, GOLDEN_REPAIR_PASS, workspace.root)
    return GoldenRepairOutcome(
        child_id=child_id, workspace_root=workspace.root, state=GOLDEN_REPAIR_PASS,
        repair_result=repair_result, protected_path_violations=violations,
        gate_passed=gate_passed, gate_findings=gate_findings,
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-candidate-id", required=True,
        help="a real, ACCEPTED golden-work-* candidate id; refused before any "
             "workspace mutation if it is not real, ACCEPTED, or integrity-intact",
    )
    parser.add_argument(
        "--candidate-id", required=True,
        help="the new, isolated repair child's own candidate id (never reused "
             "from --source-candidate-id, which is never itself mutated)",
    )
    parser.add_argument("--model", default="qwen2.5-coder:14b")
    parser.add_argument("--output-tokens", type=int, default=8192)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument("--corpus", type=pathlib.Path, default=DEFAULT_CORPUS)
    parser.add_argument("--budget-profile", choices=sorted(BUDGET_PROFILES), default="golden-repair-standard-v1")
    args = parser.parse_args(argv[1:])

    entries = load_corpus_instance(args.corpus)
    budget = BUDGET_PROFILES[args.budget_profile]
    provider_model = f"ollama/{args.model}"

    ledger = CandidateLedger(CANDIDATES / "_ledger")
    provenance = GenerationProvenance(
        goal_hash=hash_text(f"golden-repair:{args.source_candidate_id}:{args.candidate_id}"),
        source_commit=_source_commit(),
        runtime="ollama", endpoint="http://localhost:11434", model=args.model,
        model_parameters={"max_output_tokens": args.output_tokens, "timeout_seconds": args.timeout_seconds},
        pipeline_version="phase-30-golden-repair/1.0.0",
    )
    attempt_repair = _make_attempt_repair(args.model, args.output_tokens, args.timeout_seconds)

    request = GoldenRepairRequest(
        parent_id=args.source_candidate_id, child_id=args.candidate_id,
        entries=entries, budget=budget, attempt_repair=attempt_repair,
        provenance=provenance,
    )
    started = time.monotonic()
    outcome = run_isolated_golden_repair(
        ledger, CANDIDATES, request, inspect_gate=inspect_product_files,
    )
    elapsed = round(time.monotonic() - started, 3)

    declared_unrepairable = tuple(e.id for e in entries if not e.repairable)
    evidence_payload = {
        "candidate_id": args.candidate_id,
        "parent_revision": args.source_candidate_id,
        "corpus_hash": corpus_hash(entries),
        "declared_budget": budget.model_dump(mode="json"),
        "per_defect_outcome": {
            entry.id: (
                "resolved" if entry.id in outcome.repair_result.resolved
                else "escalated" if entry.id in outcome.repair_result.escalated
                else "not_reached"
            )
            for entry in entries
        },
        "budget_consumption": outcome.repair_result.ledger.consumption.model_dump(mode="json"),
        "regression_delta": outcome.repair_result.ledger.consumption.regression_delta,
        "declared_unrepairable_entries": declared_unrepairable,
        "escalated_entries": outcome.repair_result.escalated,
        "fingerprints": [fp.model_dump(mode="json") for fp in outcome.repair_result.ledger.fingerprints],
        "protected_path_violations": outcome.protected_path_violations,
        "gate_passed": outcome.gate_passed,
        "gate_findings": outcome.gate_findings,
        "lifecycle_state": outcome.state,
        "elapsed_seconds": elapsed,
    }
    payload = json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode()
    evidence_ref = _freeze(
        payload, args.candidate_id, corpus_hash(entries),
        ("golden repair corpus run",), provider_model,
    )

    print(json.dumps({
        "candidate_id": args.candidate_id,
        "parent_revision": args.source_candidate_id,
        "lifecycle_state": outcome.state,
        "workspace": str(outcome.workspace_root),
        "resolved": outcome.repair_result.resolved,
        "escalated": outcome.repair_result.escalated,
        "protected_path_violations": outcome.protected_path_violations,
        "gate_passed": outcome.gate_passed,
        "evidence_ref": evidence_ref,
        "elapsed_seconds": elapsed,
    }, ensure_ascii=False))
    return 0 if outcome.state == GOLDEN_REPAIR_PASS else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
