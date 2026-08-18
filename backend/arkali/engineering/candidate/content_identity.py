"""Content-address re-export for `engineering.candidate` (ADR-0008 decomposition).

`manifest.py` and `assembly.py` each independently imported
`kernel.contracts.content_address` directly - two modules in the same context
holding two separate edges to the same kernel primitive, which pushed its
fan-in to 16 of the 15 ceiling once a further context (`lifecycle.evolution`,
Phase 23) gained its own genuine need for it. This is the one shared site
`engineering.candidate` now imports the kernel primitive through, the same
shape `evidence.artifact.content_address` already uses for the identity it
owns. Nothing here decides anything the kernel primitive did not already
decide; it is a re-export, not a second mechanism.
"""

from __future__ import annotations

from arkali.evidence.artifact.content_address import is_address
from arkali.kernel.contracts.content_address import address_of

__all__ = ["address_of", "is_address"]
