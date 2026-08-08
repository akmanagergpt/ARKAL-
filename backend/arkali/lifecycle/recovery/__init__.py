"""Bounded context: lifecycle.recovery (layer lifecycle, rank 5).

Canonical authority for:
  - stable_rollback
  - backup_and_restore

Protected Core: yes.
Implementation phase: 22B.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "lifecycle.recovery"
__layer__ = "lifecycle"
__layer_rank__ = 5
__protected_core__ = True
__all__: list[str] = []
