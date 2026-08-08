"""Bounded context: execution.sandbox (layer execution, rank 3).

Canonical authority for:
  - sandbox_execution

Protected Core: no.
Implementation phase: 4.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "execution.sandbox"
__layer__ = "execution"
__layer_rank__ = 3
__protected_core__ = False
__all__: list[str] = []
