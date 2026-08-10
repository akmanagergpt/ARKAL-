"""What Phase 8 owes, and what it must not claim — derived from the register.

A phase can be dishonest in two directions: by failing to discharge what it
owns, and by claiming what it does not. Phase 8 is the repository's first
ZERO-DENOMINATOR phase, so the second risk is the live one — there is no
requirement to discharge, and therefore nothing to point at except a claim that
would have to be manufactured.

Every subject here is read from `REQUIREMENT_REGISTER.md` and
`CONTRACT_INVENTORY.md` at call time. Nothing is transcribed, so if governance
ever assigns Phase 8 a requirement these controls change their answer instead of
going stale.
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Final

import pytest

from arkali.acceptance.discharge_shape import check_claim_shape
from arkali.acceptance.requirement_claim import TraceabilityRecord
from arkali.control.specification.register_parser import RequirementRegister

REPO: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parents[3]
PHASE: Final[str] = "8"
CONTRACT: Final[str] = "C-21"
#: Failure-domain isolation. Named here only to prove it is NOT Phase 8's.
FAILURE_DOMAIN_REQUIREMENT: Final[str] = "ARK-REQ-0354"

TRACEABILITY = REPO / "docs" / "acceptance" / f"phase_{PHASE}_traceability.json"
REPORT = REPO / "docs" / "acceptance" / f"phase_{PHASE}_report.json"
INVENTORY = REPO / "docs" / "canonical" / "CONTRACT_INVENTORY.md"


@pytest.fixture(scope="module")
def register() -> RequirementRegister:
    return RequirementRegister.load(REPO)


class TestPhaseEightOwesNoRequirement:
    """The denominator is zero, and that is governed data, not an opinion."""

    def test_the_register_assigns_this_phase_nothing(
        self, register: RequirementRegister
    ) -> None:
        owned = register.for_phase(PHASE)
        assert owned == (), (
            f"the register now assigns Phase {PHASE} {[r.req_id for r in owned]}; "
            "the zero-denominator reasoning below no longer holds and the "
            "traceability record must be rebuilt"
        )

    def test_the_schedulers_only_registered_requirement_belongs_to_a_later_phase(
        self, register: RequirementRegister
    ) -> None:
        """`ARK-REQ-0354` is Phase 31. Phase 8 may not discharge it."""
        record = register.get(FAILURE_DOMAIN_REQUIREMENT)
        assert record.owning_component == "execution.scheduler"
        assert record.owning_phase != PHASE
        assert record.owning_phase == "31", (
            f"{FAILURE_DOMAIN_REQUIREMENT} moved to phase {record.owning_phase}"
        )

    def test_no_requirement_anywhere_names_the_contract_this_phase_delivers(
        self, register: RequirementRegister
    ) -> None:
        """C-21 has no `ARK-REQ` anchor, so none may be fabricated for it."""
        for req_id in register.all_ids():
            statement = register.get(req_id).statement
            assert CONTRACT not in statement, (
                f"{req_id} names {CONTRACT}; the contract would then have an "
                "anchor and this phase's evidence model would change"
            )

    def test_the_contract_inventory_assigns_the_contract_to_this_phase(self) -> None:
        """Anti-vacuity: the phase does own something — a contract, not a requirement."""
        rows = [
            line for line in INVENTORY.read_text(encoding="utf-8").splitlines()
            if re.match(rf"^\|\s*\**{CONTRACT}\**\s*\|", line)
        ]
        assert len(rows) == 1, f"expected exactly one {CONTRACT} row, got {len(rows)}"
        cells = [cell.strip() for cell in rows[0].split("|")]
        assert cells[-2] == PHASE, f"{CONTRACT} is not assigned to phase {PHASE}"
        assert "INT" in cells, f"{CONTRACT} is no longer an INT contract"


class TestTheOnlyTruthfulRecordShape:
    """An empty record is legal here, and a non-empty one is not."""

    def test_the_recorded_traceability_is_empty_and_permitted(
        self, register: RequirementRegister
    ) -> None:
        record = TraceabilityRecord.load(REPO, PHASE)
        expected = frozenset(r.req_id for r in register.for_phase(PHASE))
        assert len(record) == 0, f"the record claims {record.ids()}"
        assert check_claim_shape(expected, record) is None, (
            "C6 refuses the shape of the record this phase recorded"
        )

    def test_the_report_discharges_nothing(self) -> None:
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        assert raw["ark_req_ids_closed"] == [], (
            f"the report discharges {raw['ark_req_ids_closed']} against an empty "
            "denominator"
        )

    def test_a_manufactured_claim_would_be_refused(
        self, register: RequirementRegister
    ) -> None:
        """The strictly stronger half of F-0040's repair, proven live.

        A zero-denominator phase may not assert a position on another phase's
        requirement, so no claim can be invented to make the record look busy.
        """
        expected = frozenset(register.for_phase(PHASE))
        foreign = TraceabilityRecord(
            PHASE,
            {
                FAILURE_DOMAIN_REQUIREMENT: _claim(FAILURE_DOMAIN_REQUIREMENT),
            },
            str(TRACEABILITY),
        )
        refusal = check_claim_shape(frozenset(expected), foreign)
        assert refusal is not None, (
            "a foreign-phase claim was accepted against an empty denominator"
        )
        assert "denominator is empty" in refusal[0]

    def test_the_contract_id_cannot_be_smuggled_in_as_a_requirement(self) -> None:
        """`C-21` is not an `ARK-REQ`, and the register is the sole denominator."""
        register = RequirementRegister.load(REPO)
        with pytest.raises(Exception):
            register.get(CONTRACT)


def _claim(req_id: str) -> object:
    from arkali.acceptance.requirement_claim import ClaimState, RequirementClaim

    return RequirementClaim(
        req_id=req_id,
        state=ClaimState.SATISFIED,
        implementation="manufactured",
        evidence="manufactured",
    )
