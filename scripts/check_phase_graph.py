#!/usr/bin/env python3
"""Deterministic phase-dependency validator for ARKALI GENESIS v2 Phase 0.

Validation tool, not application source code.

SOURCE OF TRUTH
---------------
This validator holds NO dependency data of its own. Everything it tests is
parsed at run time from the authoritative documents:

  canonical phase order  <- docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md
                            (Canonical Implementation Phases)
  explicit prerequisites <- docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md
  DENY precondition      <- docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md
                            (ARKALI Self-Evolution)
  HUMAN GATE constraints <- docs/canonical/AUTHORITY_MAP.yaml (human_gates)

A hard-coded copy of the graph would be a shadow verification model: the
authoritative matrix could drift while the validator kept passing against a
stale duplicate. Only the *expected invariants* are asserted in code.

GRAPH COMPOSITION
-----------------
THREE graph-edge classes are inserted into the graph:
  1. explicit prerequisite edges
  2. canonical phase-order edges
  3. DENY precondition edges
HUMAN GATE constraints are checked separately and are NOT graph edges; a gate
suspends progression at a node, it does not add a dependency between phases.

Exit 0 = all checks PASS. Exit 1 = at least one FAIL.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MS = os.path.join(ROOT, "docs/ARKALI_GENESIS_V2_MASTER_SPECIFICATION.md")
MATRIX = os.path.join(ROOT, "docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md")
AUTH = os.path.join(ROOT, "docs/canonical/AUTHORITY_MAP.yaml")

PHASE_RE = re.compile(r"\b(\d{1,2}[AB]?)\b")


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------- parsers
def parse_canonical_order(ms_text):
    """Canonical phase order from the Master Specification phase list."""
    seg = ms_text.split("## Canonical Implementation Phases")[1]
    seg = seg.split("\n## ")[0]
    order = []
    for line in seg.splitlines():
        m = re.match(r"^(\d{1,2}[AB]?)\s+\S", line.strip())
        if m and m.group(1) not in order:
            order.append(m.group(1))
    return order


def parse_prereqs(matrix_text, order):
    """Explicit prerequisites from the dependency matrix table."""
    known = set(order)
    prereq = {}
    for line in matrix_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        raw_id = cells[0].replace("*", "").replace("`", "").strip()
        raw_deps = cells[2].replace("*", "").replace("`", "").strip()
        # "GATE n" in the prerequisite cell is a HUMAN GATE constraint, not a
        # phase dependency. Strip it before extracting phase tokens, otherwise
        # "GATE 1" parses as phase 1 and creates a self-loop.
        raw_deps = re.sub(r"GATE\s*\d+", " ", raw_deps, flags=re.I)
        ids = []
        if "–" in raw_id or "-" in raw_id.replace("–", "-"):
            rng = re.match(r"^(\d+)[–-](\d+)$", raw_id)
            if rng:
                ids = [str(n) for n in range(int(rng.group(1)),
                                             int(rng.group(2)) + 1)]
        if not ids:
            ids = [raw_id] if raw_id in known else []
        if not ids:
            continue
        deps = [d for d in PHASE_RE.findall(raw_deps) if d in known]
        for pid in ids:
            if pid in known:
                prereq[pid] = sorted(set(deps), key=lambda x: order.index(x))
    return prereq


def parse_deny(ms_text, order):
    """DENY preconditions declared in the Master Specification."""
    deny = {}
    seg_split = ms_text.split("## ARKALI Self-Evolution")
    if len(seg_split) > 1:
        seg = seg_split[1].split("\n## ")[0]
        m = re.search(r"DENY until .*?\(Phase (\d{1,2}[AB]?)\)", seg)
        if m:
            gate_phase = m.group(1)
            target = next((p for p in order
                           if _title(ms_text, p).lower()
                           .startswith("self-evolution")), None)
            if target and gate_phase in order:
                deny[target] = gate_phase
    return deny


def _title(ms_text, pid):
    seg = ms_text.split("## Canonical Implementation Phases")[1].split("\n## ")[0]
    for line in seg.splitlines():
        m = re.match(r"^(\d{1,2}[AB]?)\s+(.+)$", line.strip())
        if m and m.group(1) == pid:
            return m.group(2)
    return ""


def parse_gates(auth_path):
    """HUMAN GATE constraints from the machine-readable authority map."""
    import yaml
    return yaml.safe_load(read(auth_path)).get("human_gates", {})


# ---------------------------------------------------------------- graph
def build_edges(order, prereq, deny):
    """THREE graph-edge classes. Human gates are constraints, not edges."""
    edges = set()
    for p, deps in prereq.items():
        for d in deps:
            edges.add((d, p))                       # class 1
    for a, b in zip(order, order[1:]):
        edges.add((a, b))                           # class 2
    for blocked, req in deny.items():
        edges.add((req, blocked))                   # class 3
    return edges


def find_cycle(nodes, edges):
    adj = {n: [] for n in nodes}
    for a, b in edges:
        adj[a].append(b)
    WHITE, GREY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}
    stack, cycle = [], []

    def dfs(u):
        color[u] = GREY
        stack.append(u)
        for v in adj[u]:
            if color[v] == GREY:
                cycle.extend(stack[stack.index(v):] + [v])
                return True
            if color[v] == WHITE and dfs(v):
                return True
        stack.pop()
        color[u] = BLACK
        return False

    for n in nodes:
        if color[n] == WHITE and dfs(n):
            return cycle
    return None


# ---------------------------------------------------------------- run
def validate(ms_text, matrix_text, auth_path, label="AUTHORITATIVE"):
    fails = []

    def ck(name, ok, detail=""):
        print(("PASS " if ok else "FAIL ") + name +
              (("  -- " + detail) if detail else ""))
        if not ok:
            fails.append(name)

    order = parse_canonical_order(ms_text)
    prereq = parse_prereqs(matrix_text, order)
    deny = parse_deny(ms_text, order)
    gates = parse_gates(auth_path)
    idx = {p: i for i, p in enumerate(order)}
    edges = build_edges(order, prereq, deny)

    print(f"[{label}] parsed: {len(order)} phases from MS | "
          f"{len(prereq)} prereq rows from MATRIX | "
          f"{len(deny)} DENY from MS | {len(gates)} human gates from AUTHORITY_MAP")
    print(f"[{label}] graph: {len(edges)} edges "
          f"(3 edge classes; human gates checked separately)\n")

    ck("0  authoritative sources parsed non-empty",
       len(order) > 30 and len(prereq) > 30 and len(deny) == 1 and len(gates) == 8,
       f"order={len(order)} prereq={len(prereq)} deny={deny} gates={len(gates)}")

    fwd = [(p, d) for p, deps in prereq.items() for d in deps
           if idx[d] >= idx[p]]
    ck("1  no phase requires a later or same canonical phase", not fwd, str(fwd))

    cyc = find_cycle(order, edges)
    ck("2  no directed cycle (3 graph-edge classes)", cyc is None,
       " -> ".join(cyc) if cyc else "")

    adj = {n: [] for n in order}
    for a, b in edges:
        adj[a].append(b)
    seen, frontier = {order[0]}, [order[0]]
    while frontier:
        u = frontier.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                frontier.append(v)
    unreach = [p for p in order if p not in seen]
    ck("3  every phase reachable from accepted Phase 0A", not unreach, str(unreach))

    bad = [p for p, deps in prereq.items() if any(idx[d] > idx[p] for d in deps)]
    ck("4  canonical order is a valid execution order", not bad, str(bad))

    ok5 = all(idx[req] < idx[blocked] for blocked, req in deny.items())
    ck("5  DENY precondition satisfiable (gate phase precedes blocked phase)",
       ok5, str(deny))

    rel = next((p for p in order if _title(ms_text, p).startswith("Release")), None)
    ck("6  Release phase remains reachable",
       rel in seen and all(idx[d] < idx[rel] for d in prereq.get(rel, [])),
       f"{rel} prereqs={prereq.get(rel)}")

    inst = next((p for p in order
                 if "Recovery Supervisor Integration" in _title(ms_text, p)), None)
    rs = deny.get(next(iter(deny), ""), None)
    ck("7  Installer phase can integrate the Recovery Supervisor",
       inst is not None and rs is not None and rs in prereq.get(inst, []),
       f"{inst} prereqs={prereq.get(inst)}")

    orphan = [g for g in gates if not gates[g]]
    ck("8  human gate constraints present and named (not graph edges)",
       len(gates) == 8 and not orphan, f"{sorted(gates)}")

    try:
        import yaml
        m = yaml.safe_load(read(auth_path))
        promo = [c["owner"] for c in m["concerns"]
                 if c["concern"] == "stable_promotion"]
        roll = [c["owner"] for c in m["concerns"]
                if c["concern"] == "stable_rollback"]
        ck("9  no duplicate release/lifecycle authority",
           promo == ["lifecycle.release"] and roll == ["lifecycle.recovery"],
           f"promotion={promo} rollback={roll}")
    except Exception as exc:                                # pragma: no cover
        ck("9  no duplicate release/lifecycle authority", False, str(exc))

    print()
    if fails:
        print(f"[{label}] RESULT: FAIL ({len(fails)}) -> {fails}")
        return 1
    print(f"[{label}] RESULT: PASS (10/10) - graph executable, deadlock-free")
    return 0


def main():
    return validate(read(MS), read(MATRIX), AUTH)


if __name__ == "__main__":
    sys.exit(main())
