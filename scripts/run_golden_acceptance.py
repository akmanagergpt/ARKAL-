#!/usr/bin/env python3
"""The manual/CLI entry point onto `factory_acceptance`'s one real, generic
acceptance engine -- for either the manual verification track
(`golden-work-*`) or a real production Factory candidate (`factory-
<job_id>`, `scripts/run_factory_worker.py`, which calls the SAME engine
directly, in-process, once it reaches its own real `STAGED_GENERATION_PASS`).
Both candidate shapes live under the same `CANDIDATES` root and the same
`CandidateLedger`; this script's only own opinion is `_candidate()`'s
identity-shape check below -- everything else is `factory_acceptance`'s.

This runner owns every process it starts, disables Flask's debug reloader,
refuses occupied ports, and records one machine-readable result.  It never
edits the candidate and never turns a failed obligation into a PASS.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from factory_acceptance import (  # noqa: E402
    CANDIDATES,
    _accept,
    _candidate_contract_files,
    _resolve_scenario,
    _run,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: ARK-REQ-0074 ("Golden domain logic must not enter ARKALI core"): the
#: runner itself names no resource, field, or route -- every real domain
#: fact (route, payload, relationship, navigation, editable field) comes
#: from a real `_AcceptanceScenario`, by default COMPILED from the
#: candidate's own real generated contracts (`_compile_acceptance_plan`),
#: never hand-authored per candidate. `golden/scenarios/student_fee_
#: management.json` remains real data too -- now only a regression
#: fixture/oracle a real `--scenario` override can point at, reconciled
#: against the candidate's own contracts before it is trusted.
DEFAULT_SCENARIO = ROOT / "golden" / "scenarios" / "student_fee_management.json"

#: The two real, canonical candidate-identity shapes `CANDIDATES` already
#: contains: `golden-work-*` (the manual verification track, `scripts/
#: run_golden_repair.py`) and `factory-<job_id>` (real production goals,
#: `scripts/run_factory_worker.py`'s own `candidate_id = f"factory-{job_id}"`).
#: Both are written to, and tracked by, the exact same `CandidateLedger` at
#: the exact same `CANDIDATES` root -- this tuple is the runner's only
#: identity-shape opinion, never a second candidate root or lifecycle.
_CANDIDATE_ID_PREFIXES = ("golden-work-", "factory-")


def _candidate(candidate_id: str) -> pathlib.Path:
    if (
        not candidate_id.startswith(_CANDIDATE_ID_PREFIXES)
        or not candidate_id.replace("-", "").isalnum()
    ):
        raise ValueError(
            "candidate id must be a golden-work-* or factory-* identifier"
        )
    path = (CANDIDATES / candidate_id).resolve()
    if path.parent != CANDIDATES.resolve() or not path.is_dir():
        raise ValueError(f"candidate does not exist: {candidate_id}")
    return path


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--skip-browser", action="store_true", help="diagnostic only; can never accept")
    parser.add_argument(
        "--scenario", type=pathlib.Path, default=None,
        help="explicit AcceptanceScenario JSON override (ARK-REQ-0074: this runner names no "
             "resource, field, or route of its own); by default the runner instead COMPILES a "
             "real scenario from the candidate's own generated contracts (product/ux_spec.json, "
             "backend/*.json). An override is only ever used after it RECONCILES against those "
             f"same real contracts (e.g. the Student/Fee Golden's own regression fixture, "
             f"{DEFAULT_SCENARIO.relative_to(ROOT)})",
    )
    args = parser.parse_args(argv[1:])

    candidate_dir = _candidate(args.candidate_id)
    contract_files = _candidate_contract_files(candidate_dir)
    resolved = _resolve_scenario(args.candidate_id, contract_files, args.scenario)
    if isinstance(resolved, dict):
        print(json.dumps(resolved, ensure_ascii=False))
        return 2
    scenario, scenario_path = resolved

    result = _accept(
        args.candidate_id, candidate_dir, scenario, scenario_path, skip_browser=args.skip_browser,
    )
    if args.skip_browser and result["outcome"] == "GOLDEN_ACCEPTANCE_PASS":
        result["outcome"] = "GOLDEN_ACCEPTANCE_INCOMPLETE"
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["outcome"] == "GOLDEN_ACCEPTANCE_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
