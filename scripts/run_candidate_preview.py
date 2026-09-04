#!/usr/bin/env python3
"""CLI entrypoint for `engineering.candidate.preview.run_preview` — a fixed
wall-clock preview with no durable job, for direct operator use or a real
live-proof run. See that module for what "preview" actually means and why
it never touches acceptance's ledger state or duplicates
`run_golden_acceptance.py`'s process-lifecycle primitives.

For the Command Center's own "Uygulamayı Aç" flow, see
`scripts/run_candidate_preview_worker.py` instead — the same `run_preview`
call, driven by a real durable job rather than a fixed timer.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))

from arkali.engineering.candidate.preview import PreviewRefused, run_preview  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument(
        "--max-seconds", type=float, default=180.0,
        help="hard ceiling; the preview always stops itself by then even if never interrupted",
    )
    args = parser.parse_args()

    try:
        with run_preview(args.candidate_id) as info:
            print(json.dumps({**info, "status": "READY"}), flush=True)
            deadline = time.monotonic() + args.max_seconds
            try:
                while time.monotonic() < deadline:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
            print(json.dumps({"status": "STOPPING"}), flush=True)
    except PreviewRefused as error:
        print(json.dumps({"status": "REFUSED", "reason": str(error)}), flush=True)
        return 1
    print(json.dumps({"status": "STOPPED"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
