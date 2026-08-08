"""Bounded context: evidence.artifact (layer evidence, rank 2).

Canonical authority for:
  - artifact_identity_and_provenance

Protected Core: no.
Implementation phase: 6.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "evidence.artifact"
__layer__ = "evidence"
__layer_rank__ = 2
__protected_core__ = False
__all__: list[str] = []
