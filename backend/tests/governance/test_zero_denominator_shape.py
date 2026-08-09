"""Zero-denominator phase shape controls for check C6 (closes F-0040).

Second module over the false-discharge corpus because `module <= 400 logical
lines` is a real architecture budget and ADR-0008 makes decomposition the answer
rather than an exception. The seam is a real one: `test_false_discharge.py` owns
the F-0024 question — *may this discharge be trusted?* — and this module owns the
F-0040 question — *is this phase entitled to claim what it claims?*

THE SUBJECT IS DERIVED, NEVER NAMED. The zero-denominator phases are asked of
`RequirementRegister`, so if governance ever assigns a requirement to one of
them these controls follow instead of expiring — the F-0029/F-0031 lesson.
"""

from __future__ import annotations

import pathlib

from arkali.acceptance.discharge_shape import check_claim_shape
from arkali.acceptance.requirement_claim import (
    ClaimState,
    RequirementClaim,
    TraceabilityRecord,
    reconcile_discharge,
)

REPO = pathlib.Path(__file__).resolve().parents[3]


def satisfied(req_id: str) -> RequirementClaim:
    return RequirementClaim(
        req_id=req_id,
        state=ClaimState.SATISFIED,
        implementation="module.py",
        evidence="test_module.py",
    )


def report_for(phase_id: str, discharged: tuple[str, ...] = ()):  # noqa: ANN201
    """The smallest well-formed C-17 report. Only C6's inputs vary.

    C6 reads `phase_id` and `ark_req_ids_closed`; every other field is filled
    only because `PhaseReport` requires it, so nothing here can influence the
    check under test.
    """
    from arkali.acceptance.phase_report import PhaseReport, TestExecutionRecord
    from arkali.kernel.contracts.results import HonestState

    return PhaseReport(
        phase_id=phase_id,
        objective="fixture",
        ark_req_ids_closed=discharged,
        files_created=("fixture.py",),
        files_modified=(),
        public_contracts=(),
        migrations=(),
        state_machine_capability_changes="none",
        tests_executed=(TestExecutionRecord(command="pytest", exit_code=0),),
        architecture_checks="none",
        duplicate_shadow_check="none",
        security_findings="none",
        fake_success_scan="none",
        evidence_created=("EV-0000",),
        limitations="none",
        blockers="none",
        next_exact_action="none",
        status=HonestState.PASS,
    )


def satisfied(req_id: str) -> RequirementClaim:
    return RequirementClaim(
        req_id=req_id,
        state=ClaimState.SATISFIED,
        implementation="module.py",
        evidence="test_module.py::TestThing",
    )


