"""PREREQ and HUMAN_GATE check logic, split from `checker.py`.

Owner: `acceptance.engine` (Protected Core).

ADR-0008 decomposition: `checker.py` hit its module logical-line budget when
Phase 20's `check_migration_data_loss_risk` was added. These two checks moved
here unchanged in behaviour - `checker.py` keeps the public
`check_prerequisites`/`check_human_gate` methods and now delegates to the
functions below rather than computing inline.
"""

from __future__ import annotations

from arkali.acceptance.governance_state import GovernanceState


def _evaluate_prerequisites(state: GovernanceState, phase_id: str) -> tuple[bool, str, str]:
    """(passed, summary, detail) for check PREREQ."""
    prereqs = state.prerequisites_of(phase_id)
    unmet = [
        dep for dep in prereqs
        if dep in state.phases and not state.phase(dep).is_accepted
    ]
    unknown = [dep for dep in prereqs if dep not in state.phases]
    if unknown:
        return False, "prerequisite phase has no status row", f"unknown={unknown}"
    if unmet:
        return False, "prerequisite phase is not accepted", f"unmet={unmet}"
    return True, f"all {len(prereqs)} prerequisites accepted", ""


def _human_gate_for(state: GovernanceState, phase_id: str) -> str | None:
    """Which gate this phase carries, read from authoritative state.

    NO SHADOW MODEL: the mapping is parsed from the Gate column of
    IMPLEMENTATION_DEPENDENCY_MATRIX.md. Phase 0A and 0B form one acceptance
    package, so 0A and 0 inherit the gate the matrix records against 0B.
    """
    direct = state.phase_gates.get(phase_id)
    if direct:
        return direct
    if phase_id in ("0", "0A"):
        return state.phase_gates.get("0B")
    return None
