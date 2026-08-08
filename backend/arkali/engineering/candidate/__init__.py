"""Bounded context: engineering.candidate (layer engineering, rank 4).

Canonical authority for:
  - candidate_workspace_content

Protected Core: no.
Implementation phase: 12.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "engineering.candidate"
__layer__ = "engineering"
__layer_rank__ = 4
__protected_core__ = False
__all__: list[str] = []
