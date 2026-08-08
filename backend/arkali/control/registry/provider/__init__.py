"""Bounded context: control.registry.provider (layer control, rank 1).

Canonical authority for:
  - provider_identity
  - model_identity
  - provider_configuration
  - provider_health
  - provider_availability
  - provider_cost_metadata
  - provider_fallback_configuration

Protected Core: no.
Implementation phase: 9.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "control.registry.provider"
__layer__ = "control"
__layer_rank__ = 1
__protected_core__ = False
__all__: list[str] = []
