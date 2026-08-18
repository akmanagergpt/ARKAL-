"""Builds real C-13 capability nodes from real local-AI probe results (Stage 5).

Owner: engineering.localai.

EXPOSES CAPABILITY, NEVER ROUTING POLICY. Phase 16's `execution_routing.
select_execution_tier` is the sole routing authority and is not modified by
this module or by this phase (`ARK-REQ-0392`/`0393`, D-026). This module
builds the one thing `engineering.localai` owns: a `CapabilityNode` (C-13,
`control.capability`) whose `configured_state` is CONFIGURED only when a real
runtime probe and a real hardware-aware suitability verdict both genuinely
resolved PASS. It composes `control.capability`'s canonical schema; it stores
no provider identity, no health and no availability of its own (no shadow
registry - `runtime_requirements` carries only local, non-provider-owned facts,
proven by the existing `validate_no_shadow_registry` check against
`AUTHORITY_MAP.yaml`'s `provider_authority.fields_owned`).

CONFIGURED IS EARNED, NEVER DEFAULTED. `build_capability_node` reads
`RuntimeProbeResult.state` and `SuitabilityVerdict.state` and never assumes a
model is usable because it was merely listed by a runtime - the same
"existence of an adapter proves nothing about the host" principle
`control.isolation.backend_probe` states for isolation backends.
"""

from __future__ import annotations

import re

from arkali.control.capability.capability_node import CapabilityNode, ConfiguredState
from arkali.engineering.localai.adapter import (
    HonestState,
    LocalModelDescriptor,
    RuntimeProbeResult,
)
from arkali.engineering.localai.suitability import SuitabilityVerdict

_NON_IDENTIFIER = re.compile(r"[^a-z0-9]+")


def capability_id_for(descriptor: LocalModelDescriptor) -> str:
    """A stable, deterministic C-13 capability id for one local model.

    `localai.<runtime>.<slug(model_id)>` - the same runtime and the same
    model id always produce the same id, and two different models never
    collide onto the same id (the slug preserves every alphanumeric run).
    """
    slug = _NON_IDENTIFIER.sub("_", descriptor.model_id.lower()).strip("_")
    return f"localai.{descriptor.runtime}.{slug}"


def build_capability_node(
    descriptor: LocalModelDescriptor,
    probe: RuntimeProbeResult,
    suitability: SuitabilityVerdict,
    *,
    isolation_tier: str = "TRUST-1",
) -> CapabilityNode:
    """A real `CapabilityNode` for one local model, honestly configured.

    Declares no external reference (`prerequisites`, `permission_refs`,
    `evidence_requirement_refs`, `provider_refs`, `fallback_refs` all stay
    empty): a local model's own availability is this context's own probed
    fact, not another authority's. `runtime_requirements` carries only
    locally-owned metadata - never a provider-owned concern.
    """
    configured = probe.state is HonestState.PASS and suitability.state is HonestState.PASS
    return CapabilityNode(
        id=capability_id_for(descriptor),
        version=1,
        isolation_tier=isolation_tier,
        configured_state=(
            ConfiguredState.CONFIGURED if configured else ConfiguredState.UNCONFIGURED
        ),
        runtime_requirements={
            "local_ai_runtime": descriptor.runtime,
            "local_ai_quantization": descriptor.quantization,
            "local_ai_context_length": descriptor.context_length,
        },
    )


__all__ = ["capability_id_for", "build_capability_node"]
