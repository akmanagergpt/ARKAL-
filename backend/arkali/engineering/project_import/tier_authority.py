"""TRUST tier assignment for imported projects (ARK-REQ-0161).

Owner: engineering.import.

WHY THIS FUNCTION TAKES NO TIER PARAMETER. MS §Trust-Tiered Isolation names
`TRUST-3` for "imported/untrusted projects" unconditionally — every import,
without exception. A function that accepted a tier argument would let a
caller choose one, which is precisely what ARK-REQ-0161's "cannot be
reassigned by an implementing actor" forbids. `assign_tier` has exactly one
possible return shape, enforced twice: once here (no parameter to vary it)
and once more in `TierAssignment` itself (`Literal["TRUST-3"]` — the type
cannot hold anything else even if this function's own logic were bypassed).

A REAL, COMPLETED INSPECTION IS A PRECONDITION, NOT A FORMALITY.
`import_project_state_machine.py`'s `tier_assignment_guard` already refuses
the `STATICALLY_INSPECTED -> TIER_ASSIGNED` transition unless an assigner
outside `implementing_actor` is named; this function is that assigner, and it
additionally refuses to run at all against a report claiming inspection
never completed, which cannot occur structurally (`executed` is always
`False` by type) but is asserted here anyway as the single place the
precondition is stated for a human reader.
"""

from __future__ import annotations

from arkali.engineering.project_import.contracts import (
    FIXED_ASSIGNER,
    FIXED_TIER,
    StaticInspectionReport,
    TierAssignment,
)


def assign_tier(inspection: StaticInspectionReport) -> TierAssignment:
    """The only way to obtain a `TierAssignment`. Always TRUST-3, always
    assigned by the fixed tier authority, always bound to `inspection`."""
    return TierAssignment(inspection_ref=inspection.source_address)


__all__ = ["assign_tier", "FIXED_TIER", "FIXED_ASSIGNER"]
