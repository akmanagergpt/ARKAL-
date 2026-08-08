"""Bounded context: control.capability (layer control, rank 1).

Canonical authority for:
  - capability_availability_answer

Protected Core: no.
Implementation phase: 3 (schema) / 9B (activation).

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "control.capability"
__layer__ = "control"
__layer_rank__ = 1
__protected_core__ = False
__all__: list[str] = []
