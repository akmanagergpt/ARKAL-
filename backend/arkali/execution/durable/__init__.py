"""Bounded context: execution.durable (layer execution, rank 3).

Canonical authority for:
  - durable_job_state

Protected Core: no.
Implementation phase: 7.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "execution.durable"
__layer__ = "execution"
__layer_rank__ = 3
__protected_core__ = False
__all__: list[str] = []
