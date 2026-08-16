"""C-28 knowledge record + validity state (ARK-REQ-0126, ARK-REQ-0127).

ONLY EVIDENCE-BACKED OUTCOMES BECOME AUTHORITATIVE KNOWLEDGE (ARK-REQ-0126,
ARK-REQ-0394). The refusal is structural, not a text check on a free-form
field: `KnowledgeRecord.evidence` and `VerifiedOutcome.evidence`
(`outcome_statistics.py`) both require an `EvidenceReference` — a real,
canonically content-addressed pointer to independently produced evidence
(a C-14 artifact, a C-15 audit record, or an `acceptance.engine` C-16/C-17
result). `SelfReportedClaim` — a model's own unverified statement about
itself — is a structurally distinct type with no `content_address` field at
all, so it cannot be supplied anywhere an `EvidenceReference` is required;
pydantic refuses it at construction, the same shape `RepairFingerprint`
(C-26) uses for its own required fields. Nothing here inspects prose to
decide whether a claim is "self-reported" — the type a caller chooses to
construct decides that, once, at the boundary.

NO LIVE EVIDENCE-STORE LOOKUP. `EvidenceReference.content_address` is
validated to be a well-formed canonical address (`kernel.contracts.
content_address.is_address`); this package does not cross-reference it
against a currently-stored C-14/C-15/C-16 record. That is the identical
non-live-lookup shape `engineering.repair`'s C-26 `RepairFingerprint`
already established — content-addressed identity, not a live authority
call — recorded here rather than invented silently, per
`docs/contracts/knowledge.md`.

KNOWLEDGE VALIDITY IS A LOCAL LIFECYCLE, NOT A 13TH STATE MACHINE.
`docs/canonical/STATE_MACHINES.md` (Human Gate 1, closed) declares exactly
12 machines and knowledge validity is not one of them; MS §Knowledge names
the five state values (`fresh`, `aging`, `revalidation_required`,
`deprecated`, `invalid`) but states no transition graph for them, unlike
every one of the 12 canonical machines, each of which lists its transitions
explicitly. The graph in `_ALLOWED_TRANSITIONS` below is derived from the
ordinary meaning of each state name — the same textual-derivation method
`docs/contracts/knowledge.md` records and `harness_elements.py`
(Phase 10) established as this build's answer to an underspecified
canonical vocabulary — not invented ad hoc and not a governance addition to
`STATE_MACHINES.md`'s reconciled count, which stays 12.
"""

from __future__ import annotations

import enum
import json
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

from arkali.engineering.knowledge.errors import (
    IllegalValidityTransitionError,
    UnbackedKnowledgeClaimError,
)
from arkali.kernel.contracts.content_address import address_of, is_address

CONTRACT_VERSION: Final[str] = "1.0.0"
Declared = Annotated[str, Field(min_length=1)]
Count = Annotated[int, Field(ge=0)]


class EvidenceKind(str, enum.Enum):
    """The closed, real-evidence vocabulary `EvidenceReference.kind` may
    declare. There is deliberately no `SELF_REPORTED` member here —
    self-reported claims are `SelfReportedClaim`, a different type."""

    ARTIFACT = "artifact"
    AUDIT = "audit"
    ACCEPTANCE_RESULT = "acceptance_result"


class EvidenceReference(BaseModel):
    """A real, content-addressed pointer to independently produced
    evidence. Required by `KnowledgeRecord.evidence` and
    `outcome_statistics.VerifiedOutcome.evidence` alike — one shared type,
    never a second copy of the same discipline."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    kind: EvidenceKind
    content_address: Declared

    @field_validator("content_address")
    @classmethod
    def _must_be_canonical_address(cls, value: str) -> str:
        if not is_address(value):
            raise UnbackedKnowledgeClaimError(
                f"evidence content_address {value!r} is not a canonical "
                "content address (sha256:<64 hex>)"
            )
        return value


class SelfReportedClaim(BaseModel):
    """A model's own unverified statement about an outcome or its
    performance. Honestly recordable as what it is — never accepted where
    `EvidenceReference` is required (ARK-REQ-0126, ARK-REQ-0394)."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    reported_by: Declared
    claim: Declared


class KnowledgeValidityState(str, enum.Enum):
    FRESH = "fresh"
    AGING = "aging"
    REVALIDATION_REQUIRED = "revalidation_required"
    DEPRECATED = "deprecated"
    INVALID = "invalid"


#: Transitions not listed are structurally impossible — see the module
#: docstring for the derivation. `INVALID` is terminal, matching
#: `STATE_MACHINES.md`'s cross-cutting invariant 7 ("every terminal state
#: is genuinely terminal"), applied here by the same convention even though
#: this lifecycle is not one of the reconciled 12.
_ALLOWED_TRANSITIONS: Final[dict[KnowledgeValidityState, frozenset[KnowledgeValidityState]]] = {
    KnowledgeValidityState.FRESH: frozenset(
        {KnowledgeValidityState.AGING, KnowledgeValidityState.INVALID}
    ),
    KnowledgeValidityState.AGING: frozenset(
        {
            KnowledgeValidityState.FRESH,
            KnowledgeValidityState.REVALIDATION_REQUIRED,
            KnowledgeValidityState.INVALID,
        }
    ),
    KnowledgeValidityState.REVALIDATION_REQUIRED: frozenset(
        {
            KnowledgeValidityState.FRESH,
            KnowledgeValidityState.DEPRECATED,
            KnowledgeValidityState.INVALID,
        }
    ),
    KnowledgeValidityState.DEPRECATED: frozenset({KnowledgeValidityState.INVALID}),
    KnowledgeValidityState.INVALID: frozenset(),
}


def assert_transition_allowed(
    current: KnowledgeValidityState, target: KnowledgeValidityState
) -> None:
    """Raise unless `current -> target` is a declared transition."""
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise IllegalValidityTransitionError(
            f"{current.value} -> {target.value} is not a declared "
            "knowledge-validity transition"
        )


class KnowledgeRecord(BaseModel):
    """One authoritative knowledge claim. `evidence` is mandatory and typed
    as `EvidenceReference`, so a `SelfReportedClaim` cannot be substituted —
    ARK-REQ-0126 enforced by construction, not by inspecting prose."""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    contract_version: str = CONTRACT_VERSION
    subject: Declared
    claim: Declared
    evidence: EvidenceReference
    validity_state: KnowledgeValidityState = KnowledgeValidityState.FRESH

    def rendering(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    @property
    def record_ref(self) -> str:
        return address_of(self.rendering())

    def transitioned(self, target: KnowledgeValidityState) -> KnowledgeRecord:
        """Return a new record in `target` state, or refuse. Immutable
        functional update, the same shape `RepairBudgetLedger.record`
        (C-26) established."""
        assert_transition_allowed(self.validity_state, target)
        return type(self).model_validate(
            {**self.model_dump(), "validity_state": target}
        )
