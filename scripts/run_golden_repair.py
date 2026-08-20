#!/usr/bin/env python3
"""One budgeted real-model repair attempt over an immutable generated candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.engineering.candidate.workspace import WorkspaceAuthority  # noqa: E402
from arkali.engineering.factory.model_product_generation import (
    write_model_product_output,  # noqa: E402
)
from arkali.engineering.localai.ollama_adapter import OllamaAdapter  # noqa: E402
from arkali.engineering.repair.contracts import (  # noqa: E402
    RepairBudget,
    RepairBudgetLedger,
    RepairFingerprint,
)
from arkali.engineering.repair.product_root_cause import (
    analyze_python_product_failure,  # noqa: E402
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


def _hashes(root: pathlib.Path) -> list[dict[str, object]]:
    files = [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
        and p.relative_to(root).parts[0] != "snapshot"
    ]
    return [
        {
            "path": p.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "bytes": p.stat().st_size,
        }
        for p in files
    ]


def _artifact(
    payload: bytes,
    task_id: str,
    context_hash: str,
    *,
    model: str,
    parents: tuple[str, ...] = (),
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
                    provider_model=f"ollama/{model}",
                    task_id=task_id,
                    specification_version="C-26/1.0.0",
                    context_hash=context_hash,
                    evidence=("real failing pytest collection",),
                    parents=parents,
                ),
            )
    finally:
        engine.dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--model", default="qwen2.5-coder:7b")
    parser.add_argument("--output-tokens", type=int, default=8192)
    parser.add_argument(
        "--prior-failure",
        help="Exact rejected output from a prior bounded attempt.",
    )
    parser.add_argument(
        "--record-escalated",
        action="store_true",
        help="Record a previously written final candidate as terminal ESCALATED.",
    )
    parser.add_argument("--terminal-failure")
    args = parser.parse_args(argv[1:])
    source = pathlib.Path(args.source).resolve()
    backend = (source / "backend/src/main.py").read_text(encoding="utf-8")
    test = (source / "tests/backend/test_works.py").read_text(encoding="utf-8")
    failure = "ModuleNotFoundError: No module named 'app'"
    cause = analyze_python_product_failure(
        "backend/src/main.py", backend, test, failure
    )
    budget = RepairBudget(
        attempts=2,
        ai_calls=2,
        elapsed_seconds=1200,
        cost=Decimal(0),
        touched_files=64,
        regression_delta=0,
    )
    ledger = RepairBudgetLedger(candidate_id=source.name, budget=budget)
    frozen = {
        "candidate_id": source.name,
        "parent_revision": source.name,
        "files": _hashes(source),
        "failure_output": failure,
        "failing_test_sha256": hashlib.sha256(test.encode()).hexdigest(),
        "root_cause": cause.model_dump(mode="json"),
        "budget": ledger.model_dump(mode="json"),
        "original_provider": "ollama/qwen2.5-coder:7b",
    }
    payload = json.dumps(frozen, sort_keys=True, separators=(",", ":")).encode()
    evidence_ref = _artifact(
        payload,
        args.candidate_id,
        cause.failure_signature,
        model=args.model,
    )
    prior_attempt_ref = None
    if args.prior_failure:
        rejected = RepairFingerprint(
            failure_signature=cause.failure_signature,
            root_cause_class="+".join(cause.root_cause_classes),
            files=("backend/src/main.py", "tests/backend/test_works.py"),
            strategy="model_reconcile_contracts",
            provider_model=f"ollama/{args.model}",
            outcome=f"rejected: {args.prior_failure}",
        )
        ledger = ledger.record(
            rejected,
            ai_calls=1,
            elapsed_seconds=34,
            cost=Decimal(0),
            touched_files=0,
            regression_delta=0,
        )
        prior_payload = json.dumps(
            {
                "candidate_id": source.name,
                "fingerprint": rejected.model_dump(mode="json"),
                "ledger": ledger.model_dump(mode="json"),
                "failure_output": args.prior_failure,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        prior_attempt_ref = _artifact(
            prior_payload,
            args.candidate_id,
            rejected.fingerprint,
            model=args.model,
            parents=(evidence_ref,),
        )
    if args.record_escalated:
        repaired = source.parent / args.candidate_id
        if not repaired.is_dir() or not args.terminal_failure:
            raise ValueError(
                "terminal recording requires an existing candidate and failure"
            )
        changed = tuple(
            item["path"]
            for item in _hashes(repaired)
            if item["path"] not in {entry["path"] for entry in frozen["files"]}
            or item["sha256"]
            != next(
                (
                    entry["sha256"]
                    for entry in frozen["files"]
                    if entry["path"] == item["path"]
                ),
                None,
            )
        )
        terminal = RepairFingerprint(
            failure_signature=hashlib.sha256(
                args.terminal_failure.encode("utf-8")
            ).hexdigest(),
            root_cause_class="+".join(cause.root_cause_classes),
            files=changed or ("backend/src/main.py",),
            strategy="model_complete_contract_and_roots",
            provider_model=f"ollama/{args.model}",
            outcome=f"rejected_and_escalated: {args.terminal_failure}",
        )
        ledger = ledger.record(
            terminal,
            ai_calls=1,
            elapsed_seconds=32,
            cost=Decimal(0),
            touched_files=len(changed),
            regression_delta=0,
        )
        terminal_payload = json.dumps(
            {
                "candidate_id": args.candidate_id,
                "parent_revision": source.name,
                "files": _hashes(repaired),
                "changed_files": changed,
                "failure_output": args.terminal_failure,
                "fingerprint": terminal.model_dump(mode="json"),
                "ledger": ledger.model_dump(mode="json"),
                "terminal_outcome": "ESCALATED",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        terminal_ref = _artifact(
            terminal_payload,
            args.candidate_id,
            terminal.fingerprint,
            model=args.model,
            parents=tuple(
                ref for ref in (evidence_ref, prior_attempt_ref) if ref is not None
            ),
        )
        print(
            json.dumps(
                {
                    "candidate": str(repaired),
                    "terminal_outcome": "ESCALATED",
                    "terminal_ref": terminal_ref,
                    "attempts": ledger.consumption.attempts,
                    "budget": ledger.budget.attempts,
                    "changed_files": changed,
                },
                ensure_ascii=False,
            )
        )
        return 2
    workspace = WorkspaceAuthority(source.parent).allocate(
        workspace_id=args.candidate_id,
        task_id=args.candidate_id,
        agent_id="golden-repair",
        stable_snapshot=source,
    )
    prompt = json.dumps(
        {
            "role": "bounded software repair worker",
            "instruction": "Return one JSON object only containing a complete repaired multi-file product. Do not weaken or delete tests. Change only files justified by the evidence.",
            "output_schema": {
                "files": [
                    {"path": "relative/posix/path", "content": "complete file text"}
                ]
            },
            "required_roots": ["backend", "frontend", "tests", "config"],
            "root_cause_evidence": cause.model_dump(mode="json"),
            "failure": failure,
            "prior_attempt_failure": args.prior_failure,
            "convergence_instruction": "This is the final permitted attempt. Return every required root, including config/README.md, and reconcile module imports, backend contracts, and persistent SQLite bootstrap without weakening tests.",
            "original_files": {
                item["path"]: (source / str(item["path"])).read_text(encoding="utf-8")
                for item in frozen["files"]
            },
        },
        ensure_ascii=False,
    )
    started = time.monotonic()
    outcome = OllamaAdapter(json_mode=True, max_output_tokens=args.output_tokens).infer(
        args.model, prompt, timeout_seconds=600
    )
    if outcome.state.value != "PASS":
        raise RuntimeError(
            f"model repair failed: {outcome.state.value}: {outcome.detail}"
        )
    files = write_model_product_output(
        outcome.output,
        workspace,
        baseline={
            item["path"]: (source / str(item["path"])).read_text(encoding="utf-8")
            for item in frozen["files"]
        },
    )
    print(
        json.dumps(
            {
                "candidate": str(workspace.root),
                "parent": str(source),
                "evidence_ref": evidence_ref,
                "prior_attempt_ref": prior_attempt_ref,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "model": args.model,
                "files": files,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
