"""Bounded context: surfaces.command (layer surfaces, rank 6).

Canonical authority for:
  - command_center_presentation

Protected Core: no.
Implementation phase: 5 onward (slices) / 27 (consolidation).

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "surfaces.command"
__layer__ = "surfaces"
__layer_rank__ = 6
__protected_core__ = False
__all__: list[str] = []
