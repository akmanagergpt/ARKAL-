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

import hashlib
import os
import pathlib

from arkali.evidence.artifact.content_address import is_address
from arkali.kernel.contracts.content_address import address_of

__all__ = ["address_of", "is_address"]


def file_manifest(root: pathlib.Path) -> dict[str, dict[str, object]]:
    """Sorted content identity; never follows symlinks or stable snapshot scaffolding.

    Shared by the staged candidate ledger. The ledger remains the lifecycle
    authority; this helper only hashes bytes within the candidate root.
    """
    manifest: dict[str, dict[str, object]] = {}
    if not root.is_dir():
        return manifest
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = pathlib.Path(dirpath)
        if current == root:
            dirnames[:] = [d for d in dirnames if d != "snapshot"]
        dirnames[:] = [d for d in dirnames if not (current / d).is_symlink()]
        for name in filenames:
            path = current / name
            if path.is_symlink():
                continue
            relative = path.relative_to(root)
            data = path.read_bytes()
            manifest[relative.as_posix()] = {
                "byte_length": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
    return manifest
