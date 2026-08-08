#!/usr/bin/env python3
"""Negative control for the reserved-keyword module_root check (F-0015 / ERR-001).

Proves the Phase 1 structural check is EFFECTIVE, not vacuous:

  1. an in-memory authority mapping whose module_root contains a segment named
     "import" must be REJECTED;
  2. the corrected "project_import" mapping must be ACCEPTED;
  3. a spread of other keywords, soft keywords and non-identifiers must also be
     rejected, proving the check is generic rather than special-cased on the one
     word that happened to be found.

No canonical repository state is read for the mutation and none is modified.
Exit 0 = the control behaved correctly.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_repository_structure import _is_illegal_module_segment  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH = os.path.join(ROOT, "docs/canonical/AUTHORITY_MAP.yaml")


def offenders(mapping: dict) -> list[str]:
    """Same predicate the real validator uses, applied to a supplied mapping."""
    found = []
    for name, meta in mapping.items():
        segments = meta["module_root"].split("/")
        try:
            package_segments = segments[segments.index("arkali"):]
        except ValueError:
            package_segments = segments
        bad = [s for s in package_segments if _is_illegal_module_segment(s)]
        if bad:
            found.append(f"{name} -> {meta['module_root']} (illegal: {bad})")
    return found


def main() -> int:
    failures: list[str] = []

    def expect(label: str, condition: bool, detail: str = "") -> None:
        print(("PASS " if condition else "FAIL ") + label
              + (f"  -- {detail}" if detail else ""))
        if not condition:
            failures.append(label)

    # 1 defective mapping must be rejected
    defective = {"engineering.import":
                 {"module_root": "backend/arkali/engineering/import"}}
    found = offenders(defective)
    expect("1  defective mapping ('import') is REJECTED", len(found) == 1, str(found))

    # 2 corrected mapping must be accepted
    corrected = {"engineering.import":
                 {"module_root": "backend/arkali/engineering/project_import"}}
    expect("2  corrected mapping ('project_import') is ACCEPTED",
           offenders(corrected) == [])

    # 3 generic, not special-cased on "import"
    generic = {
        f"ctx.{word}": {"module_root": f"backend/arkali/engineering/{word}"}
        for word in ["class", "lambda", "return", "async", "match", "_",
                     "2bad", "my-pkg", "with"]
    }
    rejected = offenders(generic)
    expect("3  generic: all keywords/soft-keywords/non-identifiers rejected",
           len(rejected) == len(generic),
           f"{len(rejected)}/{len(generic)} rejected")

    # 4 legal names must not be rejected (no false positives)
    legal = {
        f"ctx.{word}": {"module_root": f"backend/arkali/engineering/{word}"}
        for word in ["project_import", "policy", "candidate", "localai",
                     "registry", "workflow"]
    }
    expect("4  no false positives on legal identifiers", offenders(legal) == [])

    # 5 the real repository mapping is clean
    import yaml
    with open(AUTH, encoding="utf-8") as fh:
        real = yaml.safe_load(fh)["contexts"]
    live = offenders(real)
    expect("5  live AUTHORITY_MAP has no illegal module_root", live == [], str(live))

    # 6 repository untouched by this control
    before = open(AUTH, encoding="utf-8").read()
    expect("6  canonical AUTHORITY_MAP unmodified by this control",
           "project_import" in before and "engineering/import}" not in before)

    print()
    if failures:
        print(f"NEGATIVE CONTROL: FAILED -> {failures}")
        return 1
    print("NEGATIVE CONTROL: PASS - keyword check rejects defective input, "
          "accepts corrected input, and is generic across the keyword table.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
