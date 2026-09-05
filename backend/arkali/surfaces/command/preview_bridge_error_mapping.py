"""Product-preview-resolution error to HTTP-status mapping.

Owner: `surfaces.command`.

WHY THIS IS A SEPARATE MODULE. `error_mapping.py` already touches three
bounded contexts (`control.registry.project`, `control.policy`, `kernel.
contracts`), exactly `max_contexts_touched_by_module`. Adding `evidence.
artifact`'s taxonomy there would make four, so it lives here and `error_
mapping.py` composes it across a same-context import -- the identical
`job_error_mapping.py`/`workflow_error_mapping.py` precedent.

NOTHING IS SWALLOWED. Only the refusals this surface genuinely has an
opinion about appear; an unmapped error propagates.
"""

from __future__ import annotations

from typing import Final

from arkali.evidence.artifact.errors import InvalidArtifactIdentity, UnknownArtifact
from arkali.surfaces.command.product_preview_resolution import (
    _NoRevisionForProjectError,
    _ProvenanceNotManagedProductError,
    _ReferencedCandidateNotEligibleError,
    _RevisionHasNoProvenanceError,
    _UnknownRevisionForProjectError,
)

#: Ordered most-specific first, matching the sibling tables' discipline.
PREVIEW_BRIDGE_STATUS_BY_ERROR: Final[tuple[tuple[type[Exception], int], ...]] = (
    (_NoRevisionForProjectError, 409),
    (_UnknownRevisionForProjectError, 404),
    (_RevisionHasNoProvenanceError, 409),
    (InvalidArtifactIdentity, 400),
    (UnknownArtifact, 404),
    (_ProvenanceNotManagedProductError, 422),
    (_ReferencedCandidateNotEligibleError, 409),
)
