"""Deterministic Phase Gate Checker.

Owner: acceptance.engine (Protected Core).
Specification: docs/canonical/PHASE_GATE_CHECKER.md.

Properties this implementation must keep:
  * no AI judgement, no network, no clock, no randomness;
  * governed data is parsed from authoritative artifacts, never hard-coded;
  * unknown, malformed, missing or contradictory state FAILS CLOSED;
  * governance data is never silently repaired;
  * a human gate is never self-accepted.
"""

from __future__ import annotations

import pathlib

from arkali.acceptance.gate_verdict import GateVerdict, Verdict
from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.phase_report import PhaseReport
from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.runner import GateRunner
from arkali.control.specification.register_parser import RequirementRegister
from arkali.kernel.contracts.errors import GovernanceStateError
from arkali.kernel.contracts.results import (
    ACCEPTANCE_STOPPING,
    CheckResult,
    Finding,
    HonestState,
    Severity,
)

_SPEC = "docs/canonical/PHASE_GATE_CHECKER.md"


def _fail(check_id: str, summary: str, detail: str = "") -> CheckResult:
    return CheckResult(
        check_id=check_id,
        state=HonestState.FAIL,
        summary=summary,
        detail=detail,
        authoritative_source=_SPEC,
        findings=(
            Finding(
                code=f"PGC-{check_id}",
                severity=Severity.HIGH,
                summary=summary,
                detail=detail,
                source=_SPEC,
            ),
        ),
    )


def _ok(check_id: str, summary: str, detail: str = "") -> CheckResult:
    return CheckResult(
        check_id=check_id,
        state=HonestState.PASS,
        summary=summary,
        detail=detail,
        authoritative_source=_SPEC,
    )


