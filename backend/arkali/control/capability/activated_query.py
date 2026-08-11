"""The activated verdict for one node's own inputs (Phase 9B, Package 2).

Owner: control.capability.

WHAT THIS DECIDES, AND WHAT IT REFUSES TO DECIDE. `MS §Capability Graph` requires
ARKALI to "answer 'Can I perform this?' deterministically from the graph", and
`EXECUTION_AND_CAPABILITY.md` §1 says how: "`can_perform(capability_id)` resolves
every `*_ref` at query time against its owning authority." This module answers
that for one node's OWN inputs. Composition across `prerequisites` stays in
`CapabilityGraph`, which owns the node set.

THE NEGATIVE STATE IS `NOT_CONFIGURED`, AND IT IS DERIVED RATHER THAN CHOSEN.
§4 admits a job when "its capability resolves other than `NOT_CONFIGURED`" — the
sentence pairs *resolving* with *not being* `NOT_CONFIGURED`, so a capability
that did not resolve is `NOT_CONFIGURED`. `docs/contracts/worker.md` §7 glosses
the accepted Phase 8 outcome the same way: `CAPABILITY_NOT_CONFIGURED` means
"the capability did not resolve". `MS §Capability Graph` reaches the same state
for the same reason before activation — no referenced authority can answer — and
calls it "a determinate answer". A reference that does not resolve after
activation is that condition narrowed to one reference.

`FAIL` IS NOT A CAPABILITY STATE. The canonical set never assigns it to a
capability query. Choosing it here would also be unsafe: the accepted Phase 8
predicate is `state is not NOT_CONFIGURED`, so any other negative state would be
read as condition (a) SATISFIED and would admit work whose references do not
resolve. The predicate is canonical and accepted; this package derives a mapping
that is correct under it rather than quietly narrowing it.

`UNSUPPORTED` IS SOMEBODY ELSE'S ANSWER. The canonical set assigns it to a
capability in exactly two places: isolation properties that no available backend
composition satisfies (`MS §Isolation Backends`, ADR-0002,
`AUTHORITY_MAP.yaml` `isolation.capability_state_when_unsatisfiable`) and a
secret-dependent capability with no OS key protection (`MS §Secrets`). Both are
owned by rank 1 contexts this one may not import, both are already produced by
their owners, and admission condition (b) already consumes the first. Producing
either here would be a second authority for another context's verdict.

PASS IS EARNED, NEVER DEFAULTED. An affirmative answer requires every reference
the node declares to have been resolved by a live authority. A missing resolver,
a refusing authority and an unresolved identifier are all refusals, and there is
no branch in which an unasked authority contributes an affirmative.
"""

from __future__ import annotations

from typing import Final

from arkali.control.capability.capability_node import CapabilityNode, ConfiguredState
from arkali.control.capability.reference_resolution import (
    ReferenceResolution,
    unresolved,
)

ACTIVATED_SOURCE: Final[str] = (
    "docs/canonical/EXECUTION_AND_CAPABILITY.md §1 and §4 + MS §Capability Graph"
)


def refusal_for(
    node: CapabilityNode, resolutions: tuple[ReferenceResolution, ...]
) -> str | None:
    """Why this node's own inputs did not resolve, or None if they did.

    Deterministic by construction: the node's own declaration is read first, then
    the resolutions in the order `ReferenceResolvers.resolve` produced them, which
    is the canonical schema's field order followed by each field's declared
    reference order. The first refusal wins, so the same inputs always yield the
    same reason as well as the same state.
    """
    if node.configured_state is not ConfiguredState.CONFIGURED:
        return (
            f"the node declares configured_state "
            f"{node.configured_state.value}; a capability that declares itself "
            "unconfigured has not resolved"
        )
    outstanding = unresolved(resolutions)
    if outstanding:
        first = outstanding[0]
        return (
            f"{first.field} reference {first.reference!r} did not resolve: "
            f"{first.reason}"
        )
    return None
