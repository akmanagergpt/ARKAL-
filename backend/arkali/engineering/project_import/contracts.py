"""C-29 imported project descriptor + tier assignment (ARK-REQ-0115, 0161, 0162).

Owner: engineering.import.

STRUCTURAL, TYPE-LEVEL TIER FIXATION (ARK-REQ-0161 §12: "the tier cannot be
reassigned by an implementing actor"). `TierAssignment.tier` and
`.assigned_by` are `Literal` types carrying exactly one value each — there is
no constructor argument, no setter and no code path anywhere in this package
by which a caller can produce a `TierAssignment` naming a different tier or a
different assigner. MS §Trust-Tiered Isolation's table names `imported/
untrusted projects` as TRUST-3, unconditionally; this module does not decide
that, it is incapable of deciding anything else.

STRUCTURAL, TYPE-LEVEL NO-EXECUTION PROOF (ARK-REQ-0115, ARK-REQ-0161).
`StaticInspectionReport.executed` is `Literal[False]` — the same shape
`engineering.knowledge`'s `SelfReportedClaim`/`EvidenceReference` split uses
to make a distinction structural rather than advisory. No caller can
construct a report claiming execution occurred; only `static_inspection.py`
produces this type, and it never imports, executes or evaluates the target
source.

THE TIER IS CRYPTOGRAPHICALLY BOUND TO THE INSPECTION THAT JUSTIFIED IT.
`TierAssignment.inspection_ref` must equal the exact
`StaticInspectionReport.source_address` it was assigned against;
`ImportedProjectDescriptor` refuses construction otherwise. A tier assigned
against one snapshot of a source tree cannot silently carry over to a
different one — the C-29 analogue of `WorkflowApprovalGate`'s stale-revision
refusal (`docs/contracts/import.md`).

C-29 IS `INT`: no table, no migration, no ORM record — matching the C-11 /
C-13 / C-23 / C-28 precedent. Every value here is derived at call time from
canonical documents and content-addressed inputs; nothing is a second copy of
governed data.
"""

from __future__ import annotations

import json
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arkali.engineering.project_import.errors import TierReassignmentError
from arkali.kernel.contracts.content_address import address_of, is_address

CONTRACT_VERSION: Final[str] = "1.0.0"

#: MS §Trust-Tiered Isolation: "imported/untrusted projects" -> TRUST-3,
#: unconditionally. Not a default — the only value the type admits.
FIXED_TIER: Final[str] = "TRUST-3"

#: The one authority permitted to assign a tier. Never "implementing_actor" —
#: the exact string `import_project_state_machine.py`'s `tier_assignment_guard`
#: refuses (STATE_MACHINES.md §12).
FIXED_ASSIGNER: Final[str] = "engineering.import.tier_authority"

Declared = Annotated[str, Field(min_length=1)]
NonNegative = Annotated[int, Field(ge=0)]


class StaticInspectionReport(BaseModel):
    """The result of statically inspecting an imported project — never the
    result of running it. `executed` can only ever be `False`."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    #: Content address over the sorted (relative_path, digest) file listing —
    #: the same normalised-rendering-then-hash idiom `CodeGraph.address` and
    #: `CandidateManifest.manifest_ref` already use.
    source_address: Declared
    #: Exactly the graph kinds `PythonGraphBuilder.builds()` produced —
    #: reused, never re-derived by this module.
    graph_kinds: tuple[str, ...]
    #: (kind, content address) pairs, sorted — the built graphs' identities.
    graph_addresses: tuple[tuple[str, str], ...]
    file_count: NonNegative
    executed: Literal[False] = False

    @model_validator(mode="after")
    def _source_address_is_canonical(self) -> StaticInspectionReport:
        if not is_address(self.source_address):
            raise TierReassignmentError(
                f"source_address {self.source_address!r} is not a canonical "
                "content address"
            )
        return self


class TierAssignment(BaseModel):
    """A TRUST tier binding. `tier` and `assigned_by` each admit exactly one
    value — reassignment by an implementing actor is a type error, not a
    runtime check that could be skipped."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    tier: Literal["TRUST-3"] = FIXED_TIER  # type: ignore[assignment]
    assigned_by: Literal["engineering.import.tier_authority"] = FIXED_ASSIGNER  # type: ignore[assignment]
    #: The exact `StaticInspectionReport.source_address` this assignment was
    #: made against.
    inspection_ref: Declared

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def assignment_ref(self) -> str:
        return address_of(self.rendering())


class ImportedProjectDescriptor(BaseModel):
    """The C-29 descriptor: one imported project, its static inspection, its
    tier assignment, and the rescue mode selected for it."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    contract_version: str = CONTRACT_VERSION
    project_id: Declared
    inspection: StaticInspectionReport
    tier_assignment: TierAssignment
    #: Canonical identifier from `RescueModeVocabulary.require_mode`.
    rescue_mode: Declared
    #: Mirrors the `ImportProject` state-machine instance's current state —
    #: informational; the machine itself remains the sole authority on
    #: legality.
    state: Declared

    @model_validator(mode="after")
    def _tier_bound_to_this_inspection(self) -> ImportedProjectDescriptor:
        if self.tier_assignment.inspection_ref != self.inspection.source_address:
            raise TierReassignmentError(
                "tier_assignment.inspection_ref does not match this "
                "descriptor's own inspection.source_address; a tier "
                "assigned against a different snapshot may not be carried "
                "over (ARK-REQ-0161)"
            )
        return self

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def descriptor_ref(self) -> str:
        return address_of(self.rendering())

    def advanced(self, *, state: str) -> ImportedProjectDescriptor:
        """Immutable functional update of `state` only — the same shape
        `KnowledgeRecord.transitioned` established. Callers still drive the
        real `StateMachineInstance`; this only mirrors its outcome."""
        return type(self).model_validate({**self.model_dump(), "state": state})
