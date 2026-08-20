"""C-31 real `HUMAN_GATE_7`-gated `SIGNED_READY -> RELEASED` transition.
Closes "bypassed acceptance" / "bypassed release policy" (ARK-REQ-0007).

Owner: `lifecycle.release` (Protected Core).

THE GAP THIS CLOSES. `release_state_machine.release_guard` requires
`human_gate_7_recorded` and `evidence_complete` in its context, but nothing
before this package supplied either fact from a real source - a caller
could call `instance.apply("RELEASED", {"human_gate_7_recorded": True,
"evidence_complete": True})` directly and the guard would believe it. This
module is the sole real supplier of both facts.

`HUMAN_GATE_7` IS A SINGLETON, NOT A SCOPED GATE - PROVEN, NOT ASSUMED.
`CLAUDE_ARKALI_GENESIS_V2_BUILD_PROTOCOL.md`'s own Canonical HUMAN GATES
list names Gate 7 "Final Production Release" - textually the same shape as
Gate 1 ("PHASE 0 canonical architecture acceptance"), and
`acceptance.human_gate_authorization.SINGLETON_GATES` already declares both
`{"HUMAN_GATE_1", "HUMAN_GATE_7"}` as "a unique, non-repeatable project
event", answered by "a legacy, gate-ID-only record" rather than the scoped
`(gate, operation_class, target, revision)` mechanism `CORE_PROMOTION`/
`PROMOTE_CHILD_PRODUCT`/`APPLY_MIGRATION` each use. This module therefore
composes `GovernanceState.accepted_human_gates` - the identical simple,
unscoped membership check Gate 1 already answers phase acceptance with -
never a scoped `operation_grant` lookup: inventing one for a canonically-
declared singleton would be a second, narrower grant-scoping mechanism this
repository's own `SINGLETON_GATES` declaration already forbids building.
(An earlier draft of this module built exactly that scoped mechanism before
this canonical text was read closely enough to catch the mismatch -
corrected here, not shipped.)

`evidence_complete` STILL COMES FROM REAL ARTIFACT RE-VERIFICATION -
`release_composition.verify_evidence_complete`, never a stored flag.

`HumanGate7Source` IS A STRUCTURAL PROTOCOL, NOT A DIRECT IMPORT.
`acceptance.engine.GovernanceState` satisfies it structurally through its
own `accepted_human_gates` attribute - `lifecycle.release`'s own chain into
`kernel.contracts` has no headroom for a direct `acceptance.engine` edge,
the identical constraint `core_upgrade_orchestrator.HumanGate2Source` and
`migration_safety_types.HumanGateSource` already answered the same way.
"""

from __future__ import annotations

from typing import Final, Protocol, runtime_checkable

from arkali.lifecycle.release.release_composition import (
    ReleaseManifestComposition,
    verify_evidence_complete,
)
from arkali.lifecycle.release.release_provenance import ArtifactRegistrar

GATE_7: Final[str] = "HUMAN_GATE_7"


@runtime_checkable
class HumanGate7Source(Protocol):
    """Structural view of `GovernanceState`'s own `accepted_human_gates` set
    - the singleton mechanism Gate 1 already uses. See the module docstring
    for why this is not a scoped `operation_grant` lookup."""

    accepted_human_gates: frozenset[str]


def authorize_release(
    gates: HumanGate7Source, artifacts: ArtifactRegistrar,
    composition: ReleaseManifestComposition,
) -> dict[str, object]:
    """The real guard context for `SIGNED_READY -> RELEASED`.

    `human_gate_7_recorded` is populated only from the real, unscoped
    `HUMAN_GATE_7` singleton membership - never a caller-asserted boolean.
    `evidence_complete` is re-derived from real artifact verification for
    `composition`, which every release candidate still supplies genuinely
    even though the gate itself is project-wide, not per-release.
    """
    recorded = GATE_7 in gates.accepted_human_gates
    complete = verify_evidence_complete(artifacts, composition)
    return {"human_gate_7_recorded": recorded, "evidence_complete": complete}


__all__ = [
    "GATE_7",
    "HumanGate7Source",
    "authorize_release",
]