class TestZeroDenominatorShape:
    """C6's claim-shape judgement, derived from the register (closes F-0040).

    The subject is DERIVED, never named: the zero-denominator phases are asked
    of `RequirementRegister`, so if governance ever assigns a requirement to one
    of them these controls follow rather than expire — the F-0029/F-0031 lesson.
    """

    @staticmethod
    def _register():  # noqa: ANN205
        from arkali.control.specification.register_parser import RequirementRegister

        return RequirementRegister.load(REPO)

    @classmethod
    def _phases(cls) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(phases owning nothing, phases owning something), from the register."""
        register = cls._register()
        candidates = ["0A", "0B", "9B", "22B"] + [str(n) for n in range(0, 38)]
        empty = tuple(p for p in candidates if not register.for_phase(p))
        nonempty = tuple(p for p in candidates if register.for_phase(p))
        return empty, nonempty

    def _denominator(self, phase_id: str) -> frozenset[str]:
        return frozenset(r.req_id for r in self._register().for_phase(phase_id))

    def test_the_register_really_declares_zero_denominator_phases(self) -> None:
        """Non-vacuity: without one of these, every control below is empty."""
        empty, nonempty = self._phases()
        assert empty, (
            "no canonical phase owns zero requirements; F-0040's premise is "
            "gone and these controls must be re-derived, not deleted"
        )
        assert nonempty, "no phase owns any requirement; the register is broken"

    def test_empty_claims_are_accepted_when_the_denominator_is_empty(
        self,
    ) -> None:
        """MUTATION 1. `E = ∅`, `C = ∅` is the truthful shape and must pass."""
        empty, _ = self._phases()
        for phase in empty:
            record = TraceabilityRecord(phase, {}, "in-memory")
            assert check_claim_shape(self._denominator(phase), record) is None, (
                f"phase {phase} owns nothing yet an empty record was refused"
            )

    def test_empty_claims_are_refused_when_the_denominator_is_not(self) -> None:
        """MUTATION 2. The pre-F-0040 protection, preserved exactly."""
        _, nonempty = self._phases()
        for phase in nonempty:
            record = TraceabilityRecord(phase, {}, "in-memory")
            refusal = check_claim_shape(self._denominator(phase), record)
            assert refusal is not None, (
                f"phase {phase} owns requirements but claimed nothing and was "
                "not refused"
            )
            assert "claims nothing" in refusal[0]

    def test_any_claim_is_refused_when_the_denominator_is_empty(self) -> None:
        """MUTATION 3 and 5. STRICTLY STRONGER than anything before F-0040.

        A phase owning no requirement may not assert a position on another
        phase's requirement, so neither a synthetic claim nor a foreign-phase
        claim can be manufactured to satisfy an invariant. Both a SATISFIED and
        a non-SATISFIED claim are refused: the state is irrelevant, the phase's
        entitlement is not.
        """
        empty, _ = self._phases()
        register = self._register()
        foreign = sorted(register.all_ids())[0]
        for phase in empty:
            for claim in (
                RequirementClaim(req_id=foreign, state=ClaimState.DEFERRED,
                                 note="not this phase's to discharge"),
                satisfied(foreign),
                RequirementClaim(req_id="C-21", state=ClaimState.SATISFIED,
                                 implementation="worker.py", evidence="t.py"),
            ):
                record = TraceabilityRecord(phase, {claim.req_id: claim},
                                            "in-memory")
                refusal = check_claim_shape(self._denominator(phase), record)
                assert refusal is not None, (
                    f"phase {phase} owns nothing but claim {claim.req_id} on "
                    f"state {claim.state.value} was permitted"
                )
                assert "does not assign" in refusal[0]

    def test_a_false_discharge_is_still_refused_with_an_empty_record(
        self,
    ) -> None:
        """MUTATION 4. `reconcile_discharge` semantics are unchanged.

        The repair must not open a discharge path. An empty record that
        nevertheless discharges something is refused exactly as before, and the
        refusal names the missing claim rather than the empty shape.
        """
        empty, _ = self._phases()
        register = self._register()
        ids = frozenset(register.all_ids())
        real = sorted(ids)[0]
        for phase in empty:
            record = TraceabilityRecord(phase, {}, "in-memory")
            violations = reconcile_discharge((real,), record, ids)
            assert violations and "no traceability claim" in violations[0]
            unknown = reconcile_discharge(("ARK-REQ-9999",), record, ids)
            assert unknown and "absent from the register" in unknown[0]

    def test_a_zero_denominator_phase_discharging_nothing_is_clean(self) -> None:
        """The composed result: shape permitted AND no discharge violation."""
        empty, _ = self._phases()
        ids = frozenset(self._register().all_ids())
        for phase in empty:
            record = TraceabilityRecord(phase, {}, "in-memory")
            assert check_claim_shape(self._denominator(phase), record) is None
            assert reconcile_discharge((), record, ids) == ()

    def test_c6_itself_enforces_the_shape_rule_end_to_end(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The WIRING, not just the function (found by mutation).

        Every control above calls `check_claim_shape` directly, so all of them
        still passed when `check_discharge_integrity` was mutated to ignore its
        result — the F-0017 shape: a control that passes for a reason unrelated
        to the property it claims to protect. This drives the real
        `PhaseGateChecker` over a real copy of the canonical documents, so a C6
        that stops consulting the shape rule fails here.
        """
        import json
        import shutil

        from arkali.acceptance.checker import PhaseGateChecker
        from arkali.kernel.contracts.results import HonestState

        shutil.copytree(REPO / "docs", tmp_path / "docs")
        checker = PhaseGateChecker(tmp_path)
        empty, nonempty = self._phases()
        zero_phase = empty[0]
        real_phase = next(
            p for p in nonempty
            if (REPO / "docs/acceptance" / f"phase_{p}_traceability.json").is_file()
        )
        foreign = sorted(checker.register.all_ids())[0]

        def write(phase: str, claims: list[dict[str, object]]) -> None:
            (tmp_path / "docs/acceptance" / f"phase_{phase}_traceability.json"
             ).write_text(json.dumps({"phase_id": phase, "claims": claims}),
                          encoding="utf-8")

        def c6(phase: str, discharged: tuple[str, ...] = ()):  # noqa: ANN202
            return checker.check_discharge_integrity(
                report_for(phase, discharged)
            )

        # A zero-denominator phase claiming nothing: C6 must PASS.
        write(zero_phase, [])
        assert c6(zero_phase).state is HonestState.PASS

        # The same phase asserting a foreign claim: C6 must FAIL.
        write(zero_phase, [{"req_id": foreign, "state": "DEFERRED"}])
        refused = c6(zero_phase)
        assert refused.state is HonestState.FAIL
        assert "does not assign" in refused.summary

        # A phase that owns requirements but claims nothing: C6 must FAIL.
        write(real_phase, [])
        refused = c6(real_phase)
        assert refused.state is HonestState.FAIL
        assert "claims nothing" in refused.summary

    def test_the_live_accepted_phases_still_satisfy_the_shape_rule(self) -> None:
        """No accepted phase's record changes meaning under the repair."""
        _, nonempty = self._phases()
        checked = 0
        for phase in nonempty:
            path = REPO / "docs/acceptance" / f"phase_{phase}_traceability.json"
            if not path.is_file():
                continue
            record = TraceabilityRecord.load(REPO, phase)
            checked += 1
            assert check_claim_shape(self._denominator(phase), record) is None, (
                f"accepted phase {phase} would now be refused"
            )
        assert checked >= 5, f"only {checked} live records checked"

