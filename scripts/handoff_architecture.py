"""Architecture-metric drift controls for ARKALI_HANDOFF.md.

Validation tool, not application source code.

WHY THIS EXISTS (F-0047). F-0046 added seven narrative controls to
`check_handoff.py`, but every one of them is a predicate over GOVERNANCE state -
which phase is current, what it declares, which commit a revision was generated
at, whether the interpreter and the execution surfaces exist. The validator
never imported `control.architecture` at all, so no architecture number in the
manifest had ever been compared with anything. Phase 9 Package 1 added two
cross-context edges, the mandatory refresh did not re-derive the summary, and
the manifest reported one edge count while the gates measured another - with the
validator reporting PASS. The F-0002/F-0011/F-0041 transcribed-value family.

NO SHADOW MODEL - the F-0028 rule applied to a validator. Nothing here
re-implements a measurement. The canonical gate runner is executed and every
number is read back out of the results it produced.

ADR-0008 decomposition: `check_handoff.py` reached its 400 logical-line budget
and these controls have a different subject and a different authority from the
governance-state controls that remain there. No GATE 8 exception was requested.
"""
from __future__ import annotations

import pathlib
import re
import sys
from typing import Any

from handoff_markdown import DriftReport, first_int, plain, section

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

#: The section carrying the LIVE architecture summary. Matched by ROLE, so the
#: section can be renumbered without expiring the controls that read it.
CURRENT_STATE_HEADING = r"^##\s*\d+\.\s*Current verified state\s*$"
#: How far past the depth claim the path that belongs to it may be written.
_PATH_WINDOW = 240
#: A dotted module or context name as the manifest renders one.
_NODE = r"[a-z_][\w.]*\.[\w.]+"


def _canonical_fan_in(repo: pathlib.Path, amap: Any) -> dict[str, int]:
    """Every module's fan-in, measured by the canonical budget gate itself.

    The gate renders a fan-in violation as `<module>: fan-in <n> > <ceiling>`.
    Lowering the declared ceiling to zero in an IN-MEMORY copy of the authority
    map therefore makes it report its own measured value for every module that
    has one, so this reads the gate's arithmetic instead of restating it. The
    authority map file is never written.
    """
    from arkali.control.architecture.authority_map import AuthorityMap
    from arkali.control.architecture.gates.base import GateContext
    from arkali.control.architecture.gates.structure_gates import ArchitectureBudgetGate

    data = amap.model_dump()
    data["architecture_budgets"] = {
        **amap.architecture_budgets, "max_fan_in_per_module": 0
    }
    probe = ArchitectureBudgetGate().evaluate(
        GateContext(repo, AuthorityMap.model_validate(data))
    )
    measured: dict[str, int] = {}
    for finding in probe.findings:
        found = re.match(r"(\S+): fan-in (\d+) > ", finding.summary)
        if found:
            measured[found.group(1)] = int(found.group(2))
    return measured


def architecture_truth(repo: pathlib.Path) -> dict[str, Any]:
    """Live architecture metrics, taken from the canonical gate mechanism.

    The depth and its path come from `ArchitectureBudgetGate.measure_depth`,
    which `control.architecture` had already made public so that "the gate's own
    evidence and the drift controls read the same measurement rather than two
    implementations of it". The edge count is taken from TWO independent gates
    and is refused unless they agree, so one gate being reworded or rescoped
    cannot quietly become its sole source.

    A metric that cannot be derived is returned as None, and the caller reports
    HANDOFF_DRIFT rather than silently skipping the comparison.
    """
    from arkali.control.architecture.authority_map import AuthorityMap
    from arkali.control.architecture.budget_measurement import (
        MEASUREMENT_KEY,
        MeasurementContract,
    )
    from arkali.control.architecture.gates.base import GateContext
    from arkali.control.architecture.gates.runner import GateRunner
    from arkali.control.architecture.gates.structure_gates import ArchitectureBudgetGate

    amap = AuthorityMap.load(repo)
    results = GateRunner(repo, amap).run_all()
    by_id = {r.check_id: r for r in results}
    budgets = amap.architecture_budgets
    contract = MeasurementContract.from_authority_map(
        {MEASUREMENT_KEY: amap.architecture_budget_measurement}, amap.source_path
    )
    depth = ArchitectureBudgetGate.measure_depth(
        GateContext(repo, amap), budgets, contract
    )

    counted = [
        first_int(by_id[gate].summary)
        for gate in ("forbidden_dependency_direction", "forbidden_cycles")
        if gate in by_id
    ]
    edges = counted[0] if counted and len(set(counted)) == 1 else None

    budget_gate = by_id.get("architecture_budget_violation")
    version = None
    if budget_gate is not None:
        found = re.search(r"measurement_contract=(\S+)", budget_gate.detail)
        version = found.group(1) if found else None

    return {
        "gates_total": len(results),
        "gates_passing": sum(1 for r in results if r.state.value == "PASS"),
        "violations": sum(len(r.findings) for r in results),
        "edges": edges,
        "budgets_evaluated": (
            first_int(budget_gate.summary) if budget_gate is not None else None
        ),
        "measurement_contract": version,
        "depth": depth.depth,
        "depth_allowed": int(budgets["max_orchestration_depth"]),
        "depth_path": " -> ".join(depth.path),
        "fan_in": _canonical_fan_in(repo, amap),
        "fan_in_allowed": int(budgets["max_fan_in_per_module"]),
    }


