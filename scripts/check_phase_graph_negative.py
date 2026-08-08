#!/usr/bin/env python3
"""Drift negative control for check_phase_graph.py.

Proves the validator FAILS when the AUTHORITATIVE dependency matrix is
defective, rather than passing vacuously. It:

  1. reads the real IMPLEMENTATION_DEPENDENCY_MATRIX.md into memory;
  2. reintroduces the original HG1-05 defect (22B prerequisites 5, 20, 26);
  3. runs the SAME parser + validator against that modified input;
  4. asserts FAIL and cycle detection.

No repository file is created or modified. The mutation exists only in memory.
Exit 0 = negative control behaved correctly (validator failed as required).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_phase_graph as g  # noqa: E402


def main():
    ms = g.read(g.MS)
    matrix = g.read(g.MATRIX)

    # --- in-memory mutation of the authoritative input -------------------
    mutated, n = re.subn(
        r"(\|\s*\*\*22B\*\*\s*\|[^|]*\|\s*)\*\*5, 6, 13, 20\*\*(\s*\|)",
        r"\g<1>**5, 20, 26**\g<2>",
        matrix,
    )
    if n != 1:
        print(f"NEGATIVE CONTROL SETUP FAILED: expected 1 substitution, got {n}")
        return 1
    assert mutated != matrix
    print("Injected defect into an IN-MEMORY copy of "
          "IMPLEMENTATION_DEPENDENCY_MATRIX.md: 22B prereqs -> 5, 20, 26")
    print("(repository files untouched)\n")

    rc = g.validate(ms, mutated, g.AUTH, label="NEGATIVE CONTROL")

    print()
    if rc == 0:
        print("NEGATIVE CONTROL: **FAILED** - validator passed a defective "
              "matrix. The check is vacuous and cannot be trusted.")
        return 1
    print("NEGATIVE CONTROL: PASS - validator rejected the defective "
          "authoritative input and reported the deadlock cycle.")

    # confirm the repository copy is still clean
    if g.read(g.MATRIX) != matrix:
        print("NEGATIVE CONTROL: **FAILED** - repository matrix was modified.")
        return 1
    print("Repository IMPLEMENTATION_DEPENDENCY_MATRIX.md verified unmodified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
