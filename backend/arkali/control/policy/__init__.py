"""Bounded context: control.policy (layer control, rank 1).

Canonical authority for:
  - policy_decision
  - secret_storage_and_brokering

Protected Core: yes.
Implementation phase: 4.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.
"""

__context__ = "control.policy"
__layer__ = "control"
__layer_rank__ = 1
__protected_core__ = True
__all__: list[str] = []
