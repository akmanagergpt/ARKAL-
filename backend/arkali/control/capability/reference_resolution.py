"""Query-time resolution of C-13 references (Phase 9B, Package 1).

Owner: control.capability.

THE CANONICAL RULE, IMPLEMENTED AS WRITTEN. `EXECUTION_AND_CAPABILITY.md` §1:
"`can_perform(capability_id)` resolves every `*_ref` at query time against its
owning authority. Health, cost, availability and fallback are **never** stored
here." `MS §Capability Graph` says the same of every externally owned attribute:
"stored as references, never copies, and are resolved at query time." This module
is that resolution, and nothing else.

REFERENCE IN, OUTCOME OUT - NEVER A VALUE. Resolution answers one question per
reference: does the owning authority resolve this identifier? It never asks for,
receives, returns or retains the referenced value. That is what keeps
`ARK-REQ-0053` structurally true rather than policed: there is no field here that
could hold provider identity, model identity, configuration, health,
availability, cost metadata or fallback, so no shadow registry can form even by
accident.

NOTHING IS CACHED, AND THAT IS STRUCTURAL. `ReferenceResolvers` holds the
AUTHORITIES and never their answers: it has exactly two attributes, both supplied
at construction, and `resolve` builds its outcomes fresh and hands them to the
caller. There is no memo, no last-answer field and no lazy default, so an
authority that changes its mind between two calls is observed on the second one.
ADR-0003 puts that obligation on consumers; a graph that cached would make the
consumer rule unenforceable from below.

PASS IS PRODUCED ONLY BY A LIVE AUTHORITY. A reference resolves if and only if a
supplied resolver was asked and answered true. A missing resolver yields
`NOT_CONFIGURED` and a refusing resolver yields `FAIL` - both determinate, both
non-PASS. There is no branch in which an absent, silent or unsupplied authority
produces a resolved reference. That is the fail-closed rule `MS §Capability
Graph` states as "never returns a stubbed, defaulted or assumed value".

WHAT THIS PACKAGE DELIBERATELY DOES NOT DO. It composes no capability verdict.
`CapabilityGraph.can_perform` is unchanged and still answers `NOT_CONFIGURED`
before activation, so Phase 8 admission still refuses with
`CAPABILITY_NOT_CONFIGURED` and the honest production position is preserved. How
a set of resolutions becomes one determinate answer to "Can I perform this?" is
the next package's question, and the canonical set is read for it there rather
than guessed at here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from arkali.control.capability.capability_node import CapabilityNode
from arkali.control.capability.reference_authority import (
    CapabilityReferenceAuthority,
    ReferenceBinding,
)
from arkali.kernel.contracts.capability_errors import InvalidCapabilityReference
from arkali.kernel.contracts.error_base import AuthoritativeSourceError
from arkali.kernel.contracts.results import HonestState

RESOLUTION_SOURCE: Final[str] = (
    "docs/canonical/EXECUTION_AND_CAPABILITY.md §1 (resolution rule) + "
    "MS §Capability Graph"
)


@runtime_checkable
class ReferenceResolver(Protocol):
    """The one question this context may ask of another authority.

    A Protocol rather than a concrete type, because `control.capability` is layer
    rank 1 and so is every authority it references: `allow_same_layer: false`
    forbids the import outright, and `ARCHITECTURE.md` §4 rule 3 makes interface
    inversion the canonical answer. The composition root supplies the
    implementation; this context never reaches for one.

    The question is deliberately narrow. `resolves` returns whether the authority
    declares the identifier - not what it holds against it. A resolver that
    returned a value would let a caller store one, and storing one is exactly
    what ARK-REQ-0047 and ARK-REQ-0053 forbid.
    """

    def resolves(self, reference: str) -> bool:
        ...


class ReferenceResolution(BaseModel):
    """The outcome of resolving one reference against one authority."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: The `CapabilityNode` field the reference was declared in.
    field: str
    #: The identifier that was resolved. A reference, never a value.
    reference: str
    #: The context the canonical schema names as its owner.
    authority: str
    state: HonestState
    reason: str
    authoritative_source: str = RESOLUTION_SOURCE

    @property
    def resolved(self) -> bool:
        """True only for a live authority's affirmative answer."""
        return self.state is HonestState.PASS


