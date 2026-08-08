"""Bounded context: lifecycle.evolution (layer lifecycle, rank 5).

Canonical authority for:
  - evolution_campaign_state

Protected Core: no.
Implementation phase: 23.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "lifecycle.evolution"
__layer__ = "lifecycle"
__layer_rank__ = 5
__protected_core__ = False
__all__: list[str] = []
