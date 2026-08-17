"""PREREQ and HUMAN_GATE check logic, split from `checker.py`.

Owner: `acceptance.engine` (Protected Core).

ADR-0008 decomposition: `checker.py` hit its module logical-line budget when
Phase 20's `check_migration_data_loss_risk` was added. These two checks moved
here - `checker.py` keeps the public `check_prerequisites`/`check_human_gate`
methods and now delegates to the functions below rather than computing inline.

HUMAN_GATE_SCOPE_GAP REMEDIATION. `_evaluate_human_gate` no longer asks "has
this gate number ever been granted anywhere" (`state.accepted_human_gates`,
still used, but only for the two canon-singleton gates - see
`human_gate_authorization.SINGLETON_GATES`). For every other gate it asks "is
there a recorded grant naming this exact gate, this exact phase, and this
exact evidence-package digest" via `human_gate_authorization._find_phase_gate_
grant`, the same digest-binding discipline `rescoring_authorization.py`
already established for GOV-001. A grant for phase 19 can no longer satisfy a
future check of the identical gate number for phase 21.
"""

from __future__ import annotations

import pathlib

from arkali.acceptance.governance_state import GovernanceState
from arkali.acceptance.human_gate_authorization import (
    SINGLETON_GATES,
    _find_phase_gate_grant,
)
from arkali.acceptance.rescoring_authorization import evidence_package_digest


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


def _evaluate_human_gate(
    repo_root: pathlib.Path, state: GovernanceState, phase_id: str, gate_id: str,
) -> tuple[bool, str]:
    """(satisfied, summary) once `_human_gate_for` has already named a gate.

    `gate_id in SINGLETON_GATES` is the only case where a bare gate-ID-only
    record (`state.accepted_human_gates`, unchanged legacy parsing) may
    satisfy the check - HUMAN_GATE_1 and HUMAN_GATE_7 are project-singular by
    their own canonical definition (see `human_gate_authorization.py`).
    Every other gate requires a `_PhaseGateGrant` scoped to this exact phase
    and this exact evidence-package digest; a grant recorded for a different
    phase, or the same phase under a since-changed evidence package, does not
    satisfy it.

    Raises `AuthoritativeSourceError` (propagated, not caught here) when the
    evidence package cannot be located - the caller already imports that
    type for its own RESCORING check, so catching it there instead of adding
    a second `kernel.contracts.errors` importer keeps this module's own
    fan-in contribution at zero.
    """
    if gate_id in SINGLETON_GATES:
        if gate_id in state.accepted_human_gates:
            return True, f"{gate_id} has a recorded acceptance (project-singular gate)"
        return False, f"{gate_id} required and not recorded"
    digest = evidence_package_digest(repo_root, phase_id)
    grant = _find_phase_gate_grant(repo_root, gate_id, phase_id, digest)
    if grant is None:
        return (
            False,
            f"{gate_id} required and not recorded for this exact evidence package "
            f"(digest={digest})",
        )
    return (
        True,
        f"{gate_id} has a recorded acceptance scoped to this exact evidence "
        f"package ({grant.identifier})",
    )
