"""Sole `engineering.plugin` importer of `kernel.contracts.content_address`.

ADR-0008 decomposition. Three C-30 modules in this context each need a
content address (`manifest.py`, `trust4_execution_gate.py`, `research.py`),
which would otherwise make `engineering.plugin` three separate importers of
a kernel primitive already carrying real fan-in pressure - measured at 15 of
15 (the ceiling) once this phase's own Package 3 landed. One shared
importer, not three, keeps this context's contribution to that ceiling at
one, the same absorber-module shape `contract_violation_base.py` already
established for the error taxonomy.
"""

from __future__ import annotations

from arkali.kernel.contracts.content_address import address_of, is_address

__all__ = ["address_of", "is_address"]
