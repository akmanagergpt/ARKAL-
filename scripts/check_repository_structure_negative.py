#!/usr/bin/env python3
"""Negative controls for the structure validator.

Part 1 - reserved-keyword module_root check (F-0015 / ERR-001):

  1. an in-memory authority mapping whose module_root contains a segment named
     "import" must be REJECTED;
  2. the corrected "project_import" mapping must be ACCEPTED;
  3. a spread of other keywords, soft keywords and non-identifiers must also be
     rejected, proving the check is generic rather than special-cased on the one
     word that happened to be found.

Part 2 - runtime-construct authority check 12 (F-0027). Proves the replacement
for the retired phase-scoped rule is EFFECTIVE in both directions: it accepts a
legitimate construct inside the context canonical architecture makes responsible
for it, rejects the identical construct anywhere else, sees untracked files,
cannot be evaded by renaming or moving, and fails closed when an authority or an
owner cannot be resolved.

Every control imports the DEPLOYED predicate rather than a copy of it (F-0013).
No canonical repository state is modified. The one control that must touch the
filesystem creates a single file and deletes it in a `finally`.

Exit 0 = the controls behaved correctly.
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from check_repository_structure import (  # noqa: E402
    _is_illegal_module_segment,
    canonical_responsibilities,
    construct_authority,
    construct_violations,
    owning_context,
    shipping_root,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH = os.path.join(ROOT, "docs/canonical/AUTHORITY_MAP.yaml")
ARCH = os.path.join(ROOT, "docs/canonical/ARCHITECTURE.md")

ENGINE_SOURCE = 'engine = create_engine("sqlite+pysqlite:///arkali.db")\n'
WEB_SOURCE = 'router = APIRouter(prefix="/projects")\n'


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


def load_canonical() -> tuple[dict, dict[str, str]]:
    import yaml
    with open(AUTH, encoding="utf-8") as fh:
        contexts = yaml.safe_load(fh)["contexts"]
    with open(ARCH, encoding="utf-8") as fh:
        responsibilities = canonical_responsibilities(fh.read())
    return contexts, responsibilities


def path_in(contexts: dict, context: str, filename: str) -> str:
    """A repository-relative path inside a declared context module root."""
    return f"{contexts[context]['module_root']}/{filename}"


def run_validator() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts",
                                      "check_repository_structure.py")],
        cwd=ROOT, capture_output=True, text=True, check=False)


def keyword_controls(expect, contexts: dict) -> None:
    """Part 1: the reserved-keyword module_root check."""
    defective = {"engineering.import":
                 {"module_root": "backend/arkali/engineering/import"}}
    found = offenders(defective)
    expect("1  defective mapping ('import') is REJECTED", len(found) == 1, str(found))

    corrected = {"engineering.import":
                 {"module_root": "backend/arkali/engineering/project_import"}}
    expect("2  corrected mapping ('project_import') is ACCEPTED",
           offenders(corrected) == [])

    generic = {
        f"ctx.{word}": {"module_root": f"backend/arkali/engineering/{word}"}
        for word in ["class", "lambda", "return", "async", "match", "_",
                     "2bad", "my-pkg", "with"]
    }
    rejected = offenders(generic)
    expect("3  generic: all keywords/soft-keywords/non-identifiers rejected",
           len(rejected) == len(generic),
           f"{len(rejected)}/{len(generic)} rejected")

    legal = {
        f"ctx.{word}": {"module_root": f"backend/arkali/engineering/{word}"}
        for word in ["project_import", "policy", "candidate", "localai",
                     "registry", "workflow"]
    }
    expect("4  no false positives on legal identifiers", offenders(legal) == [])

    live = offenders(contexts)
    expect("5  live AUTHORITY_MAP has no illegal module_root", live == [], str(live))

    before = open(AUTH, encoding="utf-8").read()
    expect("6  canonical AUTHORITY_MAP unmodified by this control",
           "project_import" in before and "engineering/import}" not in before)


def authority_controls(expect, contexts: dict, resp: dict[str, str]) -> tuple[str, str]:
    """Part 2a: authority is DERIVED from the canonical documents, not listed."""
    db_owner, db_error = construct_authority("DB engine", resp, contexts)
    expect("7  'DB engine' resolves from ARCHITECTURE section 3 to exactly one "
           "context", db_owner == ["kernel.persistence"] and not db_error,
           f"{db_owner} {db_error}")

    api_owner, api_error = construct_authority("API", resp, contexts)
    expect("8  'API' resolves from ARCHITECTURE section 3 to exactly one context",
           api_owner == ["surfaces.command"] and not api_error,
           f"{api_owner} {api_error}")

    moved = dict(resp)
    moved["kernel.persistence"] = "session, migration runner"
    moved["evidence.artifact"] = "Artifact Fabric, DB engine"
    drifted, _ = construct_authority("DB engine", moved, contexts)
    expect("9  authority FOLLOWS the canonical document (no path list in the "
           "validator)", drifted == ["evidence.artifact"], str(drifted))

    absent, absent_error = construct_authority("Quantum Ledger", resp, contexts)
    expect("10 a phrase matching no canonical responsibility FAILS CLOSED",
           absent == [] and bool(absent_error), absent_error)

    undeclared, undeclared_error = construct_authority(
        "DB engine", {"ghost.context": "DB engine"}, contexts)
    expect("11 a responsibility naming a context absent from AUTHORITY_MAP "
           "FAILS CLOSED", undeclared == [] and bool(undeclared_error),
           undeclared_error)

    return db_owner[0], api_owner[0]


def placement_controls(expect, contexts: dict, resp: dict[str, str],
                       db_owner: str, api_owner: str) -> None:
    """Part 2b: the same construct is legal in one context and illegal elsewhere."""
    legal_db = {path_in(contexts, db_owner, "engine.py"): ENGINE_SOURCE}
    expect(f"12 persistence engine ACCEPTED inside {db_owner}",
           construct_violations(legal_db, contexts, resp) == [],
           str(construct_violations(legal_db, contexts, resp)))

    for wrong in ("control.registry.project", "lifecycle.recovery",
                  "surfaces.command"):
        found = construct_violations(
            {path_in(contexts, wrong, "engine.py"): ENGINE_SOURCE}, contexts, resp)
        expect(f"13 persistence engine REJECTED inside {wrong}",
               len(found) == 1 and wrong in found[0], str(found))

    legal_web = {path_in(contexts, api_owner, "routes.py"): WEB_SOURCE}
    expect(f"14 web router ACCEPTED inside {api_owner}",
           construct_violations(legal_web, contexts, resp) == [],
           str(construct_violations(legal_web, contexts, resp)))

    for wrong in ("kernel.persistence", "control.policy", "surfaces.operations"):
        found = construct_violations(
            {path_in(contexts, wrong, "routes.py"): WEB_SOURCE}, contexts, resp)
        expect(f"15 web router REJECTED inside {wrong}",
               len(found) == 1 and wrong in found[0], str(found))

    both = {path_in(contexts, db_owner, "app.py"): ENGINE_SOURCE + WEB_SOURCE}
    found = construct_violations(both, contexts, resp)
    expect("16 a file mixing both constructs is judged per construct class",
           len(found) == 1 and "web application" in found[0], str(found))


def evasion_controls(expect, contexts: dict, resp: dict[str, str],
                     db_owner: str) -> None:
    """Part 2c: renaming or moving the file does not change the verdict."""
    wrong = "control.registry.project"
    names = ["engine.py", "renamed_engine.py", "totally_unrelated_name.py",
             "sub/nested/deep.py"]
    verdicts = [len(construct_violations(
        {path_in(contexts, wrong, n): ENGINE_SOURCE}, contexts, resp)) for n in names]
    expect("17 renaming a violating file does not bypass the rule",
           verdicts == [1, 1, 1, 1], str(dict(zip(names, verdicts))))

    moved = {ctx: len(construct_violations(
        {path_in(contexts, ctx, "engine.py"): ENGINE_SOURCE}, contexts, resp))
        for ctx in ("kernel.observability", "evidence.audit", "execution.durable",
                    "engineering.factory", db_owner)}
    expect("18 moving a violating file between contexts does not bypass the rule; "
           "only the canonical authority accepts it",
           [v for k, v in moved.items() if k != db_owner] == [1, 1, 1, 1]
           and moved[db_owner] == 0, str(moved))

    prefix = shipping_root(contexts)
    orphan = {f"{prefix}engine.py": ENGINE_SOURCE}
    found = construct_violations(orphan, contexts, resp)
    expect("19 a construct inside the package but owned by NO declared context "
           "FAILS CLOSED", len(found) == 1 and "no declared context" in found[0],
           str(found))

    expect("20 ownership resolution returns None for an unowned package path",
           owning_context(f"{prefix}engine.py", contexts) is None)

    quiet = {path_in(contexts, "control.policy", "pdp.py"):
             "class PolicyDecisionPoint:\n    pass\n"}
    expect("21 no false positive on a module building neither construct",
           construct_violations(quiet, contexts, resp) == [])


def untracked_control(expect, contexts: dict) -> None:
    """Part 2d: an UNTRACKED violating file is seen before it is committed (F-0016)."""
    rel = path_in(contexts, "evidence.audit", "_control_untracked_engine.py")
    full = os.path.join(ROOT, rel)
    listed = subprocess.run(["git", "ls-files", "--error-unmatch", rel],
                            cwd=ROOT, capture_output=True, text=True, check=False)
    if listed.returncode == 0:
        expect("22 untracked violating file is DETECTED", False,
               f"{rel} is unexpectedly tracked; control cannot run")
        return
    try:
        with open(full, "w", encoding="utf-8") as fh:
            fh.write('"""Control file. Deleted by this script."""\n' + ENGINE_SOURCE)
        proc = run_validator()
        expect("22 untracked violating file is DETECTED by the real validator",
               proc.returncode == 1 and rel in proc.stdout,
               f"exit={proc.returncode}")
    finally:
        if os.path.isfile(full):
            os.remove(full)
    after = run_validator()
    expect("23 validator returns to PASS once the control file is removed",
           after.returncode == 0, f"exit={after.returncode}")


def main() -> int:
    failures: list[str] = []

    def expect(label: str, condition: bool, detail: str = "") -> None:
        print(("PASS " if condition else "FAIL ") + label
              + (f"  -- {detail}" if detail else ""))
        if not condition:
            failures.append(label)

    contexts, resp = load_canonical()
    keyword_controls(expect, contexts)
    db_owner, api_owner = authority_controls(expect, contexts, resp)
    placement_controls(expect, contexts, resp, db_owner, api_owner)
    evasion_controls(expect, contexts, resp, db_owner)
    untracked_control(expect, contexts)

    print()
    if failures:
        print(f"NEGATIVE CONTROL: FAILED -> {failures}")
        return 1
    print("NEGATIVE CONTROL: PASS - keyword check is generic; runtime-construct "
          "authority is derived from the canonical documents, accepts each "
          "construct only in its own authority, sees untracked files, survives "
          "rename/move, and fails closed on unresolvable authority or ownership.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
