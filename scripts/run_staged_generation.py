#!/usr/bin/env python3
"""One real, bounded, local-model STAGED Golden Product generation attempt.

Package D of the staged-generation plan: proves generate_staged_model_product
(backend/arkali/engineering/factory/component_generation.py) against a real
Ollama model, then runs the same final promotion gate the one-shot path uses
(ModelProductEnvelope completeness + inspect_product_files), and freezes real
evidence of the outcome either way - success or the first blocking failure.
Never fabricates a PASS.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from arkali.control.architecture.authority_map import AuthorityMap  # noqa: E402
from arkali.control.policy.pdp import PolicyDecisionPoint  # noqa: E402
from arkali.control.policy.pep import PolicyEnforcementPoint  # noqa: E402
from arkali.control.specification.blueprint_engine import derive_blueprint  # noqa: E402
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
from arkali.kernel.persistence.engine import (  # noqa: E402
    create_persistence_engine,
    sqlite_url,
)
from arkali.kernel.persistence.migrations import ALEMBIC_INI  # noqa: E402
from arkali.kernel.persistence.session import (  # noqa: E402
    create_session_factory,
    unit_of_work,
)

#: Default goal (Golden Product family 1, Task/Work Management) -- kept
#: unchanged so a bare `--candidate-id` invocation reproduces exactly what
#: it always has. `--goal-file` overrides it for any other Golden Product
#: family without touching this default.
GOAL = """1. The system must persist task records using SQLite with at least 1 table.
2. The backend must expose at least 4 REST API endpoints for task management.
3. The frontend must display a task list within 1 screen.
4. The backend must respond within 500 ms for a single task request under normal load."""


def _freeze(payload: bytes, task_id: str, context_hash: str, evidence: tuple[str, ...], model: str) -> str:
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
                    provider_model=f"ollama/{model}",
                    task_id=task_id,
                    specification_version="phase-30-staged-generation/1.0.0",
                    context_hash=context_hash,
                    evidence=evidence,
                ),
            )
    finally:
        engine.dispose()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--model", default="qwen2.5-coder:14b")
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--per-stage-max-attempts", type=int, default=4)
    parser.add_argument(
        "--goal-file", type=pathlib.Path, default=None,
        help="path to a real goal-text file (one requirement per numbered line); "
             "defaults to this script's own built-in Task/Work Management GOAL",
    )
    args = parser.parse_args(argv[1:])

    goal_text = args.goal_file.read_text(encoding="utf-8") if args.goal_file else GOAL
    blueprint = derive_blueprint(goal_text, AuthorityMap.load(ROOT))
    vocabulary = StageVocabulary.load(ROOT)

    candidates_root = ROOT / "var" / "factory" / "candidates"
    empty_snapshot = ROOT / "var" / "factory" / "empty-stable-snapshot"
    workspace = WorkspaceAuthority(candidates_root).allocate(
        workspace_id=args.candidate_id, task_id=args.candidate_id,
        agent_id="staged-generation", stable_snapshot=empty_snapshot,
    )

    def model_factory(_stage_name: str) -> tuple[OllamaAdapter, str]:
        adapter = OllamaAdapter(json_mode=True, max_output_tokens=args.max_output_tokens)
        return adapter, args.model

    started = time.monotonic()
    try:
        result = generate_staged_model_product(
            blueprint, model_factory, workspace, vocabulary=vocabulary,
            timeout_seconds=args.timeout_seconds,
            per_stage_max_attempts=args.per_stage_max_attempts,
        )
    except ModelGenerationError as error:
        payload = json.dumps({
            "candidate_id": args.candidate_id, "outcome": "STAGE_FAILED",
            "error": str(error), "elapsed_seconds": round(time.monotonic() - started, 1),
            "last_raw_output": getattr(error, "last_raw_output", ""),
        }, sort_keys=True).encode()
        ref = _freeze(
            payload, args.candidate_id, f"sha256:{__import__('hashlib').sha256(payload).hexdigest()}",
            ("real staged-generation stage failure",), args.model,
        )
        print(json.dumps({
            "outcome": "STAGE_FAILED", "error": str(error), "evidence_ref": ref,
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "candidate_dir": str(workspace.root),
        }, ensure_ascii=False))
        return 2

    assembled = {path: (workspace.root / path).read_text(encoding="utf-8") for path in result.files}
    try:
        ModelProductEnvelope(files=tuple(GeneratedFile(path=p, content=c) for p, c in assembled.items()))
        inspect_product_files(assembled).require_pass()
    except (ValueError, ProductSemanticPreflightError) as error:
        payload = json.dumps({
            "candidate_id": args.candidate_id, "outcome": "FINAL_GATE_FAILED",
            "error": str(error), "files": sorted(assembled),
            "elapsed_seconds": round(time.monotonic() - started, 1),
        }, sort_keys=True).encode()
        ref = _freeze(
            payload, args.candidate_id, f"sha256:{__import__('hashlib').sha256(payload).hexdigest()}",
            ("real assembled candidate failed the final whole-product gate",), args.model,
        )
        print(json.dumps({
            "outcome": "FINAL_GATE_FAILED", "error": str(error), "evidence_ref": ref,
            "elapsed_seconds": round(time.monotonic() - started, 1),
            "candidate_dir": str(workspace.root),
        }, ensure_ascii=False))
        return 3

    payload = json.dumps({
        "candidate_id": args.candidate_id, "outcome": "STAGED_GENERATION_PASS",
        "files": sorted(assembled), "attempts_used": result.attempts_used,
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }, sort_keys=True).encode()
    ref = _freeze(
        payload, args.candidate_id, f"sha256:{__import__('hashlib').sha256(payload).hexdigest()}",
        ("real staged generation + final whole-product gate, both PASS",), args.model,
    )
    print(json.dumps({
        "outcome": "STAGED_GENERATION_PASS", "evidence_ref": ref, "files": sorted(assembled),
        "attempts_used": result.attempts_used,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "candidate_dir": str(workspace.root),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
