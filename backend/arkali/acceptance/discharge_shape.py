"""Whether a traceability record's SHAPE is permitted for its phase (F-0040).

Owner: acceptance.engine (Protected Core).

WHY THIS IS A SEPARATE MODULE. `checker.py` reached the 400 logical-line budget
when this judgement was added to it, and ADR-0008 makes decomposition the answer
rather than an exception. It also follows the pattern the acceptance engine
already uses - `findings.py`, `phase_report.py`, `requirement_claim.py`,
`rescoring_authorization.py`, `verification_profile.py` and
`protected_core_check.py` each own one concern and the checker orchestrates.

WHAT THIS DECIDES, AND WHAT IT DOES NOT. It decides only whether a phase is
entitled to claim nothing, or to claim something. Whether a *discharge* is
supported remains `reconcile_discharge`'s question and is untouched.

THE DENOMINATOR IS THE AUTHORITY. A phase's requirement set comes from
`REQUIREMENT_REGISTER.md` and is passed in already resolved. It is never read
from the record under test: a record that defined its own denominator could
always agree with itself.

WHY EMPTINESS IS A QUESTION AT ALL. Four canonical phases - **8, 15, 33 and
34** - are assigned no registered requirement. Before F-0040 the loader refused
every empty record outright, so for those phases the only truthful record was
rejected while any non-empty record would have asserted a claim the phase does
not own. The blanket rule also protected nothing: against an empty record,
`reconcile_discharge` already refuses every non-empty discharged set.
"""

from __future__ import annotations

from arkali.acceptance.requirement_claim import TraceabilityRecord

#: Returned as (summary, detail) when the shape is refused; None when permitted.
ShapeRefusal = tuple[str, str]


def check_claim_shape(
    expected: frozenset[str], record: TraceabilityRecord
) -> ShapeRefusal | None:
    """Refuse a record whose shape contradicts its phase's denominator.

    Both directions fail closed:

    * **claims nothing while the register assigns requirements** - the phase
      owes claims and made none, which is the pre-F-0040 protection preserved
      exactly, now stated against the denominator instead of absolutely;
    * **claims something while the denominator is empty** - STRICTLY STRONGER
      than anything that existed before. A phase owning no requirement may not
      assert a position on another phase's requirement, so a synthetic or
      foreign-phase claim can no longer be manufactured to satisfy an invariant.

    Returns None when the shape is permitted, including the `E = C = ∅` case a
    zero-denominator phase requires.
    """
    if not record and expected:
        return (
            "traceability record claims nothing while the register assigns "
            "this phase requirements",
            f"denominator={sorted(expected)} claims=0",
        )
    if record and not expected:
        return (
            "traceability record claims requirements the register does not "
            "assign to this phase, whose denominator is empty",
            f"denominator=[] claims={list(record.ids())}",
        )
    return None
