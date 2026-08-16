"""C-37 requirement + architecture blueprint: the data model.

Owner: control.specification. Concern: `requirement_and_architecture_intelligence`
(D-025, `docs/build/DECISION_LOG.md`).

WHY THIS IS A SEPARATE CONTRACT FROM C-04. `ARK-REQ-0388` requires user/product
requirement records to stay structurally distinct from the canonical `ARK-REQ`
governance register (`requirement_record.py`, C-04): a `CandidateRequirement`
below is never assigned an `ARK-REQ-####` id, is never accepted by
`RequirementRegister`, and carries no `owning_phase` — conflating the two would
let a product requirement discharge, or be discharged by, canonical governance
coverage, which no accepted mechanism in this repository permits.

REVISION IDENTITY IS CONTENT-ADDRESSED, NOT A COUNTER (`ARK-REQ-0389`). Every
`RequirementBlueprint.blueprint_id` is `content_address.address_of` over its own
canonical bytes, the same shape `RepairFingerprint` (C-26) and `ArtifactRecord`
(C-14) already use. Two blueprints derived from byte-identical input at the same
revision therefore carry the identical id — proving `ARK-REQ-0381`'s determinism
requirement structurally, not by convention.

NO PRODUCT CODE, NO ACCEPTANCE VERDICT (`ARK-REQ-0390`/`0391`). Every field below
is data: goal text, derived requirement statements, open questions, an
architecture-concern label. Nothing here is executable, and nothing carries a
PASS/FAIL/ACCEPTED value — nowhere before the last field of this module does a
outcome verdict of any kind ever appear.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field

from arkali.kernel.contracts import content_address


class RequirementCategory(str, enum.Enum):
    """The closed classification vocabulary (`ARK-REQ-0385`).

    `UNCLASSIFIED` is a member of the vocabulary, not an absence of one: a
    candidate requirement whose category cannot be mechanically derived is
    honestly labelled `UNCLASSIFIED` rather than defaulted to a guessed member.
    """

    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    SECURITY = "security"
    DATA = "data"
    INTEGRATION = "integration"
    UI = "ui"
    OPERATIONS = "operations"
    UNCLASSIFIED = "unclassified"


class UnresolvedQuestionKind(str, enum.Enum):
    """The closed vocabulary of governed-stop reasons (`ARK-REQ-0383`)."""

    AMBIGUOUS = "ambiguous"
    CONTRADICTORY = "contradictory"
    UNDERSPECIFIED = "underspecified"
    MISSING_ACCEPTANCE_CRITERIA = "missing_acceptance_criteria"


class ProductGoal(BaseModel):
    """The human-submitted natural-language product goal, preserved verbatim.

    `goal_text` is never rewritten or summarised: every derived requirement's
    provenance traces back to these exact bytes (`ARK-REQ-0382`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    goal_text: str = Field(min_length=1)

    @property
    def goal_id(self) -> str:
        """Content address of the goal text — the provenance root."""
        return content_address.address_of(self.goal_text.encode("utf-8"))


class UnresolvedQuestion(BaseModel):
    """One governed stop: something the engine refused to invent an answer for."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject_index: int | None = Field(
        default=None,
        description="Index into the blueprint's requirements, or None for a "
        "goal-level question.",
    )
    kind: UnresolvedQuestionKind
    detail: str = Field(min_length=1)


class CandidateRequirement(BaseModel):
    """One deterministically derived candidate requirement fragment.

    Never carries an `ARK-REQ-####` id or an `owning_phase` — `ARK-REQ-0388`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    index: int = Field(ge=0)
    statement: str = Field(min_length=1)
    category: RequirementCategory
    #: Empty when no criterion is mechanically derivable (`ARK-REQ-0384`); the
    #: absence is also recorded as a `MISSING_ACCEPTANCE_CRITERIA` question.
    acceptance_criteria: tuple[str, ...] = ()
    #: A concern name from `AuthorityMap.concerns`, or None when no concern's
    #: name shares a resolvable token with this requirement's category/text
    #: (`ARK-REQ-0386`). Never a bounded-context name invented by this module.
    owning_concern: str | None = None

    @property
    def requirement_id(self) -> str:
        """Content address over `(index, statement)` — stable, never reused."""
        payload = f"{self.index} {self.statement}".encode()
        return content_address.address_of(payload)


class RequirementBlueprint(BaseModel):
    """C-37: the machine-readable product/requirement blueprint (`ARK-REQ-0387`).

    Always produced — this model carries no PASS/FAIL/ACCEPTED field. A
    request that could not be fully resolved still yields a blueprint; the
    `unresolved` tuple is how "ambiguous request fails honestly" is expressed,
    never an exception that discards the goal.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    goal: ProductGoal
    requirements: tuple[CandidateRequirement, ...]
    unresolved: tuple[UnresolvedQuestion, ...] = ()
    #: Starts at 1. A later derivation over a changed goal for the same
    #: lineage supplies `previous_blueprint_id` and increments this.
    revision: int = Field(ge=1, default=1)
    previous_blueprint_id: str | None = None

    @property
    def blueprint_id(self) -> str:
        """Content address over the blueprint's own canonical bytes.

        Deterministic (`ARK-REQ-0381`): identical goal, requirements,
        unresolved set and revision lineage always address to the same id, in
        any process, on any host.
        """
        parts = [
            self.goal.goal_id,
            str(self.revision),
            self.previous_blueprint_id or "",
        ]
        for req in self.requirements:
            parts.append(req.requirement_id)
            parts.append(req.category.value)
            parts.append(req.owning_concern or "")
            parts.append("".join(req.acceptance_criteria))
        for question in self.unresolved:
            parts.append(str(question.subject_index))
            parts.append(question.kind.value)
            parts.append(question.detail)
        payload = "".join(parts).encode("utf-8")
        return content_address.address_of(payload)

    @property
    def is_fully_resolved(self) -> bool:
        return not self.unresolved
