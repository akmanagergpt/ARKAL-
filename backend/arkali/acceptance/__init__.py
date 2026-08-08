"""Bounded context: acceptance.engine (layer evidence, rank 2).

Canonical authority for:
  - acceptance_verdict
  - phase_gating_before_phase_13

Protected Core: yes.
Implementation phase: 2 (gate checker) / 13 (engine).

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "acceptance.engine"
__layer__ = "evidence"
__layer_rank__ = 2
__protected_core__ = True
__all__: list[str] = []
