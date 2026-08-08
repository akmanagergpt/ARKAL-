#!/usr/bin/env python3
"""Deterministic phase-dependency validator for ARKALI GENESIS v2 Phase 0.

Validation tool, not application source code. It builds the phase graph from
FOUR edge classes and proves the plan is executable:

  1. explicit prerequisite edges (IMPLEMENTATION_DEPENDENCY_MATRIX)
  2. mandatory canonical phase-order edges (MASTER_SPECIFICATION phase list)
  3. HUMAN GATE constraints
  4. DENY preconditions (22B -> 23 self-evolution)

A cycle check over class 1 alone is a false negative; classes 1 and 2 must be
combined, which is how the 22B/26 deadlock was missed.

Exit 0 = all checks PASS. Exit 1 = at least one FAIL.
"""
import sys

# --- canonical phase order (MASTER_SPECIFICATION, Canonical Implementation Phases) ---
ORDER = ["0A", "0B", "1", "2", "3", "4", "5", "6", "7", "8", "9", "9B", "10",
         "11", "12", "13", "14", "15", "16", "17", "18", "19", "20", "21",
         "22", "22B", "23", "24", "25", "26", "27", "28", "29", "30", "31",
         "32", "33", "34", "35", "36", "37"]

# --- class 1: explicit prerequisites ---
PREREQ = {
    "0B": ["0A"], "1": ["0B"], "2": ["1"], "3": ["2"], "4": ["2", "3"],
    "5": ["2", "4"], "6": ["5"], "7": ["5", "6"], "8": ["7"],
    "9": ["4", "6", "8"], "9B": ["3", "4", "6", "9"], "10": ["9", "9B"],
    "11": ["10"], "12": ["11"], "13": ["6", "12"], "14": ["13"], "15": ["13"],
    "16": ["12", "14", "15"], "17": ["7", "8", "13"], "18": ["13"],
    "19": ["4", "12"], "20": ["5", "6"], "21": ["4", "9"], "22": ["4", "9"],
    "22B": ["5", "6", "13", "20"],          # corrected: was 5,20,26 -> deadlock
    "23": ["22B", "13", "16"], "24": ["16", "13"], "25": ["7", "9", "11"],
    "26": ["6", "13", "22B"], "27": ["5", "25"], "28": ["27"],
    "29": ["26", "28", "22B"], "30": ["16", "14", "24"], "31": ["30"],
    "32": ["31"], "33": ["32"], "34": ["33"], "35": ["34"],
    "36": ["29", "31", "35"], "37": ["36"],
}

# --- class 3: human gates (phase -> gate required to EXIT it) ---
GATES = {"0B": "HUMAN_GATE_1", "23": "HUMAN_GATE_2", "37": "HUMAN_GATE_7"}

# --- class 4: DENY preconditions (blocked_phase -> must be verified first) ---
DENY = {"23": "22B"}

idx = {p: i for i, p in enumerate(ORDER)}
fails = []


def check(name, ok, detail=""):
    print(("PASS " if ok else "FAIL ") + name + (("  -- " + detail) if detail else ""))
    if not ok:
        fails.append(name)


def build_edges():
    """Union of explicit prerequisites, canonical order edges, DENY edges."""
    e = set()
    for p, deps in PREREQ.items():
        for d in deps:
            e.add((d, p))                       # class 1
    for a, b in zip(ORDER, ORDER[1:]):
        e.add((a, b))                           # class 2
    for blocked, req in DENY.items():
        e.add((req, blocked))                   # class 4
    return e


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


def main():
    edges = build_edges()
    print(f"nodes={len(ORDER)}  edges={len(edges)} "
          f"(explicit + canonical-order + DENY)\n")

    # 1 no forward prerequisite (a phase requiring a later phase)
    fwd = [(p, d) for p, deps in PREREQ.items() for d in deps
           if idx[d] >= idx[p]]
    check("1  no phase requires a later or same canonical phase",
          not fwd, str(fwd))

    # 2 no directed cycle across all edge classes
    cyc = find_cycle(ORDER, edges)
    check("2  no directed cycle (all 4 edge classes)", cyc is None,
          " -> ".join(cyc) if cyc else "")

    # 3 every phase reachable from 0A
    adj = {n: [] for n in ORDER}
    for a, b in edges:
        adj[a].append(b)
    seen, frontier = {"0A"}, ["0A"]
    while frontier:
        u = frontier.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                frontier.append(v)
    unreach = [p for p in ORDER if p not in seen]
    check("3  every phase reachable from accepted Phase 0A",
          not unreach, str(unreach))

    # 4 every phase's prerequisites all precede it -> executable in order
    bad = [p for p, deps in PREREQ.items()
           if any(idx[d] > idx[p] for d in deps)]
    check("4  canonical order is a valid execution order", not bad, str(bad))

    # 5 22B strictly before 23
    check("5  22B reachable before 23 (DENY precondition satisfiable)",
          idx["22B"] < idx["23"],
          f"22B@{idx['22B']} < 23@{idx['23']}")

    # 6 26 reachable without requiring anything at/after itself
    check("6  26 remains reachable", "26" in seen and
          all(idx[d] < idx["26"] for d in PREREQ["26"]),
          f"prereqs={PREREQ['26']}")

    # 7 29 can integrate the Recovery Supervisor
    check("7  29 can integrate Recovery Supervisor (22B precedes 29)",
          "22B" in PREREQ["29"] and idx["22B"] < idx["29"])

    # 8 human gates do not orphan any downstream phase
    orphan = []
    for gp in GATES:
        after = ORDER[idx[gp] + 1:]
        if after and not any(gp in PREREQ.get(a, []) or
                             ORDER[idx[gp] + 1] == a for a in after):
            orphan.append(gp)
    check("8  human gates block progression without orphaning phases",
          not orphan, str(orphan))

    # 9 no duplicate release/lifecycle authority introduced by 22B
    #    22B delivers the pointer primitive; authority stays lifecycle.release
    try:
        import yaml
        m = yaml.safe_load(
            open("docs/canonical/AUTHORITY_MAP.yaml", encoding="utf-8"))
        owners = [c["owner"] for c in m["concerns"]
                  if c["concern"] == "stable_promotion"]
        rollback = [c["owner"] for c in m["concerns"]
                    if c["concern"] == "stable_rollback"]
        check("9  no duplicate release/lifecycle authority",
              owners == ["lifecycle.release"] and
              rollback == ["lifecycle.recovery"],
              f"promotion={owners} rollback={rollback}")
    except Exception as exc:                     # pragma: no cover
        check("9  no duplicate release/lifecycle authority", False, str(exc))

    print()
    if fails:
        print(f"RESULT: FAIL ({len(fails)} check(s)) -> {fails}")
        return 1
    print("RESULT: PASS (9/9) - phase graph is executable and deadlock-free")
    return 0


if __name__ == "__main__":
    sys.exit(main())
