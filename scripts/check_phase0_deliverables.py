#!/usr/bin/env python3
"""Phase 0A/0B deliverable reconciliation for ARKALI GENESIS v2.

Validation tool, not application source code.

The deliverable COUNT is derived mechanically by parsing the canonical Build
Protocol lists -- never hand-entered. Each canonical bullet is then resolved to
a repository artifact by BOTH file existence AND a content probe, because a
mapping asserted by the author is not a check (defect F-0008).

Exit 0 = every canonical bullet resolved. Exit 1 = at least one unresolved.
"""
import os
import re
import sys

BP = "docs/CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md"

# canonical bullet (matched by its leading text) -> (artifact, content probe)
RESOLUTION = {
    "final repository tree":
        ("docs/canonical/ARCHITECTURE.md", "Final greenfield repository architecture"),
    "four-plane architecture map":
        ("docs/canonical/ARCHITECTURE.md", "Four-plane architecture map"),
    "bounded-context dependency map":
        ("docs/canonical/ARCHITECTURE.md", "Dependency direction rules"),
    "formal state-machine inventory":
        ("docs/canonical/STATE_MACHINES.md", "Cross-cutting invariants"),
    "capability graph schema":
        ("docs/canonical/EXECUTION_AND_CAPABILITY.md", "capability_node:"),
    "contract inventory":
        ("docs/canonical/CONTRACT_INVENTORY.md", "contract families"),
    "artifact/provenance model":
        ("docs/canonical/EXECUTION_AND_CAPABILITY.md", "Artifact / provenance architecture"),
    "durable execution architecture":
        ("docs/canonical/EXECUTION_AND_CAPABILITY.md", "Durable execution architecture"),
    "worker/resource scheduler model":
        ("docs/canonical/EXECUTION_AND_CAPABILITY.md", "resource scheduler architecture"),
    "observability architecture":
        ("docs/canonical/ARCHITECTURE.md", "Observability architecture"),
    "persistence strategy":
        ("docs/canonical/ARCHITECTURE.md", "Persistence architecture"),
    "verification/test architecture":
        ("docs/canonical/VERIFICATION_ARCHITECTURE.md", "Verification / test architecture"),
    "evidence graph strategy":
        ("docs/canonical/VERIFICATION_ARCHITECTURE.md", "Evidence graph strategy"),
    "implementation dependency matrix":
        ("docs/canonical/IMPLEMENTATION_DEPENDENCY_MATRIX.md", "Critical ordering constraints"),
    "initial ADRs":
        ("docs/adr/ADR_INDEX.md", "ADR-0009"),
    "contradiction/blocker analysis":
        ("docs/build/CONTRADICTION_ANALYSIS.md", "Contradictions found: 0"),
    "canonical requirement register":
        ("docs/canonical/REQUIREMENT_REGISTER.md", "ARK-REQ-0001"),
    "ADR-0001 plus docs/canonical/AUTHORITY_MAP.yaml":
        ("docs/canonical/AUTHORITY_MAP.yaml", "schema_version:"),
    "canonical architecture budgets":
        ("docs/canonical/AUTHORITY_MAP.yaml", "architecture_budgets:"),
    "protected-core membership declaration":
        ("docs/canonical/AUTHORITY_MAP.yaml", "protected_core: true"),
    "trust/sandbox model and isolation property matrix":
        ("docs/canonical/SECURITY_ARCHITECTURE.md", "Isolation Backend architecture"),
    "security/policy architecture":
        ("docs/canonical/SECURITY_ARCHITECTURE.md", "Computer-Use operation classes"),
    "canonical Windows clean-test baseline definition":
        ("docs/canonical/CLEAN_TEST_BASELINE.md", "Absent-tooling list"),
    "Golden Repair defect corpus definition":
        ("docs/canonical/GOLDEN_REPAIR_CORPUS_DEFINITION.md", "Corpus entry schema"),
    "minimal deterministic Phase Gate Checker specification":
        ("docs/canonical/PHASE_GATE_CHECKER.md", "What it validates"),
    "BUILD_STATE":
        ("docs/build/BUILD_STATE.md", "Phase status"),
    "PHASE 0 REPORT":
        ("docs/build/PHASE_HISTORY.md", "Phase 0 report"),
}


def canonical_bullets(text, start, end):
    """Parse the canonical bullet list between two headings. Count is derived."""
    seg = text.split(start)[1].split(end)[0]
    return re.findall(r"^- (.+)$", seg, re.M)


def resolve(bullet):
    for key, (path, probe) in RESOLUTION.items():
        if bullet.startswith(key):
            if not os.path.exists(path):
                return False, path, "MISSING FILE"
            body = open(path, encoding="utf-8").read().lower()
            if probe.lower() not in body:
                return False, path, "PROBE NOT FOUND"
            return True, path, "ok"
    return False, "-", "NO MAPPING"


def run(label, bullets):
    print(f"=== PHASE {label} — {len(bullets)} canonical bullets (derived) ===")
    passed = 0
    for b in bullets:
        ok, path, why = resolve(b)
        passed += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {b[:58]:58s} -> {path}"
              + ("" if ok else f"  ({why})"))
    print(f"  PHASE {label}: {passed}/{len(bullets)}\n")
    return passed, len(bullets)


def main():
    text = open(BP, encoding="utf-8").read()
    a = canonical_bullets(text, "### Phase 0A", "### Phase 0B")
    b = canonical_bullets(text, "### Phase 0B", "Submit PHASE 0")
    pa, ta = run("0A", a)
    pb, tb = run("0B", b)
    ok = (pa == ta) and (pb == tb)
    print(f"RESULT: {'PASS' if ok else 'FAIL'} — 0A {pa}/{ta}, 0B {pb}/{tb}")
    print("Counts derived from the canonical Build Protocol lists, not entered by hand.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
