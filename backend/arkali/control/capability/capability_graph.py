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

PHASE 9B PACKAGE 1 ADDED RESOLUTION; PACKAGE 2 ADDS THE VERDICT.
`resolve_references` performs the §1 rule — every external `*_ref` resolved at
query time against its owning authority — and `can_perform` composes those
outcomes, the node's own `configured_state` and its graph-owned `prerequisites`
into one determinate answer. The authorities are held; their answers never are,
so every query re-asks and a changed answer is observed on the next call.

THE NEGATIVE STATE IS `NOT_CONFIGURED`, DERIVED FROM §4's OWN WORDING. See
`activated_query.py` for the derivation and for why `FAIL` and `UNSUPPORTED` are
both refused here. The short form: §4 pairs *resolving* with *not being*
`NOT_CONFIGURED`, and `UNSUPPORTED` is canonically another context's verdict.

FIELDS THIS QUERY DELIBERATELY DOES NOT EVALUATE. `runtime_requirements` and
`platform_support` carry no canonical evaluation rule and no authority is
declared for either, so nothing is invented for them. `fallback_refs` are
validated as references and never consulted for the verdict, because fallback
*selection* has no canonical semantics here. `isolation_tier` satisfiability
belongs to `control.isolation` and to admission condition (b), not to this query.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from arkali.control.capability.activated_query import ACTIVATED_SOURCE, refusal_for
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
        """"Can I perform this?" — determinate, and derived from live authorities.

        Pre-activation the answer is `NOT_CONFIGURED`, unchanged since Phase 3.
        Activated, every reference the node declares is resolved at query time
        and the node's own declaration is read; an affirmative answer requires
        all of them, so `PASS` is earned rather than defaulted.

        The capability must still exist: an unknown id raises rather than being
        answered `NOT_CONFIGURED`, so a typo cannot masquerade as a governed
        answer. A prerequisite cycle raises for the same reason — a malformed
        graph is not an unconfigured capability.
        """
        node = self.get(capability_id)
        if not self.is_activated:
            return self._not_configured(
                capability_id,
                f"capability graph is schema-only until phase "
                f"{self.activation_phase}; current phase is "
                f"{self.current_phase}. No referenced authority exists yet.",
            )
        if self._references is None:
            return self._not_configured(
                capability_id,
                f"phase {self.current_phase} is the activation phase, but no "
                "reference authority is composed, so no reference can be "
                "resolved. ADR-0003 activates the graph only once its referenced "
                "authorities exist.",
            )
        refusal = self._refusal(node, ())
        if refusal is not None:
            return self._not_configured(capability_id, refusal)
        return CapabilityQueryResult(
            capability_id=capability_id,
            state=HonestState.PASS,
            reason=(
                "every reference the node declares was resolved by its owning "
                "authority at query time, and the node declares itself configured"
            ),
            authoritative_source=ACTIVATED_SOURCE,
        )

    def _not_configured(
        self, capability_id: str, reason: str
    ) -> CapabilityQueryResult:
        return CapabilityQueryResult(
            capability_id=capability_id,
            state=HonestState.NOT_CONFIGURED,
            reason=reason,
            authoritative_source=(
                ACTIVATED_SOURCE if self.is_activated else ADR_SOURCE
            ),
        )

    def _refusal(self, node: CapabilityNode, chain: tuple[str, ...]) -> str | None:
        """Why this capability did not resolve, or None if it did.

        `prerequisites` are graph-owned and transitive: a capability whose
        prerequisite has not resolved has not resolved either. They are visited
        in the order the node declares them, after the node's own inputs, so the
        reason is stable. A cycle is a malformed graph and RAISES rather than
        being answered, because answering it would report a structural defect as
        an ordinary configuration state.
        """
        if node.id in chain:
            raise InvalidCapabilityReference(
                f"prerequisite cycle {list(chain + (node.id,))}; a capability "
                "cannot be its own prerequisite, directly or transitively",
                source=ADR_SOURCE,
            )
        assert self._references is not None  # guarded by the caller
        own = refusal_for(node, self._references.resolve(node))
        if own is not None:
            return own
        for prerequisite in node.prerequisites:
            inner = self._refusal(self.get(prerequisite), chain + (node.id,))
            if inner is not None:
                return f"prerequisite {prerequisite!r} did not resolve: {inner}"
        return None

    def activate(self) -> None:
        """Always refuses. Activation is a phase fact, not an operation.

        There is no stored flag to switch, at any phase: `is_activated` is
        derived from the activation phase and the current phase, both supplied
        from authoritative state. A caller that could activate the graph would
        be deciding a governed fact locally, which is why this refuses at the
        activation phase too rather than only before it.
        """
        raise PrematureActivation(
            f"activation is not an operation: it is derived from the activation "
            f"phase {self.activation_phase} and the current phase "
            f"{self.current_phase}. ADR-0003 leaves no flag to set.",
            source=ADR_SOURCE,
        )
