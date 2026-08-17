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

from arkali.acceptance.discharge_shape import check_claim_shape
from arkali.acceptance.external_result import ExternalProviderResultRule
from arkali.acceptance.gate_verdict import GateVerdict, Verdict
from arkali.acceptance.governance_gates import _evaluate_prerequisites, _human_gate_for
from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.migration_release_check import _evaluate_migration_data_loss_risk
from arkali.acceptance.phase_report import PhaseReport
from arkali.acceptance.protected_core_check import (
    evaluate_report_profile,
    load_protected_core,
)
from arkali.acceptance.requirement_claim import TraceabilityRecord, reconcile_discharge
from arkali.acceptance.rescoring_authorization import (
    evidence_package_digest,
    find_authorization,
)
from arkali.control.architecture.authority_map import AuthorityMap
from arkali.control.architecture.gates.runner import GateRunner
from arkali.control.specification.register_parser import RequirementRegister
from arkali.kernel.contracts.errors import (
    AuthoritativeSourceError,
    GovernanceStateError,
)
from arkali.kernel.contracts.results import (
    ACCEPTANCE_STOPPING,
    CheckResult,
    Finding,
    HonestState,
    Severity,
)

_SPEC = "docs/canonical/PHASE_GATE_CHECKER.md"
#: The requirement whose Phase column decides when the stronger profile is owed.
PROFILE_REQUIREMENT = "ARK-REQ-0111"


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


