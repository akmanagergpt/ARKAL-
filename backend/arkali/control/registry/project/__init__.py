"""Bounded context: control.registry.project (layer control, rank 1).

Canonical authority for:
  - project_and_revision_identity

Protected Core: no.
Implementation phase: 5.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "control.registry.project"
__layer__ = "control"
__layer_rank__ = 1
__protected_core__ = False
__all__: list[str] = []
