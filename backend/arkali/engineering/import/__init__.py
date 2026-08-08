"""Bounded context: engineering.import (layer engineering, rank 4).

Canonical authority for:
  - imported_project_lifecycle

Protected Core: no.
Implementation phase: 19.

Phase 1 bootstrap: structure only. No capability is implemented here.
Dependency rule: may depend only on strictly lower layer ranks, plus the
sibling edges declared in docs/canonical/AUTHORITY_MAP.yaml.

NOTE (Phase 1 finding F-0015): the declared module_root ends in
'import', a Python reserved keyword. This package is discoverable and
importable only via importlib.import_module(); no `import` statement can
reference it. Recorded for governance decision; not silently renamed.
"""

__context__ = "engineering.import"
__layer__ = "engineering"
__layer_rank__ = 4
__protected_core__ = False
__all__: list[str] = []
