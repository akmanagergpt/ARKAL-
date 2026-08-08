"""Bounded context: engineering.import (layer engineering, rank 4).

Canonical authority for:
  - imported_project_lifecycle

Protected Core: no.
Implementation phase: 19.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.

Physical package name note (governance erratum ERR-001, closing F-0015):
the logical bounded-context identity remains `engineering.import`. Only the
physical module_root was changed to `project_import`, because `import` is a
Python reserved keyword and cannot appear in an import statement. Authority,
lifecycle, TRUST classification, Protected Core membership, dependency
direction and requirement meaning are unchanged.
"""

__context__ = "engineering.import"
__layer__ = "engineering"
__layer_rank__ = 4
__protected_core__ = False
__all__: list[str] = []
