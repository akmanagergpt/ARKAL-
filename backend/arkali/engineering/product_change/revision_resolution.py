"""Managed Product current-revision resolution and immutable-source
materialization (D-030 Rulings 3, 18, 19).

AUTHORITY BOUNDARIES. `ProjectRegistry` (`control.registry.project`,
unmodified) supplies revision identity/ordering; `evidence.artifact.
ArtifactStore` (unmodified) supplies the real, content-addressed
provenance record and content bytes. `engineering.candidate` is reached
only through a structural `_CandidateSourceResolver` Protocol -- a direct
import would extend that context's own already-4-of-4 orchestration-depth
chain to 5, the identical reasoning `product_registration.py`
(`engineering.factory`) and `product_preview_resolution.py`
(`surfaces.command`) already established for the same edge.

CURRENT REVISION = MAX SEQUENCE (RULING 3). No new pointer, column or
table -- `ProjectRevisionRecord.sequence` is already real, DB-enforced,
monotonic identity this module only ever reads.

TWO REAL PROVENANCE SHAPES, EACH RESOLVED TO A REAL DIRECTORY.
`_MANAGED_PRODUCT_PROVENANCE_SPEC` (byte-identical to `engineering.
factory.product_registration`'s own marker, redeclared here rather than
imported for the identical reason `_ACCEPTED_STATE` is redeclared
independently across this session's own prior work -- a same-layer
`engineering.factory` import is not legal from here either) names a
revision whose real source already lives at a real, permanent
`CandidateLedger` candidate directory -- resolved via the injected
Protocol, never copied into `ArtifactStore` itself.
`_MANAGED_PRODUCT_REVISION_SOURCE_SPEC` names a revision this context
itself promoted (Ruling 17/19): its real source is a deterministic ZIP
archive, registered as ONE real content-addressed `ArtifactStore` blob --
REUSING that store's own existing bytes-in/bytes-out contract exactly as
designed, never a second source repository. Materializing either shape
back into a real directory is the whole of what `materialized_source`
below does.
"""

from __future__ import annotations

import io
import json
import pathlib
import tempfile
import zipfile
from contextlib import contextmanager
from typing import Iterator, Protocol, runtime_checkable

from arkali.control.registry.project.records import ProjectRevisionRecord
from arkali.control.registry.project.registry import ProjectRegistry
from arkali.engineering.product_change.errors import (
    NoBaseRevisionError,
    RevisionSourceUnavailableError,
)
from arkali.evidence.artifact.store import ArtifactStore

#: Must stay byte-identical to `engineering.factory.product_registration`'s
#: own marker -- see the module docstring for why it is redeclared, not
#: imported.
_MANAGED_PRODUCT_PROVENANCE_SPEC = "managed-product-provenance/1.0.0"
#: This context's own marker for a revision IT promoted (never used by
#: `product_registration.py`, which only ever writes the spec above).
_MANAGED_PRODUCT_REVISION_SOURCE_SPEC = "managed-product-revision-source/1.0.0"


@runtime_checkable
class _CandidateSourceResolver(Protocol):
    """Structural shape reaching `engineering.candidate.preview`'s own
    private `_candidate_dir` -- unimported, see the module docstring."""

    def source_dir(self, candidate_id: str) -> pathlib.Path: ...


def resolve_current_revision(project_id: str, *, registry: ProjectRegistry) -> ProjectRevisionRecord:
    """The project's own real revision with the greatest recorded
    `sequence` -- Ruling 3's own canonical definition, read from existing
    identity, never a new pointer."""
    revisions = registry.revisions_of(project_id)
    if not revisions:
        raise NoBaseRevisionError(f"project {project_id!r} has no revision to base a change on")
    return max(revisions, key=lambda r: r.sequence)


@contextmanager
def materialized_source(
    revision: ProjectRevisionRecord, *, artifacts: ArtifactStore,
    candidate_source_resolver: _CandidateSourceResolver,
) -> Iterator[pathlib.Path]:
    """Yields a real, existing directory containing `revision`'s own
    immutable source. For a Factory-origin revision this is the real,
    permanent candidate directory (nothing to clean up). For a
    previously-promoted edited revision this is a fresh temporary
    directory holding the unzipped archive, always removed on exit --
    never the permanent copy, so a caller mutating it (the next
    modification's own workspace materialization step) can never corrupt
    the registered artifact.
    """
    if revision.provenance_ref is None:
        raise RevisionSourceUnavailableError(
            f"revision {revision.revision_id!r} carries no provenance_ref"
        )
    artifact = artifacts.require(revision.provenance_ref)
    provenance = artifact.provenance
    if provenance is None:
        raise RevisionSourceUnavailableError(
            f"artifact {revision.provenance_ref!r} carries no recorded provenance"
        )
    if provenance.specification_version == _MANAGED_PRODUCT_PROVENANCE_SPEC:
        payload = json.loads(artifacts.content_of(revision.provenance_ref))
        candidate_id = str(payload["candidate_id"])
        yield candidate_source_resolver.source_dir(candidate_id)
        return
    if provenance.specification_version == _MANAGED_PRODUCT_REVISION_SOURCE_SPEC:
        archive_bytes = artifacts.content_of(revision.provenance_ref)
        with tempfile.TemporaryDirectory(prefix="product-change-source-") as temp_dir:
            with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
                archive.extractall(temp_dir)
            yield pathlib.Path(temp_dir)
        return
    raise RevisionSourceUnavailableError(
        f"revision {revision.revision_id!r}'s provenance artifact "
        f"{revision.provenance_ref!r} does not carry a recognised Managed "
        "Product source marker"
    )


def archive_source(root: pathlib.Path) -> bytes:
    """A deterministic ZIP of every real file under `root` -- sorted file
    order, fixed per-entry timestamp, so two archives of byte-identical
    trees are themselves byte-identical (the same determinism discipline
    `engineering.candidate.ledger.file_manifest` already establishes for
    its own sorted, symlink-safe walk, applied here to produce real bytes
    `ArtifactStore.register` can content-address rather than a manifest
    describing them)."""
    buffer = io.BytesIO()
    paths = sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink())
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()
