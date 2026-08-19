"""Release Manifest domain model + Release Authority (ARK-REQ-0007 partial,
ARK-REQ-0350 partial).

Owner: `lifecycle.release` (Protected Core).

REUSES THE REAL, UNMODIFIED `Release` MACHINE. Declared in
`release_state_machine.py` since this repository's early phases
(`docs/canonical/STATE_MACHINES.md` §7) but never composed by any production
code until this phase - `ReleaseAuthority` is the first real caller.
No second state machine is minted.

REUSES THE REAL, UNMODIFIED `StableRevisionPointer`. D-017 records that
Phase 22B's pointer primitive "is not Phase 26's release/supply-chain/
deployment system... without creating a second release authority" - this
module is that system, and it READS the pointer Phase 22B already built
rather than duplicating any part of it. `ReleaseAuthority` never calls
`promote`/`rollback_to`; both remain reachable only through
`lifecycle.recovery` (rollback) and the Core Upgrade pipeline (promotion),
unchanged.

A RELEASE CANDIDATE PACKAGES AN ALREADY-STABLE CORE REVISION.
`declare_release_candidate` refuses when `StableRevisionPointer.current()`
is `None` - there is nothing to package before a Stable Core revision
exists. This is the literal mechanism behind ARK-REQ-0007 ("Stable
definitions take effect from first Release-Authority designation"): a
"Stable Product revision" (MS's own term, distinct from "Stable Core
revision") has no meaning until this Release Authority's first real `DRAFT`
declaration exists, and that declaration can only ever reference an
already-designated Stable Core revision - so "Stable" in either sense
always traces back to a real prior act of promotion, never a caller's
assertion.

WHY `core_revision_id` NOT SOME NEW "product" IDENTITY. MS §Product Plane's
own two sentences name exactly two Stable kinds - Core and Product - and
this repository's canonical scope for Phase 26 (`IMPLEMENTATION_DEPENDENCY_
MATRIX.md` row 26, prerequisites 6/13/22B, VDC §Final delivery's own list:
"complete repo; Windows installer;...") is releasing ARKALI itself, not an
arbitrary generated product - that is Phase 24's Product Evolution SDK
domain, which already built its own, deliberately separate
`child_product_version.py` lineage. Packaging the Core's own already-Stable
revision for distribution is the "Stable Product revision" this phase
designates.

THE RELEASE ID IS CONTENT-ADDRESSED, NEVER CALLER-SUPPLIED. Derived from the
core revision plus the declaration instant, so two real declarations of the
same core revision at different times are distinct release candidates
(re-releasing the same content is a legitimate act, e.g. after a
rollback-then-reapply cycle) while a replayed, byte-identical declaration
request is idempotent - the defence against "release replay" this context's
own adversarial suite proves directly.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from arkali.kernel.contracts.error_root import ArkaliError
from arkali.lifecycle.release import release_state_machine as rsm
from arkali.lifecycle.release.release_state_machine import StateMachine, StateMachineInstance
from arkali.lifecycle.release.stable_pointer import StableRevisionPointer, address_of

ACTOR: Final[str] = "lifecycle.release"


class ReleaseAuthorityError(ArkaliError):
    """A release candidate could not be declared or advanced."""

    code = "ARK-ERR-0164"


class ReleaseCandidate(BaseModel):
    """One packaging attempt over an already-Stable Core revision.

    Immutable once declared. Later packages (provenance, SBOM, suspicious-
    package review) attach further records keyed by `release_id`; none of
    them mutates this record.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    release_id: str = Field(min_length=1)
    core_revision_id: str = Field(min_length=1)
    declared_at: dt.datetime


def _release_id(core_revision_id: str, declared_at: dt.datetime) -> str:
    """Content-addressed, never caller-suppliable - the same discipline
    every other identity in this repository's Protected Core uses."""
    canonical = f"{core_revision_id}|{declared_at.isoformat()}"
    return address_of(canonical.encode("utf-8"))


class ReleaseAuthority:
    """The sole production composer of the real `Release` machine.

    Constructed over a real `StableRevisionPointer`, never a caller-supplied
    revision id - the whole point of ARK-REQ-0007 is that a release can only
    ever reference a revision this repository's own Core pointer already,
    genuinely, promoted.
    """

    def __init__(self, pointer: StableRevisionPointer) -> None:
        self._pointer = pointer
        self._machine: StateMachine = rsm.build()

    def declare_release_candidate(
        self, *, now: dt.datetime | None = None
    ) -> tuple[ReleaseCandidate, StateMachineInstance]:
        """Declare a new release candidate over the current Stable Core revision.

        Refuses before constructing anything if no Stable Core revision
        exists yet - `StableRevisionPointer.current()` is `None` before the
        first real Core promotion, and packaging nothing is not a release.
        """
        current = self._pointer.current()
        if current is None:
            raise ReleaseAuthorityError(
                "no Stable Core revision exists yet; a release candidate "
                "must reference a real prior promotion, never an assertion"
            )
        declared_at = now or dt.datetime.now(dt.UTC)
        release_id = _release_id(current.revision_id, declared_at)
        candidate = ReleaseCandidate(
            release_id=release_id,
            core_revision_id=current.revision_id,
            declared_at=declared_at,
        )
        instance = self._machine.start(rsm.DEFINITION.states[0])
        return candidate, instance

    def assert_still_stable(self, candidate: ReleaseCandidate) -> None:
        """Refuse a release candidate whose referenced revision this pointer
        no longer recognises as ever having been Stable.

        Real re-verification, not a stored boolean: re-asks the pointer
        directly rather than trusting the candidate's own field, defending
        against a stale or tampered `ReleaseCandidate` naming a revision
        this repository's own history has since disowned.
        """
        if not self._pointer.is_previously_verified(candidate.core_revision_id):
            raise ReleaseAuthorityError(
                f"release candidate {candidate.release_id!r} names core "
                f"revision {candidate.core_revision_id!r}, which this "
                "repository's own Stable pointer no longer recognises as "
                "ever having been Stable"
            )


__all__ = [
    "ReleaseAuthority",
    "ReleaseAuthorityError",
    "ReleaseCandidate",
]