def _blocked(check_id: str, summary: str, detail: str = "") -> CheckResult:
    """Refused pending an authority decision. Not a failure of the phase itself."""
    return CheckResult(
        check_id=check_id,
        state=HonestState.BLOCKED,
        summary=summary,
        detail=detail,
        authoritative_source=_SPEC,
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
        self.protected_core = load_protected_core(repo_root)

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

    def check_discharge_integrity(self, report: PhaseReport) -> CheckResult:
        """C6: the discharged set must agree with the traceability record.

        Closes F-0024. C2 asks only whether every mandatory id appears in the
        report; it cannot ask whether the work happened. This asks whether the
        report's claim agrees with the phase's own traceability record, so an
        actor cannot ship one honest artifact and one false one and still pass.
        """
        try:
            record = TraceabilityRecord.load(self.repo_root, report.phase_id)
        except AuthoritativeSourceError as exc:
            return _fail("C6", "traceability record missing or unreadable", str(exc))
        expected = self._denominator(report.phase_id)
        refusal = check_claim_shape(expected, record)
        if refusal is not None:
            return _fail("C6", *refusal)
        violations = reconcile_discharge(
            report.ark_req_ids_closed, record, frozenset(self.register.all_ids())
        )
        if violations:
            return _fail(
                "C6", "phase report discharges requirements its traceability "
                "record does not support", f"violations={list(violations)}"
            )
        return _ok(
            "C6",
            f"all {len(report.ark_req_ids_closed)} discharged requirements are "
            f"claimed SATISFIED with named evidence",
            f"denominator={len(expected)} claims={len(record)} "
            f"non_satisfied_claims={[c.req_id for c in record.non_satisfied()]}",
        )

    def _denominator(self, phase_id: str) -> frozenset[str]:
        """The requirements the register assigns to this phase. The denominator.

        Read from `RequirementRegister`, never from the record under test: a
        record that defined its own denominator could always agree with itself.
        """
        return frozenset(r.req_id for r in self.register.for_phase(phase_id))

    def check_protected_core_profile(self, report: PhaseReport) -> CheckResult:
        """ARK-REQ-0111: a change touching Protected Core needs the stronger profile.

        The profile is derived from the changed paths, never declared by the
        report. Evidence is real execution records, never a boolean.
        """
        owing_phase = self.register.get(PROFILE_REQUIREMENT).owning_phase
        if not ExternalProviderResultRule.phase_owes(report.phase_id, owing_phase):
            return CheckResult(
                check_id="PROTECTED_CORE",
                state=HonestState.NOT_APPLICABLE,
                summary=(
                    f"phase {report.phase_id} predates {PROFILE_REQUIREMENT}, "
                    f"which the register assigns to phase {owing_phase}"
                ),
                detail="the obligation begins when the register says it does",
                authoritative_source=_SPEC,
            )
        verdict = evaluate_report_profile(self.repo_root, report, self.protected_core)
        selection = verdict.selection
        if not selection.requires_stronger_profile:
            return _ok(
                "PROTECTED_CORE",
                "no protected-core member touched; normal profile applies",
                selection.rationale,
            )
        if not verdict.complete:
            return _fail(
                "PROTECTED_CORE",
                "protected-core change lacks the stronger verification profile",
                verdict.render(),
            )
        return _ok("PROTECTED_CORE", verdict.render(), selection.rationale)

    def check_external_result_integrity(self, report: PhaseReport) -> CheckResult:
        """ARK-REQ-0219: no fabricated or simulated external-provider result.

        Thin by design. The subject and its authority live in
        `external_result_check`, which `checker.py`'s 400 logical-line budget
        required anyway; what belongs here is that the check is part of the one
        acceptance path, so no other route to a verdict can skip it.
        """
        passed, summary, detail = ExternalProviderResultRule.evaluate(
            self.repo_root, report, self.register
        )
        check = _ok if passed else _fail
        return check("EXTERNAL_RESULT", summary, detail)

    def check_rescoring_authority(self, report: PhaseReport) -> CheckResult:
        """GOV-001: superseding an accepted verdict needs explicit authorization.

        First-time acceptance is untouched — a phase with no acceptance record
        takes the NOT_APPLICABLE path and behaves exactly as before. Only a
        phase that already carries one must present an authorization bound to
        this exact evidence package.
        """
        status = self.state.phases.get(report.phase_id)
        if status is None or not status.is_accepted:
            return CheckResult(
                check_id="RESCORING",
                state=HonestState.NOT_APPLICABLE,
                summary=f"phase {report.phase_id} has no prior acceptance record",
                detail="first-time acceptance requires no re-scoring authorization",
                authoritative_source=_SPEC,
            )
        try:
            digest = evidence_package_digest(self.repo_root, report.phase_id)
        except AuthoritativeSourceError as exc:
            return _blocked(
                "RESCORING", "evidence package identity cannot be computed", str(exc)
            )
        authorization = find_authorization(self.repo_root, report.phase_id, digest)
        if authorization is None:
            return _blocked(
                "RESCORING",
                f"phase {report.phase_id} is already accepted; superseding it "
                "requires a recorded re-scoring authorization (GOV-001)",
                f"evidence_package={digest}",
            )
        return _ok(
            "RESCORING",
            f"superseding re-acceptance authorized by {authorization.identifier}",
            authorization.render(),
        )

    def check_migration_data_loss_risk(self) -> CheckResult:
        """ARK-REQ-0337: known data-loss risk blocks release.

        Thin by design, same shape as `check_external_result_integrity`: the
        detection lives in `migration_release_check.py`, kept separate so this
        module's own touched-context and line budgets stay clear of
        `kernel.persistence`.
        """
        passed, summary, detail = _evaluate_migration_data_loss_risk(self.repo_root)
        check = _ok if passed else _fail
        return check("DATA_LOSS_RISK", summary, detail)

    def check_open_findings(self) -> CheckResult:
        open_rows = self.state.open_stopping_findings
        if open_rows:
            return _fail("FINDINGS", "open BLOCKER/HIGH findings block acceptance",
                         f"rows={list(open_rows)}")
        return _ok("FINDINGS", "no open BLOCKER or HIGH finding")

    def check_prerequisites(self, phase_id: str) -> CheckResult:
        passed, summary, detail = _evaluate_prerequisites(self.state, phase_id)
        return (_ok if passed else _fail)("PREREQ", summary, detail)

    def check_human_gate(self, phase_id: str) -> CheckResult:
        """A human gate is never self-accepted: only a recorded decision counts."""
        required = _human_gate_for(self.state, phase_id)
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

    # -- orchestration --------------------------------------------------------

    def _run_checks(self, report: PhaseReport) -> list[CheckResult]:
        """Every check, in canonical order, with the gate details appended."""
        gate_result, gate_details = self.check_architecture_gates()
        checks = [
            self.check_report_completeness(report),
            self.check_register_linkage(report),
            self.check_recorded_execution(report),
            gate_result,
            self.check_honest_state_integrity(report),
            self.check_discharge_integrity(report),
            self.check_external_result_integrity(report),
            self.check_protected_core_profile(report),
            self.check_rescoring_authority(report),
            self.check_migration_data_loss_risk(),
            self.check_open_findings(),
            self.check_prerequisites(report.phase_id),
            self.check_human_gate(report.phase_id),
        ]
        checks.extend(gate_details)
        return checks

    @staticmethod
    def _blocking_human_gate(checks: list[CheckResult]) -> CheckResult | None:
        return next(
            (c for c in checks if c.check_id == "HUMAN_GATE"
             and c.state is HonestState.BLOCKED),
            None,
        )

    @staticmethod
    def _is_blocked(
        checks: list[CheckResult], findings: tuple[Finding, ...]
    ) -> bool:
        failing = any(c.state is HonestState.FAIL for c in checks)
        stopping = any(f.severity in ACCEPTANCE_STOPPING for f in findings)
        return failing or stopping

    @staticmethod
    def _blocking_reason(
        checks: list[CheckResult], findings: tuple[Finding, ...]
    ) -> str:
        failing = [c.check_id for c in checks if c.state is HonestState.FAIL]
        if failing:
            return f"failing checks: {failing}"
        stopping = [f for f in findings if f.severity in ACCEPTANCE_STOPPING]
        return f"stopping findings: {len(stopping)}"

    def _decide(
        self, checks: list[CheckResult], findings: tuple[Finding, ...]
    ) -> tuple[Verdict, bool, str, CheckResult | None]:
        """Verdict, progression, reason and the blocking gate, if any.

        Order is load-bearing: a failing check blocks even when a human gate is
        also outstanding, so a blocked phase is never reported as merely
        awaiting a signature.
        """
        human = self._blocking_human_gate(checks)
        if self._is_blocked(checks, findings):
            return (
                Verdict.PHASE_BLOCKED,
                False,
                self._blocking_reason(checks, findings),
                human,
            )
        rescoring = next(
            (c for c in checks if c.check_id == "RESCORING"
             and c.state is HonestState.BLOCKED),
            None,
        )
        if rescoring is not None:
            return (
                Verdict.AWAITING_RESCORING_AUTHORITY,
                False,
                rescoring.summary,
                human,
            )
        if human is not None:
            return Verdict.AWAITING_HUMAN_GATE, False, human.summary, human
        return Verdict.PHASE_ACCEPTED_BY_MACHINE, True, "", human

    def evaluate(
        self, report: PhaseReport, requested_next_phase: str | None = None
    ) -> GateVerdict:
        """Run every check and produce a deterministic verdict."""
        if report.phase_id not in self.state.phases:
            raise GovernanceStateError(
                f"phase {report.phase_id!r} has no governance status row"
            )
        checks = self._run_checks(report)
        findings = tuple(f for c in checks for f in c.findings)
        verdict, permitted, reason, human = self._decide(checks, findings)
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