def unresolved(
    resolutions: tuple[ReferenceResolution, ...],
) -> tuple[ReferenceResolution, ...]:
    """Every outcome that is not an affirmative answer from a live authority."""
    return tuple(r for r in resolutions if not r.resolved)


class ReferenceResolvers:
    """The authorities a graph resolves its external references against.

    Holds the authorities and the canonical binding. Holds no answer.
    """

    def __init__(
        self,
        binding_authority: CapabilityReferenceAuthority,
        resolvers: Mapping[str, ReferenceResolver],
    ) -> None:
        declared = set(binding_authority.authorities())
        unknown = sorted(name for name in resolvers if name not in declared)
        if unknown:
            raise AuthoritativeSourceError(
                f"resolvers supplied for {unknown}, which the canonical "
                "capability schema does not name as reference authorities",
                source=binding_authority.source_path,
            )
        self._binding_authority = binding_authority
        self._resolvers = dict(resolvers)

    @property
    def binding_authority(self) -> CapabilityReferenceAuthority:
        return self._binding_authority

    def missing_authorities(self) -> tuple[str, ...]:
        """Declared authorities no resolver was supplied for.

        Reported rather than defaulted: a caller may legitimately hold a partial
        set, and every reference into a missing authority answers
        `NOT_CONFIGURED` rather than being assumed either way.
        """
        return tuple(
            name
            for name in self._binding_authority.authorities()
            if name not in self._resolvers
        )

    def resolve(self, node: CapabilityNode) -> tuple[ReferenceResolution, ...]:
        """Resolve every external reference the node declares, in schema order.

        Deterministic: the fields are visited in the canonical schema's order and
        each field's references in the order the node declares them, so the same
        node against the same authority state produces the identical sequence.
        """
        found: list[ReferenceResolution] = []
        for binding in self._binding_authority.external():
            for reference in _references_in(node, binding):
                found.append(self._resolve_one(binding, reference))
        return tuple(found)

    def _resolve_one(
        self, binding: ReferenceBinding, reference: str
    ) -> ReferenceResolution:
        resolver = self._resolvers.get(binding.authority)
        if resolver is None:
            return self._outcome(
                binding,
                reference,
                HonestState.NOT_CONFIGURED,
                f"no {binding.authority} resolver is supplied, so this "
                f"{binding.target_kind} cannot be resolved. The reference is "
                "neither granted nor denied",
            )
        if resolver.resolves(reference):
            return self._outcome(
                binding,
                reference,
                HonestState.PASS,
                f"{binding.authority} resolves this {binding.target_kind}",
            )
        return self._outcome(
            binding,
            reference,
            HonestState.FAIL,
            f"{binding.authority} does not resolve {binding.target_kind} "
            f"{reference!r}",
        )

    @staticmethod
    def _outcome(
        binding: ReferenceBinding, reference: str, state: HonestState, reason: str
    ) -> ReferenceResolution:
        return ReferenceResolution(
            field=binding.field,
            reference=reference,
            authority=binding.authority,
            state=state,
            reason=reason,
        )


def _references_in(node: CapabilityNode, binding: ReferenceBinding) -> tuple[str, ...]:
    """The identifiers a node holds in one declared reference field.

    A field may be a single optional identifier or a tuple of them; both shapes
    are declared in the canonical block and both are read here. A field the
    canonical schema declares and the model does not is refused rather than
    skipped, because skipping it would silently stop resolving a real reference.
    """
    if binding.field not in type(node).model_fields:
        raise AuthoritativeSourceError(
            f"the canonical schema declares reference field {binding.field!r}, "
            "which the capability node model does not carry",
            source=RESOLUTION_SOURCE,
        )
    held = getattr(node, binding.field)
    if held is None:
        return ()
    if isinstance(held, str):
        return (held,)
    if isinstance(held, tuple):
        return tuple(str(item) for item in held)
    raise InvalidCapabilityReference(
        f"{node.id}: reference field {binding.field!r} holds {type(held).__name__}, "
        "which is neither an identifier nor a tuple of identifiers",
        source=RESOLUTION_SOURCE,
    )