class PhaseGateChecker:
    """Executes checks C1..C5 plus the architecture-gate and governance checks."""

    def __init__(self, repo_root: pathlib.Path) -> None:
        self.repo_root = repo_root
        self.authority_map = AuthorityMap.load(repo_root)
        self.register = RequirementRegister.load(repo_root)
        self.state = GovernanceState.load(repo_root)

    # -- individual checks ----------------------------------------------------

    def check_report_completeness(self, report: PhaseReport) -> CheckResult:
        missing = report.missing_fields()
        if missing:
            return _fail("C1", "phase report is incomplete", f"missing={list(missing)}")
        return _ok("C1", "phase report contains all required fields")

    def check_register_linkage(self, report: PhaseReport) -> CheckResult:
        known = set(self.register.all_ids())
        unknown = sorted(set(report.ark_req_ids_closed) - known)
        if unknown:
            return _fail("C2", "phase report cites unknown requirement ids",
                         f"unknown={unknown}")
        owned = {r.req_id for r in self.register.for_phase(report.phase_id)
                 if r.is_mandatory}
        unaddressed = sorted(owned - set(report.ark_req_ids_closed))
        if unaddressed:
            return _fail(
                "C2", "mandatory requirements for this phase are neither closed "
                      "nor explicitly deferred", f"unaddressed={unaddressed}")
        return _ok("C2", f"all {len(owned)} mandatory phase requirements accounted for")

    def check_recorded_execution(self, report: PhaseReport) -> CheckResult:
        if not report.tests_executed:
            return _fail("C3", "no test execution recorded")
        unnamed = report.unnamed_runs()
        if unnamed:
            return _fail("C3", "recorded run has no command string",
                         f"indices={list(unnamed)}")
        mislabelled = [
            r.command for r in report.failing_runs()
            if report.status is HonestState.PASS
        ]
        if mislabelled:
            return _fail(
                "C3", "non-zero exit code reported under a PASS status",
                f"commands={mislabelled}")
        return _ok("C3", f"{len(report.tests_executed)} runs recorded with exit codes")

    def check_architecture_gates(self) -> tuple[CheckResult, tuple[CheckResult, ...]]:
        runner = GateRunner(self.repo_root, self.authority_map)
        results = runner.run_all()
        failed = [r.check_id for r in results if r.state is HonestState.FAIL]
        if failed:
            return _fail("C4", "architecture gates failed", f"gates={failed}"), results
        summary = GateRunner.summarise(results)
        return _ok("C4", f"{len(results)} architecture gates evaluated",
                   f"states={summary}"), results

    def check_honest_state_integrity(self, report: PhaseReport) -> CheckResult:
        if report.status is HonestState.PASS and report.failing_runs():
            return _fail("C5", "PASS status contradicts a failing recorded run")
        conditional_gap = self.register.conditional_without_rule()
        if conditional_gap:
            return _fail("C5", "CONDITIONAL requirement lacks an objective rule",
                         f"ids={list(conditional_gap)}")
        return _ok("C5", "no non-PASS state was converted into PASS")

    def check_open_findings(self) -> CheckResult:
        open_rows = self.state.open_stopping_findings
        if open_rows:
            return _fail("FINDINGS", "open BLOCKER/HIGH findings block acceptance",
                         f"rows={list(open_rows)}")
        return _ok("FINDINGS", "no open BLOCKER or HIGH finding")

    def check_prerequisites(self, phase_id: str) -> CheckResult:
        prereqs = self.state.prerequisites_of(phase_id)
        unmet = [
            dep for dep in prereqs
            if dep in self.state.phases and not self.state.phase(dep).is_accepted
        ]
        unknown = [dep for dep in prereqs if dep not in self.state.phases]
        if unknown:
            return _fail("PREREQ", "prerequisite phase has no status row",
                         f"unknown={unknown}")
        if unmet:
            return _fail("PREREQ", "prerequisite phase is not accepted",
                         f"unmet={unmet}")
        return _ok("PREREQ", f"all {len(prereqs)} prerequisites accepted")

    def check_human_gate(self, phase_id: str) -> CheckResult:
        """A human gate is never self-accepted: only a recorded decision counts."""
        required = self._human_gate_for(phase_id)
        if required is None:
            return CheckResult(
                check_id="HUMAN_GATE",
                state=HonestState.NOT_APPLICABLE,
                summary=f"phase {phase_id} carries no human gate",
                authoritative_source=_SPEC,
            )
        if required in self.state.accepted_human_gates:
            return _ok("HUMAN_GATE", f"{required} has a recorded acceptance")
        return CheckResult(
            check_id="HUMAN_GATE",
            state=HonestState.BLOCKED,
            summary=f"{required} required and not recorded",
            authoritative_source=_SPEC,
        )

    def _human_gate_for(self, phase_id: str) -> str | None:
        """Which gate this phase carries, read from authoritative state.

        NO SHADOW MODEL: the mapping is parsed from the Gate column of
        IMPLEMENTATION_DEPENDENCY_MATRIX.md. Phase 0A and 0B form one acceptance
        package, so 0A and 0 inherit the gate the matrix records against 0B.
        """
        direct = self.state.phase_gates.get(phase_id)
        if direct:
            return direct
        if phase_id in ("0", "0A"):
            return self.state.phase_gates.get("0B")
        return None

    # -- orchestration --------------------------------------------------------

    def evaluate(
        self, report: PhaseReport, requested_next_phase: str | None = None
    ) -> GateVerdict:
        """Run every check and produce a deterministic verdict."""
        if report.phase_id not in self.state.phases:
            raise GovernanceStateError(
                f"phase {report.phase_id!r} has no governance status row"
            )
        gate_result, gate_details = self.check_architecture_gates()
        checks = [
            self.check_report_completeness(report),
            self.check_register_linkage(report),
            self.check_recorded_execution(report),
            gate_result,
            self.check_honest_state_integrity(report),
            self.check_open_findings(),
            self.check_prerequisites(report.phase_id),
            self.check_human_gate(report.phase_id),
        ]
        checks.extend(gate_details)
        findings = tuple(f for c in checks for f in c.findings)

        human = next(
            (c for c in checks if c.check_id == "HUMAN_GATE"
             and c.state is HonestState.BLOCKED),
            None,
        )
        failing = [c for c in checks if c.state is HonestState.FAIL]
        stopping = [f for f in findings if f.severity in ACCEPTANCE_STOPPING]

        if failing or stopping:
            verdict, permitted = Verdict.PHASE_BLOCKED, False
            reason = (f"failing checks: {[c.check_id for c in failing]}"
                      if failing else f"stopping findings: {len(stopping)}")
        elif human is not None:
            verdict, permitted = Verdict.AWAITING_HUMAN_GATE, False
            reason = human.summary
        else:
            verdict, permitted = Verdict.PHASE_ACCEPTED_BY_MACHINE, True
            reason = ""

        return GateVerdict(
            phase_id=report.phase_id,
            requested_next_phase=requested_next_phase,
            verdict=verdict,
            checks=tuple(checks),
            findings=findings,
            human_gate_required=human.summary.split()[0] if human else None,
            progression_permitted=permitted,
            failing_condition=reason,
        )
