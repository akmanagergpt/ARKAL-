#!/usr/bin/env python3
"""Execute the deterministic Phase Gate Checker against real repository state.

Usage: python scripts/run_phase_gate.py <phase_id> [next_phase]

This is the operational entry point for machine phase acceptance. It builds a
PhaseReport from recorded evidence supplied on the command line by the phase
owner and submits it to the checker. It performs no judgement of its own and
cannot override a verdict.

Exit 0 only when the verdict is PHASE_ACCEPTED_BY_MACHINE.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from arkali.acceptance.checker import PhaseGateChecker  # noqa: E402
from arkali.acceptance.gate_verdict import Verdict  # noqa: E402
from arkali.acceptance.phase_report import PhaseReport, TestExecutionRecord  # noqa: E402
from arkali.kernel.contracts.results import HonestState  # noqa: E402


def load_report(path: pathlib.Path) -> PhaseReport:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["tests_executed"] = tuple(
        TestExecutionRecord(**r) for r in raw.get("tests_executed", [])
    )
    raw["status"] = HonestState(raw["status"])
    for key in ("ark_req_ids_closed", "files_created", "files_modified",
                "public_contracts", "migrations", "evidence_created"):
        raw[key] = tuple(raw.get(key, []))
    return PhaseReport(**raw)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    report_path = ROOT / "docs" / "acceptance" / f"phase_{argv[1]}_report.json"
    if not report_path.is_file():
        print(f"no recorded phase report at {report_path}")
        return 2
    checker = PhaseGateChecker(ROOT)
    verdict = checker.evaluate(load_report(report_path),
                               argv[2] if len(argv) > 2 else None)
    print(verdict.render())
    print()
    print(f"VERDICT: {verdict.verdict.value}")
    return 0 if verdict.verdict is Verdict.PHASE_ACCEPTED_BY_MACHINE else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
