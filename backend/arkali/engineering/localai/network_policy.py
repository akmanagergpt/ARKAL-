"""Local-Only network-egress proof for local AI calls (Stage 7, ARK-REQ-0129).

Owner: engineering.localai.

WHY LOCAL AI'S OWN TRAFFIC IS NEVER ROUTED THROUGH THIS MODULE. MS
§Local-Only mode is two separate guarantees: outbound network egress is DENY
"from every trust tier" (`NETWORK_EXTERNAL`'s canonical fixed rule is
unconditional DENY-in-Local-Only - real, measured directly: the PDP denies
`NETWORK_EXTERNAL` even for a loopback target once `local_only=True`, because
that class exists to gate traffic that LEAVES the host, not to award loopback
an exemption), while separately "Local AI, local execution and all local
capabilities remain available" and "loopback remains permitted". The
canonical resolution is structural, not a policy exemption: `ollama_adapter.py`
and `openai_compatible_adapter.py` both refuse a non-loopback endpoint at
CONSTRUCTION (`errors.LocalRuntimeTargetNotLoopbackError`) and import nothing
from `control.policy` - their real HTTP calls are never classified as
`NETWORK_EXTERNAL` at all, so Local-Only mode cannot deny what it is never
asked to permit. That is what "remains available" means here: independence
from the policy state, not a carved-out AUTO.

WHAT `gate_local_call` ACTUALLY PROVES. The negative control: if a caller
somehow held a non-loopback endpoint, classifying it as `NETWORK_EXTERNAL` and
asking the real PDP proves the honest, unweakened decision the canonical
matrix specifies (`ASK_USER` outside Local-Only, `DENY` inside) - this
context's own adapters never construct such a target, so this function exists
to prove the negative control holds even if one were attempted, never to gate
a genuine loopback call.

STRUCTURAL PROTOCOL, NOT AN IMPORT. `PolicyDecisionSource` mirrors
`control.policy.pdp.PolicyDecisionPoint.decide_network_egress` exactly, the
identical shape `engineering.plugin.research.PolicyDecisionSource` already
established and for the same reason: `decide_network_egress` takes and
returns only primitive types specifically so a caller needing it does not have
to add a new cross-context edge into `control.policy` (whose
`policy_contract.py` sits at its own fan-in ceiling). This module adds no
edge into `control.policy` at all.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from urllib.parse import urlparse

#: Hostnames this context treats as loopback. Anything else is external.
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@runtime_checkable
class PolicyDecisionSource(Protocol):
    """Structural mirror of `PolicyDecisionPoint.decide_network_egress`."""

    def decide_network_egress(
        self,
        *,
        actor: str,
        trust_tier: str,
        local_only: bool,
        target_is_loopback: bool | None = None,
    ) -> str: ...


def is_loopback_endpoint(endpoint: str) -> bool:
    """Whether `endpoint`'s host is one this context treats as loopback."""
    return urlparse(endpoint).hostname in LOOPBACK_HOSTS


def gate_local_call(
    policy_source: PolicyDecisionSource,
    *,
    endpoint: str,
    actor: str,
    trust_tier: str,
    local_only: bool,
) -> str:
    """Ask the real PDP whether a call to `endpoint` may proceed.

    Never performs the call itself - this classifies the target as
    `NETWORK_EXTERNAL` with the real, derived `target_is_loopback` fact and
    records the PDP's decision, the same "classify and ask, never call"
    boundary `engineering.plugin.research.attempt_fetch` established.
    """
    return policy_source.decide_network_egress(
        actor=actor, trust_tier=trust_tier, local_only=local_only,
        target_is_loopback=is_loopback_endpoint(endpoint),
    )


__all__ = ["LOOPBACK_HOSTS", "PolicyDecisionSource", "is_loopback_endpoint", "gate_local_call"]
