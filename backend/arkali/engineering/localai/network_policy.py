"""Local-Only network-egress proof for local AI calls (Stage 7, ARK-REQ-0129).

Owner: engineering.localai.

UNDER LOCAL-ONLY, LOCAL AI MUST REMAIN AVAILABLE AND NEVER REACH THE NETWORK.
MS §Local-Only mode: "Local AI, local execution and all local capabilities
remain available" while "the Policy Decision Point returns DENY for all
outbound network egress from every trust tier". Every adapter call this
context makes targets loopback by construction (`ollama_adapter.py`,
`openai_compatible_adapter.py` both refuse a non-loopback endpoint at
construction), so the real PDP's `NETWORK_EXTERNAL` `LOOPBACK_ONLY`/Local-Only
rule can only ever see `target_is_loopback=True` here - proving the negative
control structurally rather than merely by policy: this context never
constructs an adapter capable of asking the PDP to permit a non-loopback call.

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
