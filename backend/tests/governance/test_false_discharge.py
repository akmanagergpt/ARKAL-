"""Negative controls for the false-discharge guard (closes F-0024).

Phase 4 shipped a traceability map recording `ARK-REQ-0111` as DEFERRED and a
phase report listing the same id among the requirements it discharged. C2 reads
only the report, so it passed. The honest artifact and the false one were written
by the same actor in the same commit and nothing compared them.

These controls prove the reconciliation rejects each way the two artifacts can
disagree, and — equally important — that a genuinely satisfied requirement still
passes. A guard that rejected everything would be no more use than one that
rejected nothing.

All fixtures are in-memory. No repository artifact is written.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from arkali.acceptance.discharge_shape import check_claim_shape
from arkali.acceptance.requirement_claim import (
    ClaimState,
    RequirementClaim,
    TraceabilityRecord,
    reconcile_discharge,
)
from arkali.kernel.contracts.errors import AuthoritativeSourceError

REPO = pathlib.Path(__file__).resolve().parents[3]
REGISTER_IDS = frozenset({"ARK-REQ-0001", "ARK-REQ-0002", "ARK-REQ-0111"})


def record_of(*claims: RequirementClaim) -> TraceabilityRecord:
    return TraceabilityRecord("4", {c.req_id: c for c in claims}, "in-memory")


def satisfied(req_id: str) -> RequirementClaim:
    return RequirementClaim(
        req_id=req_id,
        state=ClaimState.SATISFIED,
        implementation="module.py",
        evidence="test_module.py",
    )


class TestGenuineDischargePasses:
    def test_a_satisfied_backed_claim_is_accepted(self) -> None:
        """Proves the rejections below are specific, not blanket refusal."""
        record = record_of(satisfied("ARK-REQ-0001"))
        assert reconcile_discharge(("ARK-REQ-0001",), record, REGISTER_IDS) == ()

    def test_several_satisfied_claims_are_accepted(self) -> None:
        record = record_of(satisfied("ARK-REQ-0001"), satisfied("ARK-REQ-0002"))
        violations = reconcile_discharge(
            ("ARK-REQ-0001", "ARK-REQ-0002"), record, REGISTER_IDS
        )
        assert violations == ()

    def test_a_non_satisfied_claim_not_discharged_is_fine(self) -> None:
        """Recording a requirement as DEFERRED is honest, so long as it is not claimed."""
        record = record_of(
            satisfied("ARK-REQ-0001"),
            RequirementClaim(req_id="ARK-REQ-0111", state=ClaimState.DEFERRED),
        )
        assert reconcile_discharge(("ARK-REQ-0001",), record, REGISTER_IDS) == ()


class TestFalseDischargeIsRejected:
    @pytest.mark.parametrize(
        "state",
        [
            ClaimState.DEFERRED,
            ClaimState.NOT_TESTED,
            ClaimState.NOT_CONFIGURED,
            ClaimState.UNSUPPORTED,
            ClaimState.BLOCKED,
            ClaimState.FAIL,
        ],
    )
    def test_every_non_satisfied_state_is_refused_when_discharged(
        self, state: ClaimState
    ) -> None:
        """The F-0024 shape, generalised across every non-satisfied state."""
        record = record_of(RequirementClaim(req_id="ARK-REQ-0111", state=state))
        violations = reconcile_discharge(("ARK-REQ-0111",), record, REGISTER_IDS)
        assert len(violations) == 1
        assert state.value in violations[0]

    def test_the_exact_f_0024_shape_is_refused(self) -> None:
        """Traceability says DEFERRED; the report discharges it anyway."""
        record = record_of(
            RequirementClaim(
                req_id="ARK-REQ-0111",
                state=ClaimState.DEFERRED,
                note="stronger verification profile is a later phase",
            )
        )
        violations = reconcile_discharge(("ARK-REQ-0111",), record, REGISTER_IDS)
        assert violations and "DEFERRED" in violations[0]

    def test_a_requirement_absent_from_traceability_is_refused(self) -> None:
        record = record_of(satisfied("ARK-REQ-0001"))
        violations = reconcile_discharge(("ARK-REQ-0002",), record, REGISTER_IDS)
        assert violations and "no traceability claim" in violations[0]

    def test_a_satisfied_claim_without_evidence_is_refused(self) -> None:
        record = record_of(
            RequirementClaim(
                req_id="ARK-REQ-0001",
                state=ClaimState.SATISFIED,
                implementation="module.py",
                evidence="",
            )
        )
        violations = reconcile_discharge(("ARK-REQ-0001",), record, REGISTER_IDS)
        assert violations and "without naming an implementation" in violations[0]

    def test_a_satisfied_claim_without_an_implementation_is_refused(self) -> None:
        record = record_of(
            RequirementClaim(
                req_id="ARK-REQ-0001",
                state=ClaimState.SATISFIED,
                implementation="",
                evidence="test.py",
            )
        )
        assert reconcile_discharge(("ARK-REQ-0001",), record, REGISTER_IDS)

    def test_an_id_absent_from_the_register_is_refused(self) -> None:
        """The register is the sole denominator; a wrong id cannot be discharged."""
        record = record_of(satisfied("ARK-REQ-9999"))
        violations = reconcile_discharge(("ARK-REQ-9999",), record, REGISTER_IDS)
        assert violations and "absent from the register" in violations[0]

    def test_every_violation_is_reported_not_just_the_first(self) -> None:
        record = record_of(
            RequirementClaim(req_id="ARK-REQ-0001", state=ClaimState.FAIL),
            RequirementClaim(req_id="ARK-REQ-0111", state=ClaimState.DEFERRED),
        )
        violations = reconcile_discharge(
            ("ARK-REQ-0001", "ARK-REQ-0002", "ARK-REQ-0111"), record, REGISTER_IDS
        )
        assert len(violations) == 3


class TestRecordLoadingFailsClosed:
    def test_a_missing_record_is_refused(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(AuthoritativeSourceError):
            TraceabilityRecord.load(tmp_path, "4")

    def test_an_unparseable_record_is_refused(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "docs" / "acceptance"
        target.mkdir(parents=True)
        (target / "phase_4_traceability.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(AuthoritativeSourceError):
            TraceabilityRecord.load(tmp_path, "4")

    def test_an_absent_claims_list_is_still_refused(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A MISSING or non-list `claims` key is malformed and stays refused.

        REPLACES `test_an_empty_record_is_refused` (F-0040). That control
        asserted the loader refuses `claims: []` for phase "4". It was verified
        firing for exactly the intended reason before being touched: after the
        repair it reported DID NOT RAISE, because the judgement moved to check
        C6 where the register is available — the loader had been refusing an
        empty list for **every** phase without consulting any denominator, and
        four canonical phases (8, 15, 33, 34) own no requirement at all, so for
        them the only truthful record was the one being rejected.

        What the loader still owns is well-formedness, and that is unchanged:
        an absent or non-list `claims` key is malformed and refused here.
        Whether an *empty but well-formed* list is permitted is a question about
        the phase, not about the file, and is proven in
        `TestZeroDenominatorShape`.
        """
        target = tmp_path / "docs" / "acceptance"
        target.mkdir(parents=True)
        for payload in ({"phase_id": "4"}, {"phase_id": "4", "claims": {}},
                        {"phase_id": "4", "claims": "none"}):
            (target / "phase_4_traceability.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
            with pytest.raises(AuthoritativeSourceError):
                TraceabilityRecord.load(tmp_path, "4")

    def test_a_well_formed_empty_list_now_loads(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The loader no longer judges emptiness; it only parses.

        Non-vacuity for the control above: an empty list really does reach the
        caller now, so the refusals there are about malformedness and not about
        emptiness by accident.
        """
        target = tmp_path / "docs" / "acceptance"
        target.mkdir(parents=True)
        (target / "phase_4_traceability.json").write_text(
            json.dumps({"phase_id": "4", "claims": []}), encoding="utf-8"
        )
        record = TraceabilityRecord.load(tmp_path, "4")
        assert len(record) == 0 and record.ids() == ()

    def test_a_duplicate_claim_is_refused(self, tmp_path: pathlib.Path) -> None:
        """Two conflicting statuses for one requirement cannot both stand."""
        target = tmp_path / "docs" / "acceptance"
        target.mkdir(parents=True)
        (target / "phase_4_traceability.json").write_text(
            json.dumps(
                {
                    "phase_id": "4",
                    "claims": [
                        {"req_id": "ARK-REQ-0001", "state": "SATISFIED",
                         "implementation": "m.py", "evidence": "t.py"},
                        {"req_id": "ARK-REQ-0001", "state": "FAIL"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(AuthoritativeSourceError):
            TraceabilityRecord.load(tmp_path, "4")

    def test_an_unknown_state_is_refused(self, tmp_path: pathlib.Path) -> None:
        target = tmp_path / "docs" / "acceptance"
        target.mkdir(parents=True)
        (target / "phase_4_traceability.json").write_text(
            json.dumps(
                {"phase_id": "4",
                 "claims": [{"req_id": "ARK-REQ-0001", "state": "PROBABLY_FINE"}]}
            ),
            encoding="utf-8",
        )
        with pytest.raises(Exception):
            TraceabilityRecord.load(tmp_path, "4")



class TestLiveRecordIsHonest:
    def test_the_phase_4_record_covers_every_mandatory_requirement(self) -> None:
        from arkali.control.specification.register_parser import RequirementRegister

        register = RequirementRegister.load(REPO)
        mandatory = {r.req_id for r in register.for_phase("4") if r.is_mandatory}
        record = TraceabilityRecord.load(REPO, "4")
        assert mandatory, "no Phase 4 mandatory requirements; control is vacuous"
        assert mandatory <= set(record.ids()), sorted(mandatory - set(record.ids()))

    def test_every_satisfied_live_claim_names_evidence(self) -> None:
        record = TraceabilityRecord.load(REPO, "4")
        unbacked = [c.req_id for c in
                    (record.get(i) for i in record.ids())
                    if c is not None and not c.is_backed]
        assert unbacked == []
