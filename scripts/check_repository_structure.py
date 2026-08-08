#!/usr/bin/env python3
"""Phase 1 repository structure validator for ARKALI GENESIS v2.

Validation tool, not application source code.

Like the Phase 0 validators, this holds NO structural data of its own: the
expected tree is derived from docs/canonical/AUTHORITY_MAP.yaml at run time.
A hard-coded expectation would be a shadow model (Phase 0 finding F-0013).

Checks (Phase 1 scope only):
  1  every declared bounded context has its module root on disk
  2  every context module root is a Python package
  3  every context package declares context/layer/rank/protected_core
  4  no duplicate module_root (structural shadow scan)
  5  no cross-context implementation modules exist yet
  6  no forbidden dependency direction among Phase 1 files
  7  architecture budgets respected by Phase 1 files
  8  no Python-keyword segment in any module root
  9  no secret-bearing file is tracked
 10  no fake implementation markers
 11  no Stable mutation path introduced
 12  no Phase 2+ capability implemented

Exit 0 = all PASS. Exit 1 = at least one FAIL.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUTH = os.path.join(ROOT, "docs/canonical/AUTHORITY_MAP.yaml")

KEYWORDS = {"import", "class", "def", "return", "from", "global", "lambda",
            "pass", "raise", "try", "with", "yield", "assert", "async",
            "await", "break", "continue", "del", "elif", "else", "except",
            "finally", "for", "if", "in", "is", "none", "nonlocal", "not",
            "or", "and", "while"}

FAKE_MARKERS = [r"\bTODO\b", r"\bFIXME\b", r"\bstub\b", r"\bdummy\b",
                r"\bfake\b", r"NotImplementedError", r"\bplaceholder\b",
                r"\bmock\b"]

SECRET_PATTERNS = [r"AKIA[0-9A-Z]{16}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
                   r"(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{12,}"]

results: list[tuple[str, str, str]] = []   # (state, name, detail)


def record(state: str, name: str, detail: str = "") -> None:
    results.append((state, name, detail))
    print(f"{state:14s} {name}" + (f"  -- {detail}" if detail else ""))


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return [p for p in out.stdout.splitlines() if p]


def main() -> int:
    import yaml
    with open(AUTH, encoding="utf-8") as fh:
        amap = yaml.safe_load(fh)
    contexts = amap["contexts"]
    ranks = {layer["name"]: layer["rank"] for layer in amap["layers"]}
    siblings = {(e["from"], e["to"]) for e in amap["allowed_sibling_edges"]}
    budgets = amap["architecture_budgets"]

    # 1 module roots exist
    missing = [f"{n} -> {m['module_root']}" for n, m in contexts.items()
               if not os.path.isdir(os.path.join(ROOT, m["module_root"]))]
    record("PASS" if not missing else "FAIL",
           f"1  all {len(contexts)} context module roots exist", str(missing))

    # 2 packages
    notpkg = [m["module_root"] for m in contexts.values()
              if not os.path.isfile(os.path.join(ROOT, m["module_root"], "__init__.py"))]
    record("PASS" if not notpkg else "FAIL",
           "2  every context module root is a Python package", str(notpkg))

    # 3 declarations
    bad = []
    for name, meta in contexts.items():
        init = os.path.join(ROOT, meta["module_root"], "__init__.py")
        if not os.path.isfile(init):
            continue
        src = open(init, encoding="utf-8").read()
        tree = ast.parse(src)
        decl = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                try:
                    decl[node.targets[0].id] = ast.literal_eval(node.value)
                except Exception:  # noqa: BLE001
                    pass
        if decl.get("__context__") != name:
            bad.append(f"{name}:__context__")
        if decl.get("__layer__") != meta["layer"]:
            bad.append(f"{name}:__layer__")
        if decl.get("__layer_rank__") != ranks[meta["layer"]]:
            bad.append(f"{name}:__layer_rank__")
        if decl.get("__protected_core__") != meta["protected_core"]:
            bad.append(f"{name}:__protected_core__")
    record("PASS" if not bad else "FAIL",
           "3  context packages declare context/layer/rank/protected_core", str(bad))

    # 4 duplicate module roots (shadow structural scan)
    roots = [m["module_root"] for m in contexts.values()]
    dupes = {r for r in roots if roots.count(r) > 1}
    record("PASS" if not dupes else "FAIL",
           "4  no duplicate module_root (shadow scan)", str(dupes))

    # 5 no implementation modules yet
    impl = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, "backend", "arkali")):
        for f in files:
            if f.endswith(".py") and f != "__init__.py":
                impl.append(os.path.relpath(os.path.join(dirpath, f), ROOT))
    record("PASS" if not impl else "FAIL",
           "5  no context implementation modules exist yet", str(impl))

    # 6 dependency direction among Phase 1 python files
    violations = []
    ctx_by_path = {m["module_root"].replace("backend/", "").replace("/", "."): n
                   for n, m in contexts.items()}
    for dirpath, _d, files in os.walk(os.path.join(ROOT, "backend", "arkali")):
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(dirpath, f)
            rel = os.path.relpath(p, os.path.join(ROOT, "backend")).replace(os.sep, ".")
            owner = next((c for mp, c in ctx_by_path.items()
                          if rel.startswith(mp)), None)
            if owner is None:
                continue
            tree = ast.parse(open(p, encoding="utf-8").read())
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    mods = [node.module]
                for mod in mods:
                    if not mod.startswith("arkali."):
                        continue
                    target = next((c for mp, c in ctx_by_path.items()
                                   if mod.replace("arkali.", "").startswith(
                                       mp.replace("arkali.", ""))), None)
                    if target is None or target == owner:
                        continue
                    if ranks[contexts[target]["layer"]] < ranks[contexts[owner]["layer"]]:
                        continue
                    if (owner, target) in siblings:
                        continue
                    violations.append(f"{owner} -> {target}")
    if not impl and not violations:
        record("PASS (vacuous)",
               "6  no forbidden dependency direction",
               "0 cross-context imports exist yet; check is structurally "
               "correct but has nothing to reject. Meaningful from Phase 2")
    else:
        record("PASS" if not violations else "FAIL",
               "6  no forbidden dependency direction", str(violations))

    # 7 architecture budgets over Phase 1 files
    over = []
    maxlines = budgets["max_module_logical_lines"]
    for f in tracked_files() + [os.path.relpath(os.path.join(d, n), ROOT).replace(os.sep, "/")
                                for d, _s, ns in os.walk(os.path.join(ROOT, "backend"))
                                for n in ns if n.endswith(".py")]:
        if not f.endswith(".py"):
            continue
        fp = os.path.join(ROOT, f)
        if not os.path.isfile(fp):
            continue
        logical = [ln for ln in open(fp, encoding="utf-8").read().splitlines()
                   if ln.strip() and not ln.strip().startswith("#")]
        if len(logical) > maxlines:
            over.append(f"{f}={len(logical)}>{maxlines}")
    record("PASS" if not over else "FAIL",
           f"7  architecture budget: module <= {maxlines} logical lines", str(over))

    # 8 python keyword segments
    kw = [f"{n} -> {m['module_root']}" for n, m in contexts.items()
          if any(s.lower() in KEYWORDS for s in m["module_root"].split("/"))]
    record("PASS" if not kw else "FAIL",
           "8  no Python-keyword segment in any module root", str(kw))

    # 9 secrets
    hits = []
    for f in tracked_files():
        fp = os.path.join(ROOT, f)
        if not os.path.isfile(fp):
            continue
        if os.path.basename(f) in {".env"} or f.endswith((".pem", ".key", ".p12")):
            hits.append(f"tracked secret-bearing file: {f}")
            continue
        try:
            body = open(fp, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for pat in SECRET_PATTERNS:
            if re.search(pat, body):
                hits.append(f"{f}: matches {pat}")
    record("PASS" if not hits else "FAIL", "9  no secret-bearing tracked file", str(hits))

    # 10 fake implementation markers in Phase 1 python
    fake = []
    for f in tracked_files():
        if not f.endswith(".py") or f.startswith("scripts/"):
            continue
        fp = os.path.join(ROOT, f)
        if not os.path.isfile(fp):
            continue
        body = open(fp, encoding="utf-8").read()
        for pat in FAKE_MARKERS:
            if re.search(pat, body):
                fake.append(f"{f}: {pat}")
    record("PASS" if not fake else "FAIL",
           "10 no fake-implementation markers in Phase 1 source", str(fake))

    # 11 stable mutation path
    stable = []
    for f in tracked_files():
        if not f.endswith(".py") or f.startswith("scripts/"):
            continue
        fp = os.path.join(ROOT, f)
        if os.path.isfile(fp) and re.search(r"WRITE_STABLE_FILE|ROLLBACK_STABLE",
                                            open(fp, encoding="utf-8").read()):
            stable.append(f)
    record("PASS" if not stable else "FAIL",
           "11 no Stable mutation path introduced", str(stable))

    # 12 no Phase 2+ capability
    forbidden = []
    for f in tracked_files():
        if not f.endswith(".py") or f.startswith(("scripts/", "backend/tests/")):
            continue
        fp = os.path.join(ROOT, f)
        if not os.path.isfile(fp):
            continue
        body = open(fp, encoding="utf-8").read()
        for pat in [r"FastAPI\(", r"APIRouter\(", r"@app\.", r"create_engine\(",
                    r"declarative_base\(", r"BaseModel\)"]:
            if re.search(pat, body):
                forbidden.append(f"{f}: {pat}")
    record("PASS" if not forbidden else "FAIL",
           "12 no Phase 2+ capability implemented", str(forbidden))

    print()
    fails = [r for r in results if r[0] == "FAIL"]
    npass = len([r for r in results if r[0].startswith("PASS")])
    print(f"SUMMARY: {npass} pass, {len(fails)} fail, {len(results)} total")
    if fails:
        print("FAILING: " + "; ".join(f"{n}" for _s, n, _d in fails))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
