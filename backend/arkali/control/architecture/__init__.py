"""Bounded context: control.architecture (layer control, rank 1).

Canonical authority for:
  - architecture_rules_and_budgets
  - protected_core_membership

Protected Core: yes.
Implementation phase: 2.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "control.architecture"
__layer__ = "control"
__layer_rank__ = 1
__protected_core__ = True
__all__: list[str] = []
