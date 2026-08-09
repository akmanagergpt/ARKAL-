"""Recovery-specific backup manifest.

Owner: `lifecycle.recovery` (Protected Core) — AUTHORITY_MAP.yaml concern
`backup_and_restore`.

DELIBERATELY NARROW. This is not the Phase 6 evidence/artifact plane and must
not become one. It carries only what a **restore decision** needs: which image,
which schema revision, how big, and a digest to detect corruption. There is no
content-addressed identity, no provenance chain and no artifact lineage —
`evidence.artifact` owns those from Phase 6, and duplicating them here would
create the competing provenance authority the authority map forbids.

NO RAW SECRET, AND NO HOST PATH. `source_database` is a file **name**, never a
path: a manifest travels with the backup, and an absolute path leaks the
operator's filesystem layout for no recovery benefit. A control asserts no
field name or value is secret-shaped.

INTEGRITY IS RECOMPUTED, NEVER TRUSTED. `digest` and `size_bytes` are what the
image was when written. `verify_against` re-reads the image and compares. A
manifest that agrees with itself proves nothing, so nothing here reports a
backup sound on the strength of its own recorded values.
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
from typing import Final

from pydantic import BaseModel, ConfigDict

from arkali.kernel.persistence.backup import file_digest, looks_like_sqlite

#: Semver over the manifest shape. A consumer that cannot read a major version
#: must refuse the backup rather than guess at the fields.
MANIFEST_VERSION: Final[str] = "1.0.0"

#: The two components a backup consists of. Either one missing is not a backup.
MANIFEST_SUFFIX: Final[str] = ".manifest.json"
IMAGE_SUFFIX: Final[str] = ".db"


class ManifestError(Exception):
    """A backup manifest is absent, unreadable, or disagrees with its image."""


class BackupManifest(BaseModel):
    """What a restore decision needs to know before touching a target."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_version: str = MANIFEST_VERSION
    backup_id: str
    #: File name of the database this image was taken from. Never a full path.
    source_database: str
    #: Alembic revision applied to the source when the image was taken. `None`
    #: means the source carried no migration state, which is itself a fact a
    #: restore must be able to refuse on.
    schema_revision: str | None
    created_at: dt.datetime
    digest: str
    size_bytes: int

    def compatible_with(self, target_revision: str | None) -> bool:
        """Whether this backup may be restored into a target at `target_revision`.

        Phase 5 requires equality: restoring an image whose schema differs from
        the target's is how a "successful" restore produces an unusable
        database. Migrating across revisions during restore is the Phase 20
        migration-safety workflow (ARK-REQ-0151) and is not implemented here.
        """
        return self.schema_revision is not None and self.schema_revision == target_revision

    def render(self) -> str:
        return (
            f"backup {self.backup_id} of {self.source_database} "
            f"@{self.schema_revision} {self.size_bytes}B"
        )


def manifest_path(image: pathlib.Path) -> pathlib.Path:
    return image.with_name(image.name + MANIFEST_SUFFIX)


def write_manifest(image: pathlib.Path, manifest: BackupManifest) -> pathlib.Path:
    path = manifest_path(image)
    path.write_text(
        json.dumps(json.loads(manifest.model_dump_json()), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def read_manifest(image: pathlib.Path) -> BackupManifest:
    """Load a manifest, refusing anything unreadable or malformed.

    Fails closed: a missing file, invalid JSON, an unknown field or a
    major-version the reader does not understand are all refusals, never a
    partially populated manifest.
    """
    path = manifest_path(image)
    if not path.is_file():
        raise ManifestError(f"backup component missing: no manifest at {path.name}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not readable JSON: {exc}") from exc
    try:
        manifest = BackupManifest(**raw)
    except Exception as exc:  # pydantic validation, reported not repaired
        raise ManifestError(f"manifest does not satisfy its contract: {exc}") from exc
    if manifest.manifest_version.split(".")[0] != MANIFEST_VERSION.split(".")[0]:
        raise ManifestError(
            f"manifest major version {manifest.manifest_version} is not readable "
            f"by this recovery implementation ({MANIFEST_VERSION})"
        )
    return manifest


def verify_against(image: pathlib.Path, manifest: BackupManifest) -> None:
    """Recompute the image's integrity and compare. Raises on any disagreement.

    This is the only integrity statement the recovery flow trusts, because it
    is the only one derived from the bytes on disk at restore time.
    """
    if not image.is_file():
        raise ManifestError(f"backup component missing: no image at {image.name}")
    if not looks_like_sqlite(image):
        raise ManifestError(
            f"{image.name} does not carry a SQLite header; refusing to treat it "
            "as a restorable image"
        )
    actual_size = image.stat().st_size
    if actual_size != manifest.size_bytes:
        raise ManifestError(
            f"size mismatch: manifest records {manifest.size_bytes}B, image is "
            f"{actual_size}B"
        )
    actual_digest = file_digest(image)
    if actual_digest != manifest.digest:
        raise ManifestError(
            f"integrity mismatch for {image.name}: recorded {manifest.digest[:16]}, "
            f"recomputed {actual_digest[:16]}"
        )
