"""Bounded context: lifecycle.release (layer lifecycle, rank 5).

Canonical authority for:
  - stable_promotion

Protected Core: yes.
Implementation phase: 26.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "lifecycle.release"
__layer__ = "lifecycle"
__layer_rank__ = 5
__protected_core__ = True
__all__: list[str] = []
