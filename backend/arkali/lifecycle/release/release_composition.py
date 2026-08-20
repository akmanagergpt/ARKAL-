"""C-31 final release manifest composition: registers the SBOM and
suspicious-package-review as real C-14 artifacts and assembles the final
release manifest artifact whose parents cite all three real, already-
registered sub-artifacts (ARK-REQ-0124 partial, ARK-REQ-0350 partial).

Owner: `lifecycle.release` (Protected Core).

WHY THIS IS SEPARATE FROM `release_provenance.py`. That module registers
ONE artifact - the release candidate's own declaration - with `parents=()`,
honestly, because at declaration time nothing has been derived yet
(`release_provenance.py`'s own module docstring). This module is the point
where a genuine derivation exists: the final manifest artifact's parents
are the SBOM artifact and the suspicious-package-review artifact, both
real, already-registered C-14 artifacts by the time this function
assembles them - `ArtifactStore.register`'s own foreign-key check on
`parents` proves this at write time, not merely by convention.

`evidence_complete` IS RE-DERIVED, NEVER A STORED FLAG. `verify_evidence_
complete` re-checks (via `ArtifactRegistrar.verify`) that all four
artifacts this composition names - provenance, SBOM, suspicious-package-
review, and the final manifest itself - are still genuinely present and
byte-correct, immediately before answering. A `release_guard` context built
from a cached boolean would be exactly the fabricated-evidence risk
`ARK-REQ-0218`/`ARK-REQ-0355`'s own rule forbids, restated for this context.
"""

from __future__ import annotations

import json
from typing import Final

from pydantic import BaseModel, ConfigDict

from arkali.lifecycle.release.release_provenance import ArtifactRegistrar, ProvenanceFields
from arkali.lifecycle.release.sbom import SoftwareBillOfMaterials
from arkali.lifecycle.release.suspicious_package_review import SuspiciousPackageReview

CONTRACT_ID: Final[str] = "C-31"
PRODUCER: Final[str] = "lifecycle.release.release_composition"


class ReleaseManifestComposition(BaseModel):
    """C-31: the four real, content-addressed artifacts one release
    declaration ultimately assembles."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    release_id: str
    core_revision_id: str
    provenance_artifact_id: str
    sbom_artifact_id: str
    review_artifact_id: str
    manifest_artifact_id: str


def _register_sbom(
    artifacts: ArtifactRegistrar, release_id: str, core_revision_id: str,
    sbom: SoftwareBillOfMaterials,
) -> str:
    payload = json.dumps(
        {
            "contract": CONTRACT_ID,
            "release_id": release_id,
            "entries": [entry.model_dump() for entry in sbom.entries],
        },
        sort_keys=True,
    ).encode("utf-8")
    return artifacts.register(
        payload,
        ProvenanceFields(
            producer_agent=PRODUCER, provider_model="none", task_id=release_id,
            specification_version=CONTRACT_ID, context_hash=core_revision_id,
        ),
    )


def _register_review(
    artifacts: ArtifactRegistrar, release_id: str, core_revision_id: str,
    review: SuspiciousPackageReview,
) -> str:
    payload = json.dumps(
        {
            "contract": CONTRACT_ID,
            "release_id": release_id,
            "reviewed_count": review.reviewed_count,
            "findings": [finding.model_dump() for finding in review.findings],
        },
        sort_keys=True,
    ).encode("utf-8")
    return artifacts.register(
        payload,
        ProvenanceFields(
            producer_agent=PRODUCER, provider_model="none", task_id=release_id,
            specification_version=CONTRACT_ID, context_hash=core_revision_id,
        ),
    )


def compose_release_manifest(
    artifacts: ArtifactRegistrar, *, release_id: str, core_revision_id: str,
    provenance_artifact_id: str, sbom: SoftwareBillOfMaterials,
    review: SuspiciousPackageReview,
) -> ReleaseManifestComposition:
    """Register the SBOM and review as real artifacts, then the final
    manifest artifact whose `parents` cite all three - the one point in this
    pipeline where a genuine derivation exists to record."""
    sbom_id = _register_sbom(artifacts, release_id, core_revision_id, sbom)
    review_id = _register_review(artifacts, release_id, core_revision_id, review)
    manifest_payload = json.dumps(
        {
            "contract": CONTRACT_ID,
            "release_id": release_id,
            "core_revision_id": core_revision_id,
            "provenance_artifact_id": provenance_artifact_id,
            "sbom_artifact_id": sbom_id,
            "review_artifact_id": review_id,
        },
        sort_keys=True,
    ).encode("utf-8")
    manifest_id = artifacts.register(
        manifest_payload,
        ProvenanceFields(
            producer_agent=PRODUCER, provider_model="none", task_id=release_id,
            specification_version=CONTRACT_ID, context_hash=core_revision_id,
            parents=(provenance_artifact_id, sbom_id, review_id),
        ),
    )
    return ReleaseManifestComposition(
        release_id=release_id, core_revision_id=core_revision_id,
        provenance_artifact_id=provenance_artifact_id, sbom_artifact_id=sbom_id,
        review_artifact_id=review_id, manifest_artifact_id=manifest_id,
    )


def verify_evidence_complete(
    artifacts: ArtifactRegistrar, composition: ReleaseManifestComposition,
) -> bool:
    """Real re-verification of every artifact this composition names - never
    trusts that registration having once succeeded still holds true."""
    return (
        artifacts.verify(composition.provenance_artifact_id)
        and artifacts.verify(composition.sbom_artifact_id)
        and artifacts.verify(composition.review_artifact_id)
        and artifacts.verify(composition.manifest_artifact_id)
    )


__all__ = [
    "ReleaseManifestComposition",
    "compose_release_manifest",
    "verify_evidence_complete",
]
