"""Capability Graph — schema-only, pre-activation (ARK-REQ-0045, ARK-REQ-0049).

Owner: control.capability. Concern: `capability_availability_answer`.

ADR-0003 splits this contract: Phase 3 delivers the schema, Phase 9B activates
the graph once `control.policy` (P4), `evidence.*` (P6) and
`control.registry.provider` (P9) exist. Between those phases every query returns
`NOT_CONFIGURED`.

WHY NOT_CONFIGURED IS THE WHOLE POINT. `NOT_CONFIGURED` is a determinate answer,
so returning it satisfies the determinism requirement (ARK-REQ-0046) without
inventing a verdict. A hard-coded "available", a default of "unavailable", or a
value assumed from the node's own `configured_state` would each be a fabricated
answer about authorities that do not exist yet — exactly the failure ADR-0003 was
written to prevent. This module therefore carries no resolution path at all:
there is nothing to accidentally leave enabled.

NO SHADOW MODEL. The activation phase is not written here. It is governed data —
`ARK-REQ-0048` carries it in the requirement register's Phase column — and is
injected at construction. Hard-coding "9B" would put a governed value in a second
place, which is defect class F-0013.

PHASE 9B PACKAGE 1 ADDS RESOLUTION, NOT A VERDICT. `resolve_references` performs
the §1 rule — every external `*_ref` resolved at query time against its owning
authority — and reports the outcome per reference. `can_perform` is deliberately
unchanged: composing those outcomes into one answer to "Can I perform this?" is
the next package's question, and until it is answered from canonical authority
the honest pre-activation position stands. The authorities are held, their
answers never are.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from arkali.control.capability.capability_node import CapabilityNode
from arkali.control.capability.reference_resolution import (
    ReferenceResolution,
    ReferenceResolvers,
)
from arkali.kernel.contracts.capability_errors import (
    DuplicateCapabilityIdentity,
    InvalidCapabilityReference,
    PrematureActivation,
)
from arkali.kernel.contracts.results import HonestState

ADR_SOURCE = "ADR-0003 (schema Phase 3, activation Phase 9B)"


class CapabilityQueryResult(BaseModel):
    """Deterministic answer to "Can I perform this?"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    capability_id: str
    state: HonestState
    reason: str
    authoritative_source: str = ADR_SOURCE

    @property
    def is_determinate(self) -> bool:
        """NOT_CONFIGURED is determinate. Only a missing answer would not be."""
        return self.state is not HonestState.NOT_TESTED


class CapabilityGraph:
    """A validated set of capability nodes. Inert until its activation phase.

    `activation_phase` and `current_phase` are both supplied by the caller from
    authoritative state; this class judges neither.
    """

    def __init__(
        self,
        nodes: Iterable[CapabilityNode],
        *,
        activation_phase: str,
        current_phase: str,
        references: ReferenceResolvers | None = None,
    ) -> None:
        self._nodes = self._index(nodes)
        self._validate_references()
        self.activation_phase = activation_phase
        self.current_phase = current_phase
        #: The referenced AUTHORITIES, never their answers. Optional because a
        #: graph may legitimately exist before its authorities are composed, and
        #: `resolve_references` refuses rather than assuming when they are absent.
        self._references = references

    @staticmethod
    def _index(nodes: Iterable[CapabilityNode]) -> dict[str, CapabilityNode]:
        indexed: dict[str, CapabilityNode] = {}
        for node in nodes:
            if node.id in indexed:
                raise DuplicateCapabilityIdentity(
                    f"capability {node.id!r} is declared more than once",
                    source=ADR_SOURCE,
                )
            indexed[node.id] = node
        return indexed

    def _validate_references(self) -> None:
        """Every prerequisite and fallback must resolve inside this graph."""
        unresolved: list[str] = []
        for node in self._nodes.values():
            for field_name in ("prerequisites", "fallback_refs"):
                for ref in getattr(node, field_name):
                    if ref not in self._nodes:
                        unresolved.append(f"{node.id}.{field_name} -> {ref}")
        if unresolved:
            raise InvalidCapabilityReference(
                f"unresolved capability references: {sorted(unresolved)}",
                source=ADR_SOURCE,
            )

    def __len__(self) -> int:
        return len(self._nodes)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._nodes))

    def get(self, capability_id: str) -> CapabilityNode:
        node = self._nodes.get(capability_id)
        if node is None:
            raise InvalidCapabilityReference(
                f"unknown capability {capability_id!r}", source=ADR_SOURCE
            )
        return node

    @property
    def is_activated(self) -> bool:
        """Activation is a phase fact, never a local flag a caller can set."""
        return self.current_phase == self.activation_phase

    def resolve_references(
        self, capability_id: str
    ) -> tuple[ReferenceResolution, ...]:
        """Resolve one node's external references against their owning authorities.

        The §1 resolution rule, executed on demand. Every call re-asks every
        authority: no outcome is stored here or in `ReferenceResolvers`, so a
        changed answer is visible on the next call rather than on the next
        process.

        Refuses rather than assuming when no authorities were composed. An empty
        answer would be indistinguishable from "everything resolved", which is
        precisely the "stubbed, defaulted or assumed value" the Master
        Specification forbids a capability query to return.
        """
        node = self.get(capability_id)
        if self._references is None:
            raise InvalidCapabilityReference(
                f"{capability_id}: no reference authorities are composed, so no "
                "reference can be resolved. Reporting none unresolved would be "
                "an assumption, not an answer",
                source=ADR_SOURCE,
            )
        return self._references.resolve(node)

    def can_perform(self, capability_id: str) -> CapabilityQueryResult:
        """Pre-activation this is always NOT_CONFIGURED — never a fabricated verdict.

        The capability must still exist: an unknown id raises rather than being
        answered NOT_CONFIGURED, so a typo cannot masquerade as a governed
        pre-activation answer.
        """
        self.get(capability_id)
        if not self.is_activated:
            return CapabilityQueryResult(
                capability_id=capability_id,
                state=HonestState.NOT_CONFIGURED,
                reason=(
                    f"capability graph is schema-only until phase "
                    f"{self.activation_phase}; current phase is "
                    f"{self.current_phase}. No referenced authority exists yet."
                ),
            )
        raise PrematureActivation(
            f"{capability_id}: resolution is owned by phase "
            f"{self.activation_phase} and is not implemented in the schema "
            "phase. Returning any verdict here would fabricate an answer.",
            source=ADR_SOURCE,
        )

    def activate(self) -> None:
        """Always refuses in the schema phase. Phase 9B owns real activation."""
        raise PrematureActivation(
            f"activation is owned by phase {self.activation_phase}; current "
            f"phase is {self.current_phase}. ADR-0003 forbids earlier activation.",
            source=ADR_SOURCE,
        )