def check_architecture(repo: pathlib.Path, text: str, report: DriftReport) -> None:
    """The manifest's LIVE architecture summary must agree with the gates.

    SCOPE IS THE LIVE SECTION ONLY. The accepted-commit history and the
    generation ledger record what was measured at a past commit. Those are
    truthful historical records and must keep their own numbers; re-deriving
    them against today's tree would destroy evidence rather than repair it.

    ANTI-VACUITY (F-0017). Every claim is required to be PRESENT. A rewording
    that removes a metric fails the run instead of quietly comparing nothing.
    """
    body = plain(section(text, CURRENT_STATE_HEADING))
    report.assert_true("a current verified-state section exists", bool(body.strip()))
    if not body.strip():
        return
    truth = architecture_truth(repo)

    def stated(name: str, pattern: str) -> re.Match[str] | None:
        found = re.search(pattern, body, re.IGNORECASE)
        report.assert_true(
            f"the live architecture summary still states the {name}",
            found is not None,
            "the claim was reworded or removed, so nothing was compared",
        )
        return found

    report.assert_true(
        "every architecture gate passes live",
        truth["gates_passing"] == truth["gates_total"] and truth["gates_total"] > 0,
        f"{truth['gates_passing']} of {truth['gates_total']} gates PASS",
    )

    for name, pattern, key in (
        ("architecture gate count", r"(\d+)\s+gates?\s+PASS", "gates_total"),
        ("architecture violation count",
         r"architecture violations\s*\|\s*(\d+)", "violations"),
        ("cross-context edge count",
         r"(\d+)\s+(?:real\s+)?cross-context edges", "edges"),
        ("numeric budget count", r"(\d+)\s+numeric budgets", "budgets_evaluated"),
    ):
        found = stated(name, pattern)
        if found:
            report.check(name, int(found.group(1)), truth[key])

    version = stated("budget measurement contract", r"ratified contract\s+([0-9][0-9.]*)")
    if version:
        report.check(
            "budget measurement contract", version.group(1), truth["measurement_contract"]
        )

    depth = stated(
        "orchestration depth", r"max_orchestration_depth is\s+(\d+)\s+of\s+(\d+)"
    )
    if depth:
        report.check("orchestration depth", int(depth.group(1)), truth["depth"])
        report.check(
            "orchestration depth ceiling", int(depth.group(2)), truth["depth_allowed"]
        )
        check_depth_path(body[depth.end():], truth, report)

    check_fan_in(body, truth, report)


def check_depth_path(
    after_depth: str, truth: dict[str, Any], report: DriftReport
) -> None:
    """The path stated with the depth claim must be the measured one.

    The search is ANCHORED to the depth claim rather than run over the whole
    section, because the live summary legitimately names other import chains -
    the two edges Phase 9 Package 1 added, for one - and a control that took the
    first chain it saw would be reporting on whichever sentence came first.
    """
    found = re.search(rf"({_NODE}(?:\s*->\s*{_NODE})+)", after_depth[:_PATH_WINDOW])
    report.assert_true(
        "the live architecture summary still states the orchestration depth path",
        found is not None,
        "no import chain follows the depth claim, so nothing was compared",
    )
    if found:
        report.check(
            "orchestration depth path",
            re.sub(r"\s*->\s*", " -> ", found.group(1).strip()),
            truth["depth_path"],
        )


def check_fan_in(body: str, truth: dict[str, Any], report: DriftReport) -> None:
    """Every fan-in figure the live summary states must be the measured one.

    The manifest names a module by its context-relative path; the measurement
    keys are fully qualified. The name is RESOLVED rather than rewritten, and an
    ambiguous or unknown name fails closed instead of being skipped.
    """
    claims = re.findall(
        rf"({_NODE})\s+fan-in is\s+(\d+)\s+of\s+(\d+)", body, re.IGNORECASE
    )
    report.assert_true(
        "the live architecture summary still states a fan-in figure",
        bool(claims),
        "no fan-in claim was found, so nothing was compared",
    )
    for name, measured, ceiling in claims:
        matches = [
            key for key in truth["fan_in"] if key == name or key.endswith(f".{name}")
        ]
        report.assert_true(
            f"the fan-in subject {name!r} resolves to exactly one module",
            len(matches) == 1,
            f"resolved to {matches}",
        )
        if len(matches) == 1:
            report.check(f"fan-in of {name}", int(measured), truth["fan_in"][matches[0]])
        report.check(f"fan-in ceiling for {name}", int(ceiling), truth["fan_in_allowed"])
