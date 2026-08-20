#!/usr/bin/env python3
"""Run one real local-model product generation into an isolated candidate.

This is a shipping composition root, not a test harness: it loads canonical
repository truth, uses the real loopback Ollama adapter, allocates through the
existing C-25 workspace authority and delegates generation to
``engineering.factory``. It grants no acceptance or release verdict.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from arkali.control.architecture.authority_map import AuthorityMap  # noqa: E402
from arkali.control.specification.blueprint_engine import derive_blueprint  # noqa: E402
from arkali.engineering.candidate.workspace import WorkspaceAuthority  # noqa: E402
from arkali.engineering.factory.model_product_generation import (  # noqa: E402
    generate_model_product_bounded,
)
from arkali.engineering.localai.ollama_adapter import OllamaAdapter  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--model", default="qwen2.5-coder:14b")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--attempts", type=int, default=2)
    parser.add_argument("--workspace-root", default=str(ROOT / "var" / "factory"))
    args = parser.parse_args(argv[1:])

    workspace_root = pathlib.Path(args.workspace_root).resolve()
    seed = workspace_root / "empty-stable-snapshot"
    seed.mkdir(parents=True, exist_ok=True)
    workspace = WorkspaceAuthority(workspace_root / "candidates").allocate(
        workspace_id=args.request_id,
        task_id=args.request_id,
        agent_id="local-model",
        stable_snapshot=seed,
    )
    blueprint = derive_blueprint(args.goal, AuthorityMap.load(ROOT))
    result = generate_model_product_bounded(
        blueprint,
        OllamaAdapter(json_mode=True),
        args.model,
        workspace,
        timeout_seconds=args.timeout,
        max_attempts=args.attempts,
    )
    print(
        json.dumps(
            {
                **result.model_dump(mode="json"),
                "workspace": str(workspace.root),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
